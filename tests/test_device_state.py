import ctypes
import json
import time

import pytest

from infuse_iot.common import InfuseType
from infuse_iot.definitions.tdf import readings, structs
from infuse_iot.epacket import interface
from infuse_iot.epacket.packet import Auth, HopReceived, PacketReceived
from infuse_iot.services.ble_observations import INFUSE_SERVICE, BleObservations
from infuse_iot.services.device_state import MAX_SAFE_INTEGER, SAMPLE_ORDER_WINDOW_S, DeviceState, _value
from infuse_iot.services.pagination import PaginationError, SnapshotPages
from infuse_iot.socket_comms import GatewayControlError
from infuse_iot.tdf import TDF
from infuse_iot.time import InfuseTime

DEVICE = 0xCE7E42571A000099


def single(reading, flags=0):
    return bytes(TDF.CoreHeader(reading.ID | flags, ctypes.sizeof(reading))) + bytes(reading)


def timestamped(reading, unix_time):
    epoch = InfuseTime.epoch_time_from_unix(unix_time)
    timestamp = TDF.AbsoluteTime(epoch // 65536, epoch % 65536)
    return bytes(TDF.CoreHeader(reading.ID | TDF.flags.TIMESTAMP_ABSOLUTE, ctypes.sizeof(reading))) + (
        bytes(timestamp) + bytes(reading)
    )


def packet(reading, device=DEVICE, payload=None):
    hop = HopReceived(
        device,
        interface.ID.BT_ADV,
        interface.Address(interface.Address.BluetoothLeAddr(0, 0x60FCF1006161)),
        Auth.NETWORK,
        0xCE7E50,
        0,
        0,
        -65,
    )
    return PacketReceived([hop], InfuseType.TDF, single(reading) if payload is None else payload)


def announce():
    return readings.announce(0xCE710003, structs.tdf_struct_mcuboot_img_sem_ver(1, 3, 1, 0x7BEE09D5), 0, 0, 10, 0, 0)


@pytest.fixture
def clock(monkeypatch):
    """Monotonic time, shared by the state and its snapshots."""
    now = [10.0]
    monkeypatch.setattr("infuse_iot.services.device_state.time.monotonic", lambda: now[0])
    return now


def unsafe_integers(value):
    if isinstance(value, dict):
        return [n for v in value.values() for n in unsafe_integers(v)]
    if isinstance(value, list):
        return [n for v in value for n in unsafe_integers(v)]
    return [value] if isinstance(value, int) and abs(value) > MAX_SAFE_INTEGER else []


def test_split_advertisements_preserve_marker_and_name():
    observations = BleObservations()
    observations.observe("device", "CT Logger", -60, [], [])
    observations.observe("device", None, -61, [0x0DE4], [INFUSE_SERVICE.upper()])
    observations.observe("device", None, -62, [], [])
    result = observations.snapshot()
    assert result["total"] == 1
    row = result["items"][0]
    assert row["name"] == "CT Logger"
    assert row["manufacturer_ids"] == ["0x0de4"]
    assert row["infuse_candidate"]


def test_old_markers_expire_without_losing_recent_name(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("infuse_iot.services.ble_observations.time.monotonic", lambda: clock[0])
    observations = BleObservations()
    observations.observe("device", None, -60, [0x0DE4], [])
    clock[0] = 30
    observations.observe("device", "CT Logger", -60, [], [])
    row = observations.snapshot(max_age_seconds=20)["items"][0]
    assert row["name"] == "CT Logger" and not row["infuse_candidate"]


def test_bluetooth_addresses_share_one_form():
    observations = BleObservations()
    observations.observe("60:fc:f1:00:61:61", None, -60, [], [])
    observations.observe("60-FC-F1-00-61-61", None, -60, [], [])
    (row,) = observations.snapshot()["items"]
    assert row["identifier"] == "60:FC:F1:00:61:61"
    state = DeviceState()
    state.observe(packet(announce()))
    assert state.snapshot()["items"][0]["bluetooth"]["address"] == row["identifier"]
    # The viewer keeps its existing format
    assert state.display_rows[DEVICE]["bt_addr"] == "60:fc:f1:00:61:61"


def test_state_keeps_firmware_freshness_separate_from_temperature(clock):
    state = DeviceState()
    assert state.observe(packet(announce()))
    clock[0] = 110
    assert state.observe(packet(readings.ambient_temperature(23000)))
    result = state.snapshot(max_age_seconds=30)
    row = result["items"][0]
    assert row["id"] == "0xce7e42571a000099"
    assert row["firmware_version"] == "1.3.1+7bee09d5"
    assert row["age_seconds"] == 0
    # The version reports the age of its announcement, not of the latest packet
    assert (row["firmware_age_seconds"], row["firmware_stale"]) == (100, True)
    assert row["readings"]["ANNOUNCE"]["stale"]
    assert not row["readings"]["AMBIENT_TEMPERATURE"]["stale"]
    assert row["readings"]["AMBIENT_TEMPERATURE"]["values"]["temperature"] == 23.0
    assert state.display_rows[DEVICE]["ANNOUNCE"]["version"] == "1.3.1+7bee09d5"
    # Selecting other fields keeps the version's own age
    (selected,) = state.snapshot(max_age_seconds=30, fields=["AMBIENT_TEMPERATURE"])["items"]
    assert list(selected["readings"]) == ["AMBIENT_TEMPERATURE"]
    assert (selected["firmware_version"], selected["firmware_age_seconds"]) == ("1.3.1+7bee09d5", 100)
    json.dumps(result, allow_nan=False)


def test_untimestamped_array_has_no_sample_time():
    state = DeviceState()
    temperature = readings.ambient_temperature(23000)
    header = TDF.CoreHeader(temperature.ID | TDF.flags.TIME_ARRAY, ctypes.sizeof(temperature))
    payload = bytes(header) + bytes(TDF.ArrayHeader(10, 32768)) + bytes(temperature) * 10
    assert state.observe(packet(temperature, payload=payload))
    reading = state.snapshot()["items"][0]["readings"]["AMBIENT_TEMPERATURE"]
    assert reading["sampled_at"] is None
    assert reading["received_at"] is not None


def test_delayed_sample_does_not_replace_newer_sample():
    state = DeviceState()
    state.observe(packet(None, payload=timestamped(readings.ambient_temperature(23000), 1761000100.0)))
    # A backlog sample from earlier arrives later
    state.observe(packet(None, payload=timestamped(readings.ambient_temperature(19000), 1761000000.0)))
    reading = state.snapshot()["items"][0]["readings"]["AMBIENT_TEMPERATURE"]
    assert reading["values"]["temperature"] == 23.0
    assert reading["sampled_at"] == pytest.approx(1761000100.0)
    # An untimestamped sample cannot be ordered, so the latest to arrive is kept
    state.observe(packet(readings.ambient_temperature(21000)))
    assert state.snapshot()["items"][0]["readings"]["AMBIENT_TEMPERATURE"]["values"]["temperature"] == 21.0


def test_wrong_device_clock_cannot_freeze_a_reading(clock):
    state = DeviceState()

    def sample(temperature, unix_time):
        state.observe(packet(None, payload=timestamped(readings.ambient_temperature(temperature), unix_time)))
        return state.snapshot()["items"][0]["readings"]["AMBIENT_TEMPERATURE"]["values"]["temperature"]

    now = time.time()
    # A sample stamped a day after its receipt shows a clock glitch, so it cannot outrank the next one.
    assert sample(20000, now + 86400) == 20.0
    assert sample(21000, now) == 21.0
    # After a reboot without time sync, the device clock restarts near the epoch.
    rebooted = InfuseTime.unix_time_from_epoch(1000 * 65536)
    assert sample(22000, rebooted) == 21.0
    clock[0] += SAMPLE_ORDER_WINDOW_S
    assert sample(23000, rebooted + 60) == 23.0
    assert sample(24000, rebooted + 61) == 24.0
    # Samples stamped earlier than the reset-clock reading are again a backlog.
    assert sample(25000, rebooted + 30) == 24.0


def test_device_ids_in_readings_are_exact_strings():
    state = DeviceState()
    state.observe(packet(readings.infuse_bluetooth_rssi(0xCE7E42571A000099, -70)))
    result = state.snapshot()
    values = result["items"][0]["readings"]["INFUSE_BLUETOOTH_RSSI"]["values"]
    assert values == {"infuse_id": "0xce7e42571a000099", "rssi": -70}
    assert not unsafe_integers(json.loads(json.dumps(result)))
    # Other integers that JavaScript cannot represent exactly are decimal strings
    assert _value(2**60) == str(2**60)
    assert _value(-(2**60)) == str(-(2**60))
    assert _value(MAX_SAFE_INTEGER) == MAX_SAFE_INTEGER
    assert _value([1, 2**64 - 1]) == [1, str(2**64 - 1)]


def test_coordinates_keep_their_decoded_values():
    state = DeviceState()
    location = structs.tdf_struct_gcs_location(2000000000, 2100000000, 0)
    state.observe(packet(readings.gcs_wgs84_llha(location, 5000, 7000)))
    reading = state.snapshot()["items"][0]["readings"]["GCS_WGS84_LLHA"]
    # The definition establishes no invalid coordinate, so none is invented
    assert reading["values"]["location"]["latitude"] == pytest.approx(200.0)
    assert reading["values"]["location"]["longitude"] == pytest.approx(210.0)
    assert "validity" not in reading


@pytest.mark.parametrize(
    "application_id, network_id",
    [("0xCE710003", "0xCE7E50"), ("ce710003", "ce7e50"), (0xCE710003, 0xCE7E50)],
)
def test_filters_are_normalized(application_id, network_id):
    state = DeviceState()
    state.observe(packet(announce()))
    result = state.snapshot(application_id=application_id, network_id=network_id)
    assert result["total"] == 1
    assert result["filters"]["application_id"] == "0xce710003"
    assert result["filters"]["network_id"] == "0xce7e50"
    assert state.snapshot(application_id="0xce710004")["total"] == 0
    with pytest.raises(ValueError, match="network_id"):
        state.snapshot(network_id="0x1000000")


@pytest.mark.parametrize(
    "parameters",
    [{"max_age_seconds": 10**400}, {"max_age_seconds": float("nan")}, {"ids": "0x1"}, {"ids": [1]}, {"fields": [1]}],
)
def test_invalid_queries_are_rejected(parameters):
    with pytest.raises(ValueError):
        DeviceState().snapshot(**parameters)


def test_snapshot_reports_coverage_and_gateway(clock, monkeypatch):
    monkeypatch.setattr("infuse_iot.services.device_state.time.time", lambda: 1761000000.0)
    state = DeviceState()
    state.gateway = {"instance_id": "abc", "version": "1.0", "gateway_kind": "native_bt", "protocol_version": 2}
    state.observe(packet(announce()))
    result = state.snapshot(ids=["CE7E42571A000099"], max_age_seconds=30)
    assert result["filters"] == {
        "ids": ["0xce7e42571a000099"],
        "application_id": None,
        "network_id": None,
        "max_age_seconds": 30,
        "fields": None,
    }
    assert result["observation_window"] == {"start": 1761000000.0, "end": 1761000000.0}
    assert result["gateway"]["instance_id"] == "abc"
    assert (result["decode_errors"], result["evictions"]) == (0, 0)


def test_bad_packet_does_not_stop_future_observations():
    state = DeviceState()
    bad = packet(announce())
    bad.payload = bytes(TDF.CoreHeader(1, 30)) + b"x"
    assert not state.observe(bad)
    assert state.decode_errors == 1
    assert state.observe(packet(announce()))
    assert state.snapshot()["total"] == 1


def test_eviction_bounds_device_memory():
    state = DeviceState(max_devices=1)
    state.observe(packet(announce(), 1))
    state.observe(packet(announce(), 2))
    assert state.snapshot()["total"] == 1
    assert 1 not in state.display_rows
    assert state.evictions == 1


def test_pages_hold_an_immutable_view_and_check_filters():
    pages = SnapshotPages(0)
    original = [{"id": "first"}, {"id": "second"}]
    first = pages.page(lambda: (original, {}), {"filter": 1}, limit=1)
    original[1]["id"] = "changed"
    second = pages.page(None, {"filter": 1}, cursor=first["next_cursor"])
    assert second["items"] == [{"id": "second"}]
    # Returned rows are copies of the snapshot
    second["items"][0]["id"] = "mutated"
    assert pages.page(None, {"filter": 1}, cursor=first["next_cursor"])["items"] == [{"id": "second"}]
    with pytest.raises(PaginationError) as error:
        pages.page(None, {"filter": 2}, cursor=first["next_cursor"])
    assert error.value.code == "invalid_cursor"


@pytest.mark.parametrize(
    "cursor, code",
    [("deadbeef:1", "snapshot_expired"), ("nonsense", "invalid_cursor"), (5, "invalid_cursor")],
)
def test_page_errors_have_codes(cursor, code):
    pages = SnapshotPages(0)
    with pytest.raises(PaginationError) as error:
        pages.page(None, {}, cursor=cursor)
    assert (error.value.code, str(error.value)) == (code, code)
    assert error.value.message
    # Gateway control replies with the code
    assert isinstance(error.value, GatewayControlError)


def test_page_beyond_snapshot_is_invalid():
    pages = SnapshotPages(0)
    first = pages.page(lambda: ([{"id": 1}, {"id": 2}], {}), {}, limit=1)
    key = first["next_cursor"].split(":")[0]
    with pytest.raises(PaginationError, match="invalid_cursor"):
        pages.page(None, {}, cursor=f"{key}:3")


def test_oversized_row_reports_budget_error():
    pages = SnapshotPages(0)
    with pytest.raises(PaginationError) as error:
        pages.page(lambda: ([{"data": "x" * 1000}], {}), {}, max_bytes=500)
    assert error.value.code == "item_exceeds_response_budget"


def test_pages_fit_the_byte_budget_exactly():
    pages = SnapshotPages(0)
    rows = [{"id": index, "padding": "x" * (index % 37)} for index in range(200)]
    cursor, received = None, []
    while True:
        result = pages.page(lambda: (rows, {"extra": "metadata"}), {}, cursor, limit=200, max_bytes=1000)
        assert len(json.dumps(result).encode()) <= 1000
        assert result["extra"] == "metadata"
        received.extend(result["items"])
        cursor = result["next_cursor"]
        if cursor is None:
            break
    assert received == rows


def test_cursor_pages_do_not_rebuild_and_stay_valid_while_used(clock, monkeypatch):
    state = DeviceState()
    for device in range(300):
        state.observe(packet(announce(), device))
    built = []
    original = DeviceState._row

    def row(*args):
        built.append(args)
        return original(*args)

    monkeypatch.setattr(DeviceState, "_row", staticmethod(row))
    result = state.snapshot(limit=30)
    assert len(built) == 300
    seen = [row["id"] for row in result["items"]]
    while result["next_cursor"]:
        # Each page is requested within the idle expiry, beyond the snapshot's first minute
        clock[0] += 50
        state.observe(packet(readings.ambient_temperature(23000), 1000))
        result = state.snapshot(cursor=result["next_cursor"], limit=30)
        seen.extend(row["id"] for row in result["items"])
    assert len(built) == 300
    assert seen == [f"0x{device:016x}" for device in range(300)]


def test_cursor_expires_when_idle_or_too_old(clock):
    state = DeviceState()
    for device in range(3):
        state.observe(packet(announce(), device))
    first = state.snapshot(limit=1)
    clock[0] += 61
    with pytest.raises(PaginationError, match="snapshot_expired"):
        state.snapshot(cursor=first["next_cursor"], limit=1)
    first = state.snapshot(limit=1)
    for _ in range(10):
        clock[0] += 55
        state.snapshot(cursor=first["next_cursor"], limit=1)
    # The snapshot's maximum lifetime ends regardless of use
    clock[0] += 55
    with pytest.raises(PaginationError, match="snapshot_expired"):
        state.snapshot(cursor=first["next_cursor"], limit=1)


def test_one_shot_lookups_do_not_evict_cursors():
    state = DeviceState()
    for device in range(60):
        state.observe(packet(announce(), DEVICE + device))
    page = state.snapshot(limit=50)
    for row in page["items"][:20]:
        lookup = state.snapshot(ids=[row["id"]], paginate=False)
        assert lookup["items"][0]["id"] == row["id"]
        assert (lookup["snapshot_id"], lookup["next_cursor"]) == (None, None)
    # Single page results are not retained either
    for _ in range(20):
        assert state.snapshot(limit=200)["next_cursor"] is None
    assert len(state.snapshot(cursor=page["next_cursor"], limit=50)["items"]) == 10
    # Without pagination, every row is returned regardless of the byte budget
    assert state.snapshot(paginate=False, max_bytes=100)["total"] == 60
    with pytest.raises(ValueError):
        state.snapshot(cursor=page["next_cursor"], paginate=False)


def test_raw_pages_fit_datagram_budget():
    observations = BleObservations()
    for index in range(100):
        observations.observe(str(index), "CT Logger", -60, [0x0DE4], [INFUSE_SERVICE])
    result = observations.snapshot(limit=200)
    assert len(json.dumps(result).encode()) <= 5000
    assert result["next_cursor"] is not None
    assert result["total"] == 100
    assert result["filters"] == {"max_age_seconds": 20, "infuse_only": False}


def test_noisy_advertiser_is_truncated_rather_than_failing_the_scan():
    observations = BleObservations()
    observations.observe("00:11:22:33:44:55", "\N{GRINNING FACE}" * 300, -70, range(0x0DE0, 0x0E00), [])
    for batch in range(5):
        services = [f"{batch:02x}{i:06x}-0000-1000-8000-00805f9b34fb" for i in range(31)]
        observations.observe("00:11:22:33:44:55", None, -70, [], [INFUSE_SERVICE, *services])
    observations.observe("AA:BB:CC:DD:EE:FF", "quiet", -60, [], [])
    result = observations.snapshot(metadata={"gateway": {"instance_id": "abc"}})
    assert len(json.dumps(result).encode()) <= 5000
    noisy = result["items"][0]
    (quiet,) = observations.snapshot(cursor=result["next_cursor"])["items"]
    assert noisy["truncated"] and not quiet["truncated"]
    # Infuse markers survive truncation
    assert "0x0de4" in noisy["manufacturer_ids"] and INFUSE_SERVICE in noisy["service_uuids"]
    assert noisy["infuse_candidate"]
    assert result["gateway"] == {"instance_id": "abc"}
    # Without pagination, nothing is truncated
    full = observations.snapshot(paginate=False)["items"][0]
    assert len(full["service_uuids"]) == 128 and not full["truncated"]
