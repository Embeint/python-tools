import time
from types import SimpleNamespace
from unittest.mock import Mock

from rich.console import Console

from infuse_iot.common import InfuseType
from infuse_iot.definitions.tdf import readings
from infuse_iot.socket_comms import (
    ClientNotification,
    ClientNotificationCommsCheck,
    ClientNotificationEpacketReceived,
    ClientNotificationObservedDevices,
    GatewayRequestObservedDevices,
)
from infuse_iot.tools.version_table import SubCommand, VersionTable, format_age, version_sort_key


def announce(application: int, major: int, minor: int, revision: int, build_num: int) -> readings.announce_v2:
    a = readings.announce_v2()
    a.application = application
    a.version.major = major
    a.version.minor = minor
    a.version.revision = revision
    a.version.build_num = build_num
    return a


def epacket(table: VersionTable, infuse_id: int, *tdfs, ptype=InfuseType.TDF) -> ClientNotificationEpacketReceived:
    """Packet notification from a device, with the table decoding it to `tdfs`"""
    table._decoder = Mock()
    table._decoder.decode.return_value = [SimpleNamespace(data=[t]) for t in tdfs]
    pkt = SimpleNamespace(route=[SimpleNamespace(infuse_id=infuse_id)], ptype=ptype, payload=b"")
    return ClientNotificationEpacketReceived(pkt)  # type: ignore[arg-type]


def render(table: VersionTable, now: float) -> str:
    console = Console(width=200, record=True)
    console.print(table.render(now))
    return console.export_text()


def known(devices: dict[int, dict]) -> ClientNotificationObservedDevices:
    # Pass through the JSON encoding used between the gateway and clients
    notification = ClientNotification.from_json(ClientNotificationObservedDevices(devices).to_json())
    assert isinstance(notification, ClientNotificationObservedDevices)
    return notification


def test_known_devices_populate_table():
    table = VersionTable()
    table.handle(
        known(
            {
                1: {
                    "network_id": 5,
                    "last_heard": 100.0,
                    "gateway": True,
                    "application_id": 0x10,
                    "application_version": "1.0.0+00000001",
                },
                2: {"network_id": 5, "last_heard": 90.0},
                3: {"last_heard": 95.0, "application_id": 0x20, "application_version": "2.1.0+000000ff"},
            }
        ),
        110.0,
    )

    # Devices without an announced application are not displayed
    assert set(table.devices) == {1, 3}
    assert table.devices[3].application_id == 0x20
    assert table.devices[3].application_version == "2.1.0+000000ff"
    assert table.devices[3].last_heard == 95.0

    output = render(table, 110.0)
    assert "Observed Devices (2)" in output
    assert "0x00000010" in output
    assert "2.1.0+000000ff" in output
    assert "10s ago" in output
    assert "15s ago" in output


def test_announce_adds_and_updates_devices():
    table = VersionTable()
    table.handle(epacket(table, 5, announce(0x30, 1, 2, 3, 0xABCD)), 50.0)
    assert table.devices[5].application_id == 0x30
    assert table.devices[5].application_version == "1.2.3+0000abcd"
    assert table.devices[5].last_heard == 50.0

    # Upgraded application version
    table.handle(epacket(table, 5, announce(0x30, 1, 3, 0, 1)), 60.0)
    assert table.devices[5].application_version == "1.3.0+00000001"

    # Other packets only refresh the last heard time
    table.handle(epacket(table, 5, ptype=InfuseType.RPC_RSP), 70.0)
    assert table.devices[5].application_version == "1.3.0+00000001"
    assert table.devices[5].last_heard == 70.0

    # Unrelated TDFs and devices without an announced application are ignored
    table.handle(epacket(table, 6, readings.battery_state()), 80.0)
    assert 6 not in table.devices


def test_stale_known_devices_do_not_regress_last_heard():
    table = VersionTable()
    table.handle(epacket(table, 5, announce(0x30, 1, 2, 3, 0)), 200.0)
    table.handle(
        known({5: {"last_heard": 150.0, "application_id": 0x30, "application_version": "1.2.3+00000000"}}), 210.0
    )
    assert table.devices[5].last_heard == 200.0


def test_application_filter():
    table = VersionTable([0x30])
    table.handle(epacket(table, 5, announce(0x30, 1, 0, 0, 0)), 10.0)
    table.handle(epacket(table, 6, announce(0x40, 1, 0, 0, 0)), 10.0)
    table.handle(known({7: {"application_id": 0x40, "application_version": "1.0.0+00000000"}}), 10.0)
    assert set(table.devices) == {5}

    # Device moving to a filtered application is removed
    table.handle(epacket(table, 5, announce(0x40, 1, 0, 0, 0)), 20.0)
    assert table.devices == {}


def test_other_notifications_ignored():
    table = VersionTable()
    table.handle(None, 10.0)
    table.handle(ClientNotificationCommsCheck(), 10.0)
    assert table.devices == {}


def rows(table: VersionTable, now: float) -> list[list[str]]:
    """Cell values of each rendered table row"""
    columns = [list(c.cells) for c in table.render(now).columns]
    return [list(r) for r in zip(*columns, strict=True)]


def test_rows_count_devices_per_version():
    table = VersionTable()
    table.handle(epacket(table, 1, announce(0x10, 1, 0, 0, 0)), 10.0)
    table.handle(epacket(table, 2, announce(0x10, 1, 0, 0, 0)), 20.0)
    table.handle(epacket(table, 3, announce(0x10, 1, 0, 0, 0)), 15.0)
    table.handle(epacket(table, 4, announce(0x10, 1, 1, 0, 0)), 25.0)
    table.handle(epacket(table, 5, announce(0x20, 1, 0, 0, 0)), 30.0)
    table.handle(known({6: {"application_id": 0x20, "application_version": "1.0.0+00000000"}}), 30.0)

    # Last heard is the most recent device of each version
    assert rows(table, 30.0) == [
        ["0x00000010", "1.0.0+00000000", "3", "10s ago"],
        ["0x00000010", "1.1.0+00000000", "1", "5s ago"],
        ["0x00000020", "1.0.0+00000000", "2", "0s ago"],
    ]
    assert "Observed Devices (6)" in render(table, 30.0)

    # Upgraded devices move between versions
    table.handle(epacket(table, 1, announce(0x10, 1, 1, 0, 0)), 30.0)
    table.handle(epacket(table, 2, announce(0x10, 1, 1, 0, 0)), 30.0)
    table.handle(epacket(table, 3, announce(0x10, 1, 1, 0, 0)), 30.0)
    assert rows(table, 30.0) == [
        ["0x00000010", "1.1.0+00000000", "4", "0s ago"],
        ["0x00000020", "1.0.0+00000000", "2", "0s ago"],
    ]


def test_rows_sorted_by_application_and_version():
    table = VersionTable()
    table.handle(epacket(table, 3, announce(0x20, 1, 0, 0, 0)), 10.0)
    table.handle(epacket(table, 2, announce(0x10, 10, 0, 0, 0)), 10.0)
    table.handle(epacket(table, 1, announce(0x10, 2, 0, 0, 0)), 10.0)
    assert [r[:2] for r in rows(table, 10.0)] == [
        ["0x00000010", "2.0.0+00000000"],
        ["0x00000010", "10.0.0+00000000"],
        ["0x00000020", "1.0.0+00000000"],
    ]


def test_version_sort_key():
    assert version_sort_key("2.0.0+00000000") < version_sort_key("10.0.0+00000000")
    assert version_sort_key("1.0.0+00000009") < version_sort_key("1.0.0+0000000a")
    assert version_sort_key("99.0.0+00000000") < version_sort_key("invalid")


def test_format_age():
    assert format_age(None, 100.0) == "Unknown"
    assert format_age(100.0, 100.0) == "0s ago"
    # Clock differences never display negative ages
    assert format_age(105.0, 100.0) == "0s ago"
    assert format_age(0.0, 125.0) == "2m 05s ago"
    assert format_age(0.0, 7500.0) == "2h 05m ago"


def command(*notifications) -> tuple[SubCommand, Mock]:
    """Command with a gateway client that receives `notifications`, then times out"""
    cmd = SubCommand.__new__(SubCommand)
    cmd._table = VersionTable()
    client = Mock()
    cmd._client = client
    pending = list(notifications)

    def receive(timeout=None):
        if pending:
            return pending.pop(0)
        time.sleep(timeout)
        return None

    client.receive.side_effect = receive
    cmd.KNOWN_DEVICES_TIMEOUT = 0.05
    return cmd, client


def test_table_initialised_from_known_devices(capsys):
    devices: dict[int, dict] = {
        1: {"network_id": 5, "gateway": True},
        2: {"last_heard": 100.0, "application_id": 0x10, "application_version": "1.0.0+00000000"},
        3: {"last_heard": 105.0, "application_id": 0x10, "application_version": "1.0.0+00000000"},
    }
    cmd, client = command(ClientNotificationCommsCheck(), known(devices))
    cmd._request_known_devices()

    (request,) = [call.args[0] for call in client.send.call_args_list]
    assert isinstance(request, GatewayRequestObservedDevices)
    assert rows(cmd._table, 110.0) == [["0x00000010", "1.0.0+00000000", "2", "5s ago"]]
    assert capsys.readouterr().err == ""


def test_known_devices_without_applications_warns(capsys):
    # Gateways running older versions of the package only report keys
    cmd, _ = command(known({1: {"network_id": 5, "gateway": True}, 2: {"network_id": 5}}))
    cmd._request_known_devices()
    assert cmd._table.devices == {}
    assert "no application versions" in capsys.readouterr().err


def test_known_devices_no_response_warns(capsys):
    cmd, _ = command()
    cmd._request_known_devices()
    assert cmd._table.devices == {}
    assert "did not report known devices" in capsys.readouterr().err
