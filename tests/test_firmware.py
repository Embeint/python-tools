"""Offline release validation and simulated firmware operations; no radio writes."""

import binascii
import ctypes
import hashlib
import json
import re
import struct
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import infuse_iot.definitions.rpc as defs
from infuse_iot.common import InfuseType
from infuse_iot.cpatch import cpatch
from infuse_iot.definitions.tdf import readings, structs
from infuse_iot.epacket import interface
from infuse_iot.epacket.packet import Auth, HopReceived, PacketReceived
from infuse_iot.services.device_operations import DeviceError
from infuse_iot.services.device_state import DeviceState
from infuse_iot.services.firmware import FirmwareService
from infuse_iot.services.jobs import JobCancelled
from infuse_iot.services.release_package import inspect_image, inspect_patch, inspect_release
from infuse_iot.socket_comms import ClientNotificationEpacketReceived, GatewayControlError
from infuse_iot.tdf import TDF
from infuse_iot.util.crc import crc16_ccitt

APP = 0xCE710003
TARGET = "1.3.1+7bee09d5"
PREVIOUS = "1.3.0+f715affe"
OLD = "1.2.0+17bf41bf"
DEVICE = 0xCE7E42571A000099


def version(value):
    semantic, build = value.split("+")
    return structs.tdf_struct_mcuboot_img_sem_ver(*map(int, semantic.split(".")), int(build, 16))


def announce_reading(value=TARGET, application=APP, board=None):
    if board is None:
        return readings.announce(application, version(value), 0, 0, 10, 0, 0)
    return readings.announce_v2(application, version(value), crc16_ccitt(board.encode()), 0, 0, 10, 0, 0)


def announcement(value=TARGET, device=DEVICE, application=APP, board=None):
    reading = announce_reading(value, application, board)
    payload = bytes(TDF.CoreHeader(reading.ID, ctypes.sizeof(reading))) + bytes(reading)
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
    return PacketReceived([hop], InfuseType.TDF, payload)


def signed_image(private, payload=b"example application" * 8):
    header = struct.pack("<IIHHIIBBHI", 0x96F3B83D, 0, 32, 0, len(payload), 0, 1, 3, 1, 0x7BEE09D5)
    signed = header + bytes(4) + payload
    signature = private.sign(signed, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32), hashes.SHA256())
    tlvs = struct.pack("<BBH", 0x10, 0, 32) + hashlib.sha256(signed).digest()
    tlvs += struct.pack("<BBH", 0x20, 0, len(signature)) + signature
    return signed + struct.pack("<HH", 0x6907, 4 + len(tlvs)) + tlvs


def make_release(tmp_path):
    root = tmp_path / "release"
    image_path = root / "logger/zephyr/zephyr.signed.bin"
    image_path.parent.mkdir(parents=True)
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = tmp_path / "trusted.pem"
    public.write_bytes(
        private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    image = signed_image(private)
    image_path.write_bytes(image)
    (root / "manifest.yaml").write_text(
        f"application:\n  primary: logger\n  id: {APP}\n  board: sr2202/nrf52840\n  version: {TARGET}\n",
        encoding="utf-8",
    )
    (root / "diffs").mkdir()
    patch = cpatch.generate(b"previous application" * 12, image, False)
    (root / "diffs" / f"{PREVIOUS}.bin").write_bytes(patch)
    return SimpleNamespace(root=root, public=public, private=private, image=image, image_path=image_path, patch=patch)


@pytest.fixture
def release(tmp_path):
    return make_release(tmp_path)


class Context:
    def __init__(self):
        self.phases = []
        self.results = []
        self.cancelled = False
        self.sent = False

    def check_cancelled(self):
        if self.cancelled:
            raise JobCancelled

    def sending(self):
        self.check_cancelled()
        self.sent = True

    def wait(self, seconds):
        self.check_cancelled()

    def progress(self, phase, **values):
        self.phases.append((phase, values))

    def checkpoint(self, result):
        self.results.append(result)


def service_for(release, tmp_path, versions=(PREVIOUS,)):
    state = DeviceState()
    for index, value in enumerate(versions):
        state.observe(announcement(value, DEVICE + index))
    return FirmwareService(("224.1.1.1", 19851), state, tmp_path / "cache")


def test_signed_image_digest_signature_and_patch_output(release, tmp_path):
    package = inspect_release(release.root, tmp_path / "cache", release.public)
    assert package["image"]["signature_status"] == "verified"
    assert package["image"]["version"] == TARGET
    assert package["patches"][PREVIOUS]["size_bytes"] == len(release.patch)
    assert inspect_image(release.image)["signature_status"] == "present_unverified"
    damaged = bytearray(release.image)
    damaged[40] ^= 1
    with pytest.raises(ValueError, match="digest mismatch"):
        inspect_image(bytes(damaged))
    with pytest.raises(ValueError, match="output does not match"):
        inspect_patch(release.patch, b"another image")
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    wrong_key = tmp_path / "wrong.pem"
    wrong_key.write_bytes(
        other.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    with pytest.raises(ValueError, match="signature verification failed"):
        inspect_image(release.image, wrong_key)


def test_manifest_version_and_symlink_escape_are_rejected(release, tmp_path):
    manifest = release.root / "manifest.yaml"
    manifest.write_text(manifest.read_text().replace(TARGET, PREVIOUS))
    with pytest.raises(ValueError, match="Manifest version"):
        inspect_release(release.root, tmp_path / "cache")
    manifest.write_text(manifest.read_text().replace(PREVIOUS, TARGET))
    outside = tmp_path / "outside.bin"
    outside.write_bytes(release.image)
    release.image_path.unlink()
    try:
        release.image_path.symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires OS privileges")
    with pytest.raises(ValueError, match="escapes"):
        inspect_release(release.root, tmp_path / "cache")


def test_six_device_plan_selects_three_patches_one_full_and_two_skips(release, tmp_path, monkeypatch):
    service = service_for(release, tmp_path, (OLD, PREVIOUS, PREVIOUS, PREVIOUS, TARGET, TARGET))
    ids = [f"0x{DEVICE + index:016x}" for index in range(6)]
    plan = service.plan(str(release.root), ids, device_boards={ids[0]: "sr2202/nrf52840"})
    assert plan["devices"][0]["board_evidence"] == "caller_assertion"
    assert [row.get("method", row["status"]) for row in plan["devices"]] == [
        "full_image",
        "patch",
        "patch",
        "patch",
        "already_current",
        "already_current",
    ]
    assert service.load_plan(plan["plan_id"]) == plan
    transfer = Mock(side_effect=lambda entry, *args: {"device_id": entry["device_id"], "status": "version_verified"})
    monkeypatch.setattr(service, "transfer", transfer)
    monkeypatch.setattr(
        service.operations,
        "read",
        Mock(
            return_value={
                "response": {"version": TARGET, "application_id": APP},
                "observed_at": time.time(),
            }
        ),
    )
    context = Context()
    result = service.run({"plan_id": plan["plan_id"]}, context)
    assert result["success"] and transfer.call_count == 4
    assert len(context.results[-1]["devices"]) == 6
    assert [row["status"] for row in result["devices"]] == ["version_verified"] * 4 + ["already_current"] * 2


def test_plan_requires_fresh_application_and_board_evidence(release, tmp_path, monkeypatch):
    service = service_for(release, tmp_path, (OLD,))
    identifier = f"0x{DEVICE:016x}"
    plan = service.plan(str(release.root), [identifier])
    assert plan["devices"][0]["status"] == "blocked"
    assert "board_unknown" in plan["devices"][0]["reason"]
    with pytest.raises(DeviceError, match="blocked"):
        service.validate_start(plan["plan_id"])
    service.state.observe(announcement(PREVIOUS, application=APP + 1))
    assert service.plan(str(release.root), [identifier])["devices"][0]["reason"] == "application_mismatch"
    service.state.observe(announcement(PREVIOUS))
    now = time.monotonic()
    monkeypatch.setattr("infuse_iot.services.device_state.time.monotonic", lambda: now + 65)
    # Newer telemetry of another kind does not refresh the firmware evidence.
    temperature = readings.ambient_temperature(23000)
    payload = bytes(TDF.CoreHeader(temperature.ID, ctypes.sizeof(temperature))) + bytes(temperature)
    service.state.observe(PacketReceived(announcement().route, InfuseType.TDF, payload))
    stale = service.plan(str(release.root), [identifier])["devices"][0]
    assert (stale["status"], stale["reason"], stale["firmware_age_seconds"]) == (
        "blocked",
        "firmware_announcement_stale",
        pytest.approx(65, abs=1),
    )
    # Plans read the state once, without retaining a cursor for other callers to evict.
    assert not service.state._pages._snapshots


def test_changed_package_and_tampered_plan_do_not_transfer(release, tmp_path, monkeypatch):
    service = service_for(release, tmp_path)
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    transfer = Mock()
    monkeypatch.setattr(service, "transfer", transfer)
    manifest = release.root / "manifest.yaml"
    manifest.write_text(manifest.read_text() + "\n# changed after approval\n")
    with pytest.raises(DeviceError, match="changed after planning"):
        service.run({"plan_id": plan["plan_id"]}, Context())
    transfer.assert_not_called()
    path = service.cache / "plans" / f"{plan['plan_id']}.json"
    modified = json.loads(path.read_text())
    modified["devices"][0]["device_id"] = "0x123"
    path.write_text(json.dumps(modified))
    with pytest.raises(DeviceError, match="integrity"):
        service.load_plan(plan["plan_id"])


def fake_transport(
    monkeypatch,
    entry,
    messages,
    acknowledgement="valid",
    current=PREVIOUS,
    fail_connection=False,
    application=APP,
    drop_preconditions=0,
    renew_error=None,
):
    clients: list = []
    sent = []
    closed = []
    renewals = []
    drops = [drop_preconditions]

    class Client:
        def __init__(self, address):
            self.index = len(clients)
            clients.append(self)

        def capabilities(self):
            return {"features": ["operation_ownership"]}

        @contextmanager
        def operation(self, target, duration_seconds):
            assert duration_seconds <= 60
            yield "owner"

        @contextmanager
        def connection(self, *args):
            if fail_connection:
                raise TimeoutError("connecting")
            yield 205

        def receive(self, **kwargs):
            # A target-version packet was queued on the transfer client's old socket.
            if self.index == 0:
                return ClientNotificationEpacketReceived(announcement())
            message = messages.pop(0) if messages else None
            return message() if callable(message) else message

        def control_request(self, method, parameters):
            renewals.append(method)
            if renew_error is not None:
                raise renew_error
            return {}

        def close(self):
            closed.append(self.index)

    class Rpc:
        def __init__(self, *args):
            pass

        def set_timeout(self, value):
            pass

        def run_standard_cmd(self, command, *args):
            if command == defs.application_info.COMMAND_ID:
                if drops[0]:
                    # RpcClient raises this when the device's connection drops
                    drops[0] -= 1
                    raise ConnectionAbortedError
                return SimpleNamespace(return_code=0), {"application_id": application, "version": current}
            return SimpleNamespace(return_code=0), {}

        def run_data_send_cmd(self, command, auth, request, payload, progress, decoder):
            params = defs.file_write_basic.request.from_buffer_copy(request)
            expected_action = (
                defs.rpc_enum_file_action.APP_CPATCH
                if entry["method"] == "patch"
                else defs.rpc_enum_file_action.APP_IMG
            )
            assert bytes(params) == bytes(defs.file_write_basic.request(expected_action, binascii.crc32(payload)))
            sent.append(payload)
            progress(len(payload))
            if acknowledgement == "disconnect":
                raise ConnectionAbortedError
            if acknowledgement == "missing":
                return None, None
            return SimpleNamespace(return_code=0), SimpleNamespace(
                recv_len=len(payload),
                recv_crc=binascii.crc32(payload) ^ (1 if acknowledgement == "wrong" else 0),
            )

    monkeypatch.setattr("infuse_iot.services.firmware.LocalClient", Client)
    monkeypatch.setattr("infuse_iot.services.firmware.RpcClient", Rpc)
    return SimpleNamespace(sent=sent, clients=clients, closed=closed, renewals=renewals)


@pytest.mark.parametrize("acknowledgement", ["valid", "missing", "disconnect"])
def test_fresh_version_verifies_even_when_transfer_ack_is_lost(release, tmp_path, monkeypatch, acknowledgement):
    service = service_for(release, tmp_path)
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    entry = plan["devices"][0]
    messages = [
        ClientNotificationEpacketReceived(announcement(TARGET, device=DEVICE + 1)),
        ClientNotificationEpacketReceived(announcement(PREVIOUS)),
        ClientNotificationEpacketReceived(announcement()),
    ]
    transport = fake_transport(monkeypatch, entry, messages, acknowledgement)
    result = service.transfer(entry, plan["package"], Context(), verification_seconds=0.02)
    assert result["status"] == "version_verified"
    assert result["transfer_verified"] == (acknowledgement == "valid")
    assert transport.sent == [release.patch] and len(transport.clients) == 2 and sorted(transport.closed) == [0, 1]


def test_queued_old_socket_announcement_cannot_verify_transfer(release, tmp_path, monkeypatch):
    service = service_for(release, tmp_path)
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    transport = fake_transport(monkeypatch, plan["devices"][0], [])
    result = service.transfer(plan["devices"][0], plan["package"], Context(), verification_seconds=0.001)
    assert result["status"] == "unknown" and result["reason"] == "verification_timeout"
    assert len(transport.sent) == 1


@pytest.mark.parametrize(
    "case,code", [("crc", "outcome_unknown"), ("version", "precondition_changed"), ("connection", "connection_timeout")]
)
def test_crc_preconditions_and_connection_errors(release, tmp_path, monkeypatch, case, code):
    service = service_for(release, tmp_path)
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    transport = fake_transport(
        monkeypatch,
        plan["devices"][0],
        [],
        acknowledgement="wrong" if case == "crc" else "valid",
        current=OLD if case == "version" else PREVIOUS,
        fail_connection=case == "connection",
    )
    context = Context()
    with pytest.raises(DeviceError) as error:
        service.transfer(plan["devices"][0], plan["package"], context, verification_seconds=0.001)
    assert error.value.code == code
    assert len(transport.sent) == (1 if case == "crc" else 0)
    # Precondition failures happen before the job is marked as sending to the device
    assert context.sent == (case == "crc")
    assert transport.closed == [0]


def test_job_is_marked_sending_just_before_the_first_device_write(release, tmp_path, monkeypatch):
    service = service_for(release, tmp_path)
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    fake_transport(monkeypatch, plan["devices"][0], [ClientNotificationEpacketReceived(announcement())])
    events = []
    rpc = service._rpc

    def recorded(client, definition, request):
        events.append(definition.NAME)
        return rpc(client, definition, request)

    monkeypatch.setattr(service, "_rpc", recorded)
    context = Context()
    monkeypatch.setattr(context, "sending", lambda: events.append("sending"))
    assert service.transfer(plan["devices"][0], plan["package"], context, 0.5)["status"] == "version_verified"
    # Setting the time is the first change the device sees
    assert events == ["application_info", "sending", "time_set"]


def test_uncertain_transfer_is_checkpointed_and_never_retried(release, tmp_path, monkeypatch):
    service = service_for(release, tmp_path)
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    transfer = Mock(side_effect=DeviceError("outcome_unknown", "connection lost after write"))
    monkeypatch.setattr(service, "transfer", transfer)
    context = Context()
    with pytest.raises(DeviceError) as error:
        service.run({"plan_id": plan["plan_id"]}, context)
    assert error.value.code == "outcome_unknown"
    assert transfer.call_count == 1
    assert context.results[-1]["devices"][0]["status"] == "unknown"


def test_safe_connection_failures_retry_and_cancellation_prevents_write(release, tmp_path, monkeypatch):
    service = service_for(release, tmp_path)
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    transfer = Mock(side_effect=[DeviceError("connection_failed", "busy", True), {"status": "version_verified"}])
    monkeypatch.setattr(service, "transfer", transfer)
    monkeypatch.setattr("infuse_iot.services.firmware.time.sleep", lambda _: None)
    assert service.run({"plan_id": plan["plan_id"]}, Context())["success"]
    assert transfer.call_count == 2
    context = Context()
    context.cancelled = True
    with pytest.raises(JobCancelled):
        service.run({"plan_id": plan["plan_id"]}, context)
    assert transfer.call_count == 2


@pytest.mark.parametrize("busy,status", [(8, "version_verified"), (30, "failed")])
def test_gateway_busy_before_write_is_retried_for_a_bounded_time(release, tmp_path, monkeypatch, busy, status):
    service = service_for(release, tmp_path)
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    outcomes: list = [DeviceError("device_busy", "busy", True)] * busy + [{"status": "version_verified"}]
    transfer = Mock(side_effect=outcomes)
    monkeypatch.setattr(service, "transfer", transfer)
    clock = iter(range(0, 100000))
    monkeypatch.setattr(
        "infuse_iot.services.firmware.time",
        SimpleNamespace(time=time.time, monotonic=lambda: 2 * next(clock), sleep=lambda _: None),
    )
    context = Context()
    if status == "failed":
        with pytest.raises(DeviceError, match="failed"):
            service.run({"plan_id": plan["plan_id"]}, context)
        assert context.results[-1]["devices"][0]["reason"] == "device_busy" and transfer.call_count < busy
    else:
        assert service.run({"plan_id": plan["plan_id"]}, context)["success"] and transfer.call_count == busy + 1


def test_full_image_uses_exact_approved_signed_bytes(release, tmp_path, monkeypatch):
    service = service_for(release, tmp_path, (OLD,))
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"], device_boards={f"0x{DEVICE:016x}": "sr2202/nrf52840"})
    transport = fake_transport(
        monkeypatch, plan["devices"][0], [ClientNotificationEpacketReceived(announcement())], current=OLD
    )
    result = service.transfer(plan["devices"][0], plan["package"], Context(), verification_seconds=0.02)
    assert result["status"] == "version_verified" and transport.sent == [release.image]


@pytest.mark.parametrize(
    "listing,error",
    [
        ("Path = ../manifest.yaml\nSize = 1", "Unsafe"),
        ("Path = manifest.yaml\nSize = 200000000", "expansion limits"),
        ("Path = manifest.yaml\nSize = 1\n\nPath = manifest.yaml\nSize = 1", "Duplicate"),
    ],
)
def test_archive_rejects_unsafe_members_before_reading(release, tmp_path, monkeypatch, listing, error):
    archive = tmp_path / "release.7z"
    archive.write_bytes(b"placeholder")
    monkeypatch.setattr("infuse_iot.services.release_package.shutil.which", lambda _: "7zz")
    extract = Mock(return_value=listing.encode())
    monkeypatch.setattr("infuse_iot.services.release_package._extract_output", extract)
    with pytest.raises(ValueError, match=error):
        inspect_release(archive, tmp_path / "cache")
    assert extract.call_count == 1  # Listing only: no member can be read.


def test_archive_without_extractor_has_actionable_failure(tmp_path, monkeypatch):
    archive = tmp_path / "release.7z"
    archive.write_bytes(b"placeholder")
    monkeypatch.setattr("infuse_iot.services.release_package.shutil.which", lambda _: None)
    with pytest.raises(ValueError, match="missing_extractor"):
        inspect_release(archive, tmp_path / "cache")


def observed(value=PREVIOUS, device=DEVICE, application=APP, board=None, rssi=-65):
    route = announcement(value, device, application, board).route[0]
    route.rssi = rssi
    return route, announce_reading(value, application, board)


def run_cli(release, tmp_path, monkeypatch, batches, *arguments, capabilities=None, transfer=None):
    import argparse
    from unittest.mock import MagicMock

    from infuse_iot.tools.ota_upgrade import SubCommand

    client = MagicMock()
    client.capabilities.return_value = capabilities or {"protocol_version": 2, "gateway_kind": "native_bt"}
    # One batch per subscription: the CLI resubscribes after each transfer.
    client.observe_announce.side_effect = [iter(batch) for batch in batches]
    monkeypatch.setattr("infuse_iot.tools.ota_upgrade.LocalClient", Mock(return_value=client))
    cache = str(tmp_path / "cli-cache")
    monkeypatch.setattr("infuse_iot.tools.ota_upgrade.platformdirs.user_cache_dir", lambda *args: cache)
    if transfer is not None:
        monkeypatch.setattr("infuse_iot.tools.ota_upgrade.FirmwareService.transfer", transfer)
    parser = argparse.ArgumentParser()
    SubCommand.add_parser(parser)
    log = tmp_path / "updates.csv"
    command = SubCommand(parser.parse_args(["--release", str(release.root), "--log", str(log), *arguments]))
    command.run()
    rows = [line.split(",")[3:] for line in log.read_text().splitlines()] if log.exists() else []
    return SimpleNamespace(command=command, client=client, rows=rows)


def test_cli_plans_from_announcements_and_verifies_later_announcement(release, tmp_path, monkeypatch):
    transport = fake_transport(monkeypatch, {"method": "patch"}, [])
    result = run_cli(
        release,
        tmp_path,
        monkeypatch,
        [[observed(PREVIOUS)], [observed(PREVIOUS), observed(TARGET)]],
        "--id",
        f"0x{DEVICE:016x}",
    )
    assert transport.sent == [release.patch]
    assert result.command._updated == 1 and result.rows == [[TARGET, "upgraded"]]
    # Native Bluetooth has no gateway device to set the time on.
    result.client.connection.assert_not_called()
    assert not (tmp_path / "cli-cache" / "plans").exists()


@pytest.mark.parametrize(
    "current,board,arguments,expected",
    [
        ("2.0.0+deadbeef", "sr2202/nrf52840", [], "downgrade"),
        (OLD, None, [], "no_diff"),
        (OLD, None, ["--full-image"], "board_unknown_for_full_image"),
        ("2.0.0+deadbeef", "sr2202/nrf52840", ["--allow-downgrade"], "no_diff"),
        ("2.0.0+deadbeef", "sr2202/nrf52840", ["--allow-downgrade", "--full-image"], "full_image"),
        (OLD, None, ["--full-image", "--board", "sr2202/nrf52840", "--id", f"0x{DEVICE:016x}"], "full_image"),
    ],
)
def test_cli_only_writes_patches_unless_full_images_and_downgrades_allowed(
    release, tmp_path, monkeypatch, current, board, arguments, expected
):
    transfer = Mock(return_value={"device_id": f"0x{DEVICE:016x}", "status": "transferred"})
    batches = [[observed(current, board=board)], [observed(TARGET)]]
    result = run_cli(release, tmp_path, monkeypatch, batches, *arguments, transfer=transfer)
    if expected == "full_image":
        assert transfer.call_args.args[0]["method"] == "full_image" and result.command._updated == 1
    else:
        transfer.assert_not_called()
        if expected == "no_diff":
            assert result.command._no_diff == 1 and result.command._missing_diffs == {current}
        else:
            assert result.command._skipped == {f"0x{DEVICE:016x}: {expected}"}


def test_cli_retries_connections_and_logs_failures_with_observed_versions(release, tmp_path, monkeypatch):
    other = DEVICE + 1
    transfer = Mock(
        side_effect=[
            DeviceError("connection_failed", "busy", True),
            {"status": "transferred"},
            DeviceError("rpc_rejected", "rejected"),
        ]
    )
    clock = iter(range(0, 100000, 100))
    monkeypatch.setattr("infuse_iot.tools.ota_upgrade.time", SimpleNamespace(time=lambda: next(clock)))
    batches = [
        [observed(PREVIOUS), observed(PREVIOUS)],
        [observed(PREVIOUS, device=other), observed(PREVIOUS)],
    ]
    result = run_cli(release, tmp_path, monkeypatch, batches, transfer=transfer)
    assert transfer.call_count == 3
    # The verification window passed without the new version, and the second device rejected its write.
    # Rows keep the five CSV columns, and the summary shows why each device failed.
    assert result.rows == [[PREVIOUS, "failed"], [PREVIOUS, "failed"]]
    assert result.command._failures == {f"0x{other:016x}": "rpc_rejected", f"0x{DEVICE:016x}": "verification_timeout"}
    assert result.command._failed == 2


def test_cli_release_and_gateway_errors_exit_cleanly(release, tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from infuse_iot.common import InfuseID

    client = MagicMock()
    client.capabilities.side_effect = TimeoutError
    monkeypatch.setattr("infuse_iot.tools.ota_upgrade.LocalClient", Mock(return_value=client))
    monkeypatch.setattr("infuse_iot.tools.ota_upgrade.platformdirs.user_cache_dir", lambda *args: str(tmp_path))
    import argparse

    from infuse_iot.tools.ota_upgrade import SubCommand

    parser = argparse.ArgumentParser()
    SubCommand.add_parser(parser)
    command = SubCommand(parser.parse_args(["--release", str(release.root)]))
    with pytest.raises(SystemExit, match="No communications gateway detected"):
        command.run()
    # Protocol v1 gateways do not report a kind, but still have their time set.
    set_time = Mock(return_value=True)
    monkeypatch.setattr(SubCommand, "set_device_time", set_time)
    run_cli(release, tmp_path, monkeypatch, [[]], capabilities={"protocol_version": 1, "features": []})
    assert set_time.call_args.args[1] == InfuseID.GATEWAY
    release.image_path.unlink()
    with pytest.raises(SystemExit, match="exactly one OTA image"):
        run_cli(release, tmp_path, monkeypatch, [[]])
    with pytest.raises(argparse.ArgumentTypeError, match="--board"):
        SubCommand(parser.parse_args(["--release", str(release.root), "--board", "sr2202/nrf52840"]))


def test_cli_migrates_explicit_devices_with_application_diffs(release, tmp_path, monkeypatch):
    other_application, other_version = APP + 1, "1.0.0+0000abcd"
    folder = release.root / "diffs" / f"0x{other_application:08x}"
    folder.mkdir()
    patch = cpatch.generate(b"other application" * 12, release.image, False)
    (folder / f"{other_version}.bin").write_bytes(patch)
    transport = fake_transport(
        monkeypatch, {"method": "patch"}, [], current=other_version, application=other_application
    )
    batches = [[observed(other_version, application=other_application)], [observed(TARGET)]]
    result = run_cli(release, tmp_path, monkeypatch, batches, "--id", f"0x{DEVICE:016x}")
    assert transport.sent == [patch] and result.rows == [[TARGET, "upgraded"]]
    # Scanning by application never selects another application's devices.
    run_cli(release, tmp_path, monkeypatch, batches[:1])
    assert transport.sent == [patch]


def test_cancel_after_last_bytes_verifies_current_device_and_stops_next(release, tmp_path, monkeypatch):
    service = service_for(release, tmp_path, (PREVIOUS, PREVIOUS))
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}", f"0x{DEVICE + 1:016x}"])
    transport = fake_transport(monkeypatch, plan["devices"][0], [ClientNotificationEpacketReceived(announcement())])
    context = Context()

    def progress(phase, **values):
        context.phases.append((phase, values))
        if values.get("cancellation_deferred"):
            context.cancelled = True

    monkeypatch.setattr(context, "progress", Mock(side_effect=progress))
    with pytest.raises(JobCancelled):
        service.run({"plan_id": plan["plan_id"]}, context)
    assert len(transport.sent) == 1
    assert context.results[-1]["devices"][0]["status"] == "version_verified"
    assert len(context.results[-1]["devices"]) == 1


def test_already_current_read_retries_gateway_teardown_without_writing(release, tmp_path, monkeypatch):
    service = service_for(release, tmp_path, (TARGET,))
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    read = Mock(
        side_effect=[
            DeviceError("device_busy", "A released link is closing", True),
            {
                "response": {"version": TARGET, "application_id": APP},
                "observed_at": time.time(),
            },
        ]
    )
    transfer = Mock()
    monkeypatch.setattr(service.operations, "read", read)
    monkeypatch.setattr(service, "transfer", transfer)
    monkeypatch.setattr("infuse_iot.services.firmware.time.sleep", lambda _: None)
    result = service.run({"plan_id": plan["plan_id"]}, Context())
    assert result["success"] and read.call_count == 2
    assert result["devices"][0]["status"] == "already_current"
    transfer.assert_not_called()


def poll_job(jobs, job_id):
    for _ in range(200):
        status = jobs.status(job_id)
        if status["state"] not in ("queued", "running"):
            return status
        time.sleep(0.02)
    raise AssertionError("Job did not finish")


@pytest.mark.parametrize(
    "current,allow,status,relation",
    [
        ("2.0.0+deadbeef", False, "blocked", "downgrade"),
        ("2.0.0+deadbeef", True, "ready", "downgrade"),
        ("1.3.1+00000001", False, "ready", "rebuild"),
        (OLD, False, "ready", "upgrade"),
    ],
)
def test_plan_blocks_downgrades_unless_allowed(release, tmp_path, current, allow, status, relation):
    service = service_for(release, tmp_path, ())
    service.state.observe(announcement(current, board="sr2202/nrf52840"))
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"], allow_downgrade=allow)
    entry = plan["devices"][0]
    assert (entry["status"], entry["version_relation"]) == (status, relation)
    assert entry.get("method", entry["reason"]) == ("downgrade" if status == "blocked" else "full_image")
    if status == "blocked":
        with pytest.raises(DeviceError) as error:
            service.validate_start(plan["plan_id"])
        assert error.value.code == "plan_blocked"


def test_full_images_need_per_device_board_evidence(release, tmp_path):
    service = service_for(release, tmp_path, (OLD,))
    service.state.observe(announcement(OLD, DEVICE + 1, board="other/board"))
    service.state.observe(announcement(OLD, DEVICE + 2, board="sr2202/nrf52840"))
    ids = [f"0x{DEVICE + index:016x}" for index in range(3)]
    unasserted = service.plan(str(release.root), ids)["devices"]
    assert [row["reason"].split(";")[0] for row in unasserted[:2]] == ["board_unknown_for_full_image", "board_mismatch"]
    assert unasserted[2]["board_evidence"] == "announcement_crc" and unasserted[2]["method"] == "full_image"
    asserted = service.plan(str(release.root), ids[:1], device_boards={ids[0]: "sr2202/nrf52840"})
    assert asserted["devices"][0]["board_evidence"] == "caller_assertion"
    assert asserted["devices"][0]["asserted_board"] == "sr2202/nrf52840"
    assert asserted["device_boards"] == {ids[0]: "sr2202/nrf52840"}
    wrong = service.plan(str(release.root), ids, device_boards={ids[0]: "other/board", ids[2]: "other/board"})
    assert [row["reason"] for row in wrong["devices"][::2]] == ["board_mismatch", "board_mismatch"]
    with pytest.raises(ValueError, match="device_boards"):
        service.plan(str(release.root), ids[:1], device_boards={f"0x{DEVICE + 9:016x}": "sr2202/nrf52840"})


def test_cancel_after_uncertain_outcome_reports_outcome_unknown(release, tmp_path, monkeypatch):
    from infuse_iot.services.jobs import JobManager

    service = service_for(release, tmp_path, (PREVIOUS, PREVIOUS))
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}", f"0x{DEVICE + 1:016x}"])
    jobs = JobManager(tmp_path / "jobs")

    def transfer(entry, package, context, seconds):
        context.progress("awaiting_ack", device_id=entry["device_id"], cancellation_deferred=True)
        jobs.cancel(context.job_id)
        return {"device_id": entry["device_id"], "status": "unknown", "reason": "verification_timeout"}

    monkeypatch.setattr(service, "transfer", Mock(side_effect=transfer))
    jobs.handlers["firmware_update"] = service.run
    try:
        status = poll_job(jobs, jobs.submit("update", {"action": "firmware_update", "plan_id": plan["plan_id"]})["id"])
    finally:
        jobs.close()
    assert status["state"] == "unknown" and status["error"]["code"] == "outcome_unknown"
    assert [row["status"] for row in status["result"]["devices"]] == ["unknown"]
    assert service.transfer.call_count == 1


def test_cancelling_after_a_write_leaves_the_job_unknown_with_its_results(release, tmp_path, monkeypatch):
    from infuse_iot.services.jobs import JobManager

    service = service_for(release, tmp_path, (PREVIOUS, PREVIOUS))
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}", f"0x{DEVICE + 1:016x}"])
    jobs = JobManager(tmp_path / "jobs")

    def transfer(entry, package, context, seconds):
        context.sending()
        jobs.cancel(context.job_id)
        return {"device_id": entry["device_id"], "status": "version_verified"}

    monkeypatch.setattr(service, "transfer", Mock(side_effect=transfer))
    jobs.handlers["firmware_update"] = service.run
    try:
        status = poll_job(jobs, jobs.submit("update", {"action": "firmware_update", "plan_id": plan["plan_id"]})["id"])
    finally:
        jobs.close()
    # The first device was written, so the job cannot report that nothing was sent.
    assert (status["state"], status["error"]["code"]) == ("unknown", "interrupted")
    assert status["error"]["message"].startswith("Cancelled")
    assert [row["status"] for row in status["result"]["devices"]] == ["version_verified"]
    assert service.transfer.call_count == 1


def test_missing_and_expired_plans_fail_before_device_contact(release, tmp_path, monkeypatch):
    from infuse_iot.services.jobs import JobManager

    service = service_for(release, tmp_path)
    with pytest.raises(DeviceError) as error:
        service.validate_start("0" * 64)
    assert error.value.code == "plan_not_found" and str(tmp_path) not in error.value.message
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    service.validate_start(plan["plan_id"])
    transfer = Mock()
    monkeypatch.setattr(service, "transfer", transfer)
    real = time.time
    # The job waits in the queue until its plan has expired.
    monkeypatch.setattr(
        "infuse_iot.services.firmware.time", SimpleNamespace(time=lambda: real() + 16 * 60, monotonic=time.monotonic)
    )
    jobs = JobManager(tmp_path / "jobs")
    jobs.handlers["firmware_update"] = service.run
    try:
        status = poll_job(jobs, jobs.submit("update", {"action": "firmware_update", "plan_id": plan["plan_id"]})["id"])
    finally:
        jobs.close()
    assert status["state"] == "failed" and status["error"]["code"] == "plan_expired"
    transfer.assert_not_called()


def test_disconnect_before_write_is_retried(release, tmp_path, monkeypatch):
    service = service_for(release, tmp_path)
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    entry = plan["devices"][0]
    transport = fake_transport(monkeypatch, entry, [], drop_preconditions=1)
    with pytest.raises(DeviceError) as error:
        service.transfer(entry, plan["package"], Context(), verification_seconds=0.001)
    assert (error.value.code, error.value.retryable, transport.sent) == ("connection_dropped", True, [])
    transport = fake_transport(
        monkeypatch, entry, [ClientNotificationEpacketReceived(announcement())], drop_preconditions=1
    )
    monkeypatch.setattr("infuse_iot.services.firmware.time.sleep", lambda _: None)
    result = service.run({"plan_id": plan["plan_id"]}, Context())
    assert result["devices"][0]["status"] == "version_verified" and transport.sent == [release.patch]


@pytest.mark.parametrize(
    "renew_error,lost", [(None, False), (GatewayControlError("operation_expired"), True), (TimeoutError(), False)]
)
def test_ownership_renewal_failure_keeps_verifying(release, tmp_path, monkeypatch, renew_error, lost):
    service = service_for(release, tmp_path)
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    messages: list = [None] * 6 + [ClientNotificationEpacketReceived(announcement())]
    transport = fake_transport(monkeypatch, plan["devices"][0], messages, renew_error=renew_error)
    clock = iter(range(0, 100000, 7))
    monkeypatch.setattr(
        "infuse_iot.services.firmware.time", SimpleNamespace(time=time.time, monotonic=lambda: next(clock))
    )
    result = service.transfer(plan["devices"][0], plan["package"], Context(), verification_seconds=180)
    assert result["status"] == "version_verified" and result["ownership_lost"] is lost
    # Renewed well inside the 60 second lease until the gateway reports it lost.
    assert set(transport.renewals) == {"renew_operation"}
    assert len(transport.renewals) == 1 if lost else len(transport.renewals) >= 5


def test_in_process_lock_covers_transfer_but_not_verification(release, tmp_path, monkeypatch):
    service = service_for(release, tmp_path)
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    held = []
    messages = [
        lambda: held.append(service.operations.lock.locked()),
        ClientNotificationEpacketReceived(announcement()),
    ]
    fake_transport(monkeypatch, plan["devices"][0], messages)
    context = Context()
    monkeypatch.setattr(
        context, "progress", lambda phase, **values: held.append((phase, service.operations.lock.locked()))
    )
    assert service.transfer(plan["devices"][0], plan["package"], context, 0.5)["status"] == "version_verified"
    assert ("transferring", True) in held and ("awaiting_reboot", False) in held and False in held


def test_release_selects_cloud_ota_image_and_checks_diffs_against_it(release, tmp_path):
    package = inspect_release(release.root, tmp_path / "cache")
    assert package["image"]["file"] == "logger/zephyr/zephyr.signed.bin"
    tfm = release.image_path.with_name("tfm_s_zephyr_ns_signed.bin")
    release.image_path.rename(tfm)
    assert (
        inspect_release(release.root, tmp_path / "cache")["image"]["file"] == tfm.relative_to(release.root).as_posix()
    )
    ota = release.root / "ota-logger-sr2202_nrf52840-1.3.1+7bee09d5.bin"
    ota.write_bytes(release.image)
    package = inspect_release(release.root, tmp_path / "cache")
    assert package["image"]["file"] == ota.name and PREVIOUS in package["patches"]
    # Diffs are generated against the OTA image, so they must construct the selected one.
    ota.write_bytes(signed_image(release.private, b"another application" * 8))
    with pytest.raises(ValueError, match=re.escape(f"diffs/{PREVIOUS}.bin: Patch header output does not match")):
        inspect_release(release.root, tmp_path / "cache")
    ota.with_name("ota-second.bin").write_bytes(release.image)
    with pytest.raises(ValueError, match="exactly one OTA image"):
        inspect_release(release.root, tmp_path / "cache")
    ota.unlink()
    ota.with_name("ota-second.bin").unlink()
    tfm.unlink()
    with pytest.raises(ValueError, match="exactly one OTA image"):
        inspect_release(release.root, tmp_path / "cache")


def test_release_ignores_stray_diff_files_and_indexes_migrations(release, tmp_path):
    (release.root / "diffs" / f"._{PREVIOUS}.bin").write_bytes(b"\x00\x05\x16\x07 AppleDouble")
    (release.root / "diffs" / "notes.bin").write_bytes(b"notes")
    migration = release.root / "diffs" / "0xCE710004" / "1.0.0+0000abcd.bin"
    migration.parent.mkdir()
    migration.write_bytes(cpatch.generate(b"other application" * 12, release.image, False))
    package = inspect_release(release.root, tmp_path / "cache")
    assert list(package["patches"]) == [PREVIOUS]
    assert list(package["migration_patches"]) == ["0xce710004"]
    assert sorted(package["ignored_files"]) == [f"diffs/._{PREVIOUS}.bin", "diffs/notes.bin"]
    service = service_for(release, tmp_path, ())
    service.state.observe(announcement("1.0.0+0000abcd", application=0xCE710004))
    identifier = f"0x{DEVICE:016x}"
    assert service.plan(str(release.root), [identifier])["devices"][0]["reason"] == "application_mismatch"
    entry = service.plan(str(release.root), [identifier], allow_application_change=True)["devices"][0]
    assert (entry["status"], entry["method"], entry["version_relation"]) == ("ready", "patch", "application_change")
    assert entry["image"]["file"] == "diffs/0xCE710004/1.0.0+0000abcd.bin"


def test_real_7z_archive_extraction(release, tmp_path):
    import shutil
    import subprocess

    executable = shutil.which("7zz") or shutil.which("7z") or shutil.which("7za")
    if executable is None:
        pytest.skip("7-Zip is not installed")
    archive = tmp_path / "release.7z"
    subprocess.run(
        [executable, "a", "-bd", "-y", str(archive), "release"], cwd=tmp_path, check=True, capture_output=True
    )
    package = inspect_release(archive, tmp_path / "cache", release.public)
    assert package["image"]["signature_status"] == "verified"
    assert package["patches"][PREVIOUS]["sha256"] == hashlib.sha256(release.patch).hexdigest()
    staged = Path(package["staged_directory"])
    assert (staged / package["image"]["file"]).read_bytes() == release.image


def test_archive_runtime_is_bounded_across_members():
    from infuse_iot.services.release_package import _extract_output

    with pytest.raises(ValueError, match="time limit"):
        _extract_output(["7zz", "l"], 1024, time.monotonic() - 1)


def test_transfer_keeps_its_staged_package_from_pruning(release, tmp_path, monkeypatch):
    import os

    from infuse_iot.services.release_package import DIGEST, prune_cache

    service = service_for(release, tmp_path)
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    entry, staged = plan["devices"][0], Path(plan["package"]["staged_directory"])
    # A long job reaches a later device after its package would otherwise expire.
    old = time.time() - 2 * 86400
    os.utime(staged, (old, old))
    fake_transport(monkeypatch, entry, [ClientNotificationEpacketReceived(announcement())])
    result = service.transfer(entry, plan["package"], Context(), verification_seconds=0.02)
    assert result["status"] == "version_verified"
    # Inspecting another release prunes the cache, keeping packages in use.
    prune_cache(staged.parent, DIGEST, None, 16)
    assert staged.is_dir()


def test_package_and_plan_caches_are_pruned(release, tmp_path):
    import os

    service = service_for(release, tmp_path)
    stale_package = service.cache / "packages" / ("a" * 64)
    stale_plan = service.cache / "plans" / f"{'b' * 64}.json"
    for path in (stale_package / "manifest.yaml", stale_plan):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
    old = time.time() - 2 * 86400
    os.utime(stale_package, (old, old))
    os.utime(stale_plan, (old, old))
    plan = service.plan(str(release.root), [f"0x{DEVICE:016x}"])
    assert not stale_package.exists() and not stale_plan.exists()
    assert Path(plan["package"]["staged_directory"]).is_dir()
    assert service.load_plan(plan["plan_id"]) == plan
