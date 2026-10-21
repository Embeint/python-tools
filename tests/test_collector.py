import ctypes
import json
import time

import pytest

from infuse_iot.common import InfuseType
from infuse_iot.definitions.tdf import readings, structs
from infuse_iot.epacket import interface
from infuse_iot.epacket.packet import Auth, HopReceived, PacketReceived
from infuse_iot.services.collector import TelemetryCollector
from infuse_iot.socket_comms import (
    ClientNotificationEpacketReceived,
    GatewayControlError,
    LocalClient,
    default_multicast_address,
)
from infuse_iot.tdf import TDF

DEVICE = 0xCE7E42571A000099


def notification(reading, device=DEVICE):
    payload = bytes(TDF.CoreHeader(reading.ID, ctypes.sizeof(reading))) + bytes(reading)
    address = interface.Address(interface.Address.BluetoothLeAddr(0, 0x60FCF1006161))
    hop = HopReceived(device, interface.ID.BT_ADV, address, Auth.NETWORK, 0xCE7E50, 0, 0, -65)
    return ClientNotificationEpacketReceived(PacketReceived([hop], InfuseType.TDF, payload))


def announce():
    return readings.announce(0xCE710003, structs.tdf_struct_mcuboot_img_sem_ver(1, 3, 1, 0x7BEE09D5), 0, 0, 10, 0, 0)


def wait_for(condition, timeout=2.0):
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "Condition not reached"
        time.sleep(0.01)


def observed(collector, name):
    items = collector.state.snapshot(paginate=False)["items"]
    return bool(items) and name in items[0]["readings"]


def test_collector_skips_unknown_and_malformed_notifications(loopback_gateway):
    gateway = loopback_gateway(28871)
    collector = TelemetryCollector(gateway.address)
    collector.start()
    try:
        assert collector.running
        assert collector.state.gateway is not None
        assert collector.state.gateway["instance_id"] == gateway.server.control.instance_id
        gateway.server.broadcast(notification(announce()))
        # A future notification type, a corrupt datagram and an invalid packet
        gateway.send_raw(json.dumps({"type": 99}).encode())
        gateway.send_raw(b"\xff")
        gateway.send_raw(json.dumps({"type": 0, "epacket": {}}).encode())
        gateway.server.broadcast(notification(readings.ambient_temperature(23000)))
        wait_for(lambda: observed(collector, "AMBIENT_TEMPERATURE"))
        assert collector.running
        assert (collector.error, collector.error_code) == (None, None)
        assert collector.skipped_notifications == 3
        assert observed(collector, "ANNOUNCE")
    finally:
        collector.close()
    assert not collector.running


def test_collector_reports_socket_failure_and_restarts(loopback_gateway, monkeypatch):
    gateway = loopback_gateway(28873)
    collector = TelemetryCollector(gateway.address)
    collector.start()
    try:
        gateway.server.broadcast(notification(announce()))
        wait_for(lambda: observed(collector, "ANNOUNCE"))
        monkeypatch.setattr(collector._client, "receive", lambda: (_ for _ in ()).throw(OSError(9, "Bad file")))
        wait_for(lambda: not collector.running)
        assert collector.error_code == "gateway_unavailable"
        assert "Bad file" in str(collector.error)
        # Restarting attaches a new socket and keeps the collected state
        collector.start()
        assert collector.running and collector.error is None
        gateway.server.broadcast(notification(readings.ambient_temperature(23000)))
        wait_for(lambda: observed(collector, "AMBIENT_TEMPERATURE"))
        assert observed(collector, "ANNOUNCE")
    finally:
        collector.close()


def test_collection_window_fails_promptly_when_the_worker_stops(loopback_gateway, monkeypatch):
    gateway = loopback_gateway(28875)
    receive = LocalClient.receive

    def failing(self, timeout=None):
        # Capability queries wait with a timeout, the worker without
        if timeout is None:
            raise OSError(9, "Bad file descriptor")
        return receive(self, timeout)

    monkeypatch.setattr(LocalClient, "receive", failing)
    collector = TelemetryCollector(gateway.address)
    start = time.monotonic()
    with pytest.raises(GatewayControlError) as error:
        collector.collect(10)
    assert error.value.code == "gateway_unavailable"
    assert time.monotonic() - start < 5
    assert not collector.running


def test_collector_without_gateway_is_unavailable():
    collector = TelemetryCollector(default_multicast_address(28877))
    with pytest.raises(GatewayControlError) as error:
        collector.start()
    assert error.value.code == "gateway_unavailable"
    assert not collector.running


def test_collection_reports_gateway_identity_and_window_counters(loopback_gateway):
    gateway = loopback_gateway(28879)
    gateway.server.control.kind = "native_bt"
    # Counters since the gateway started, at the start and end of the window
    replies = [
        {"decrypted_packets": 5, "unknown_network_packets": 1, "gateway_kind": "native_bt"},
        {"decrypted_packets": 5, "unknown_network_packets": 4, "gateway_kind": "native_bt"},
    ]

    def diagnostics(_params):
        if len(replies) == 2:
            gateway.server.broadcast(notification(announce()))
        return replies.pop(0)

    gateway.server.control.handlers["diagnostics"] = diagnostics
    collector = TelemetryCollector(gateway.address)
    result = collector.collect(0.5, paginate=False)
    assert result["total"] == 1
    assert result["gateway"] == {
        "instance_id": gateway.server.control.instance_id,
        "version": gateway.server.control.capabilities()["version"],
        "gateway_kind": "native_bt",
        "protocol_version": 2,
        "counters": {"decrypted_packets": 0, "unknown_network_packets": 3},
    }
    assert not collector.running


def test_collector_follows_a_replaced_gateway(loopback_gateway):
    first = loopback_gateway(28961)
    collector = TelemetryCollector(first.address)
    collector.start()

    def identity(key):
        return (collector.state.gateway or {}).get(key)

    try:
        first.close()
        second = loopback_gateway(28961)
        second.server.control.kind = "native_bt"
        # The socket survives the restart, so the identity comes from the next capability reply to any client.
        assert collector.running
        assert identity("instance_id") == first.server.control.instance_id
        probe = LocalClient(second.address)
        try:
            assert probe.capabilities()["instance_id"] == second.server.control.instance_id
        finally:
            probe.close()
        wait_for(lambda: identity("instance_id") == second.server.control.instance_id)
        assert identity("gateway_kind") == "native_bt"
        assert collector.capabilities["instance_id"] == second.server.control.instance_id
        # A probe made elsewhere can report an older gateway, whose replies carry no identity.
        collector.refresh({"protocol_version": 1, "features": []})
        assert collector.state.gateway == {
            "instance_id": None,
            "version": None,
            "gateway_kind": None,
            "protocol_version": 1,
        }
    finally:
        collector.close()
