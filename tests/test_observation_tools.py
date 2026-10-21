import argparse
import asyncio
import ctypes
import json
import threading
from unittest.mock import Mock

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from infuse_iot.common import InfuseType
from infuse_iot.definitions.tdf import readings, structs
from infuse_iot.epacket import interface
from infuse_iot.epacket.packet import Auth, HopReceived, PacketReceived
from infuse_iot.services.ble_observations import INFUSE_SERVICE
from infuse_iot.services.device_state import DeviceState
from infuse_iot.socket_comms import ClientNotificationEpacketReceived, GatewayControlError, default_multicast_address
from infuse_iot.tdf import TDF
from infuse_iot.tools import scan, snapshot
from infuse_iot.tools.native_bt import SubCommand as NativeBt

DEVICE = 0xCE7E42571A000099


def advertisement(address, name=None, manufacturer=None, services=()):
    data = AdvertisementData(name, manufacturer or {}, {}, list(services), None, -60, ())
    return BLEDevice(address, name, None), data


def packet(reading):
    payload = bytes(TDF.CoreHeader(reading.ID, ctypes.sizeof(reading))) + bytes(reading)
    address = interface.Address(interface.Address.BluetoothLeAddr(0, 0x60FCF1006161))
    hop = HopReceived(DEVICE, interface.ID.BT_ADV, address, Auth.NETWORK, 0xCE7E50, 0, 0, -65)
    return PacketReceived([hop], InfuseType.TDF, payload)


def announce():
    return readings.announce(0xCE710003, structs.tdf_struct_mcuboot_img_sem_ver(1, 3, 1, 0x7BEE09D5), 0, 0, 10, 0, 0)


@pytest.fixture
def native_gateway(loopback_gateway, monkeypatch):
    """A native Bluetooth gateway serving a loopback port, without credentials or an adapter."""
    gateway = loopback_gateway(28881)
    monkeypatch.setattr("infuse_iot.tools.native_bt.LocalServer", lambda _address: gateway.server)
    monkeypatch.setattr("infuse_iot.tools.native_bt.DeviceDatabase", Mock())
    monkeypatch.setattr("infuse_iot.tools.native_bt.Console.init", lambda: None)
    command = NativeBt(argparse.Namespace(root=None, server_sock=gateway.address, report_interval=0))
    return gateway, command


def test_attached_scan_pages_through_gateway_observations(native_gateway):
    gateway, command = native_gateway
    stop = threading.Event()

    def devices():
        # Devices advertising periodically while the gateway scans
        while not stop.wait(0.02):
            command.simple_callback(*advertisement("60:fc:f1:00:61:61", "CT Logger", services=[INFUSE_SERVICE]))
            command.simple_callback(*advertisement("aa:bb:cc:dd:ee:ff"))

    thread = threading.Thread(target=devices)
    thread.start()
    try:
        first = asyncio.run(scan.collect_scan(gateway.address, duration=0.1, limit=1))
    finally:
        stop.set()
        thread.join()
    assert [row["identifier"] for row in first["items"]] == ["60:FC:F1:00:61:61"]
    assert first["gateway"]["instance_id"] == gateway.server.control.instance_id
    assert first["gateway"]["gateway_kind"] == "native_bt"
    # Counters describe the scan window
    assert first["gateway"]["counters"]["unknown_network_packets"] == 0
    assert first["filters"] == {"max_age_seconds": 0.1, "infuse_only": False}
    second = asyncio.run(scan.collect_scan(gateway.address, duration=0.1, cursor=first["next_cursor"], limit=1))
    assert [row["identifier"] for row in second["items"]] == ["AA:BB:CC:DD:EE:FF"]
    assert second["gateway"]["counters"] is None
    with pytest.raises(GatewayControlError) as error:
        asyncio.run(scan.collect_scan(gateway.address, duration=0.1, cursor="deadbeef:1"))
    assert error.value.code == "snapshot_expired"


def test_attached_scan_needs_an_updated_gateway(loopback_gateway):
    gateway = loopback_gateway(28883)
    with pytest.raises(GatewayControlError) as error:
        asyncio.run(scan.collect_scan(gateway.address, duration=0.1))
    assert error.value.code == "unsupported_capability"


def test_attached_scan_without_gateway_exits_cleanly(capsys):
    args = argparse.Namespace(
        server_sock=default_multicast_address(28885), duration=0.1, standalone=False, cursor=None, limit=50, json=True
    )
    with pytest.raises(SystemExit) as exit_info:
        scan.SubCommand(args).run()
    assert str(exit_info.value.code).startswith("gateway_unavailable: ")
    assert capsys.readouterr().out == ""


def test_standalone_scan_reports_addresses(monkeypatch):
    scanners = []

    class FakeScanner:
        def __init__(self, callback, **kwargs):
            self.callback = callback
            self.kwargs = kwargs
            scanners.append(self)

        async def __aenter__(self):
            self.callback(*advertisement("60:FC:F1:00:61:61", "CT Logger", {0x0DE4: b"\x00"}))
            self.callback(*advertisement("AA:BB:CC:DD:EE:FF"))
            return self

        async def __aexit__(self, *_args):
            pass

    monkeypatch.setattr(scan, "BleakScanner", FakeScanner)
    result = asyncio.run(scan.collect_scan(default_multicast_address(28887), duration=0.01, standalone=True))
    (scanner,) = scanners
    # macOS reports identifiers rather than addresses unless asked, as native_bt does
    assert scanner.kwargs["cb"] == {"use_bdaddr": True}
    assert scanner.kwargs["bluez"] == {"filters": {"DuplicateData": True}}
    assert [row["identifier"] for row in result["items"]] == ["60:FC:F1:00:61:61", "AA:BB:CC:DD:EE:FF"]
    assert (result["next_cursor"], result["gateway"]) == (None, None)


def test_snapshot_text_gives_firmware_its_own_age(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr("infuse_iot.services.device_state.time.monotonic", lambda: clock[0])
    state = DeviceState()
    state.observe(packet(announce()))
    clock[0] = 110
    state.observe(packet(readings.ambient_temperature(23000)))
    (row,) = state.snapshot(fields=["AMBIENT_TEMPERATURE"], max_age_seconds=30)["items"]
    assert snapshot.describe(row) == (
        "0xce7e42571a000099 firmware 1.3.1+7bee09d5 (announced 100.0s ago, stale), last heard 0.0s ago"
    )
    unannounced = DeviceState()
    unannounced.observe(packet(readings.ambient_temperature(23000)))
    assert snapshot.describe(unannounced.snapshot()["items"][0]) == (
        "0xce7e42571a000099 firmware unknown, last heard 0.0s ago"
    )


def test_snapshot_collects_telemetry_from_gateway(loopback_gateway, capsys):
    gateway = loopback_gateway(28889)
    stop = threading.Event()

    def device():
        # A device announcing periodically
        while not stop.wait(0.05):
            gateway.server.broadcast(ClientNotificationEpacketReceived(packet(announce())))

    thread = threading.Thread(target=device)
    thread.start()
    try:
        snapshot.SubCommand(argparse.Namespace(server_sock=gateway.address, duration=0.5, json=True)).run()
    finally:
        stop.set()
        thread.join()
    result = json.loads(capsys.readouterr().out)
    (row,) = result["items"]
    assert (row["id"], row["firmware_version"]) == ("0xce7e42571a000099", "1.3.1+7bee09d5")
    assert result["gateway"]["instance_id"] == gateway.server.control.instance_id
    # The gateway does not report counters
    assert result["gateway"]["counters"] is None
    assert result["next_cursor"] is None


def test_snapshot_without_gateway_exits_cleanly():
    args = argparse.Namespace(server_sock=default_multicast_address(28891), duration=0.1, json=False)
    with pytest.raises(SystemExit) as exit_info:
        snapshot.SubCommand(args).run()
    assert str(exit_info.value.code).startswith("gateway_unavailable: ")
