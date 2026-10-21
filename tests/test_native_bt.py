import argparse
import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError
from cryptography.exceptions import InvalidTag

from infuse_iot.common import InfuseBluetoothUUID, InfuseType
from infuse_iot.database import UnknownNetworkError
from infuse_iot.gateway_control import GatewayControl
from infuse_iot.services.ble_observations import INFUSE_SERVICE
from infuse_iot.socket_comms import (
    ClientNotification,
    ClientNotificationConnection,
    ClientNotificationConnectionCreated,
    ClientNotificationConnectionDropped,
    ClientNotificationConnectionFailed,
    ClientNotificationEpacketReceived,
    GatewayRequest,
    GatewayRequestConnectionRelease,
    GatewayRequestConnectionRequest,
    GatewayRequestControl,
)
from infuse_iot.tools.native_bt import InfuseGattReadResponse, MulticastHandler
from infuse_iot.tools.native_bt import SubCommand as NativeBt


class FakeBleakClient:
    def __init__(self, *_args, **kwargs):
        self.disconnected_callback = kwargs["disconnected_callback"]
        self._backend = object()
        self.mtu_size = 247
        self.start_notify = AsyncMock()
        self.stop_notify = AsyncMock()
        self.read_gatt_char = AsyncMock(return_value=bytes(InfuseGattReadResponse()))
        self.write_gatt_char = AsyncMock()
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        self.closed = True


@pytest.fixture
def handler():
    database = Mock()
    database.has_shared_key.return_value = True
    database.get_device_key_id.return_value = 1
    database.devices = {123: SimpleNamespace(device_key_id=1)}
    return MulticastHandler(database, Mock(), {123: Mock()})


def datagram(handler, request):
    handler.datagram_received(json.dumps(request.to_json()).encode(), ("localhost", 1))


def test_repeated_requests_share_connection_and_subscriptions(handler, monkeypatch):
    clients = []

    def create_client(*args, **kwargs):
        clients.append(FakeBleakClient(*args, **kwargs))
        return clients[-1]

    factory = Mock(side_effect=create_client)
    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakClient", factory)

    async def run():
        datagram(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.COMMAND, 1000))
        original_task = handler._tasks[123]
        datagram(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.DATA, 1000))
        assert handler._tasks[123] is original_task
        await asyncio.sleep(0)
        datagram(handler, GatewayRequestConnectionRelease(123))
        await asyncio.sleep(0)
        assert not original_task.done()
        assert not clients[0].closed
        datagram(handler, GatewayRequestConnectionRelease(123))
        await original_task

    asyncio.run(run())
    factory.assert_called_once()
    assert [call.args[0] for call in clients[0].start_notify.call_args_list] == [
        InfuseBluetoothUUID.COMMAND_CHAR,
        InfuseBluetoothUUID.DATA_CHAR,
    ]
    assert clients[0].closed
    notifications = [call.args[0] for call in handler._server.broadcast.call_args_list]
    assert [type(message) for message in notifications] == [
        ClientNotificationConnectionCreated,
        ClientNotificationConnectionCreated,
        ClientNotificationConnectionDropped,
    ]
    assert not handler._queues
    assert not handler._tasks


@pytest.mark.parametrize("error", [BleakError("failed"), TimeoutError("failed")])
def test_failed_setup_cleans_up_connection(handler, monkeypatch, error):
    monkeypatch.setattr(handler, "create_connection_internal", AsyncMock(side_effect=error))

    async def run():
        datagram(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.DATA, 1000))
        await handler._tasks[123]

    asyncio.run(run())
    assert not handler._queues
    assert not handler._tasks
    notification = handler._server.broadcast.call_args.args[0]
    assert isinstance(notification, ClientNotificationConnectionFailed)
    assert "failed" in notification.reason


def test_remote_disconnect_wakes_connection_loop(handler, monkeypatch):
    clients = []

    def factory(*args, **kwargs):
        client = FakeBleakClient(*args, **kwargs)
        clients.append(client)
        asyncio.get_running_loop().call_soon(client.disconnected_callback, client)
        return client

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakClient", factory)

    async def run():
        datagram(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.DATA, 1000))
        await asyncio.wait_for(handler._tasks[123], timeout=1.0)

    asyncio.run(run())
    assert clients[0].closed
    assert isinstance(handler._server.broadcast.call_args.args[0], ClientNotificationConnectionDropped)
    assert not handler._tasks


def test_setup_steps_share_request_timeout(handler, monkeypatch):
    clients = []

    async def never_completes(*_args):
        await asyncio.Event().wait()

    def factory(*args, **kwargs):
        client = FakeBleakClient(*args, **kwargs)
        # Subscribing never completes after the connection has been established.
        client.start_notify = AsyncMock(side_effect=never_completes)
        clients.append(client)
        return client

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakClient", factory)

    async def run():
        datagram(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.DATA, 50))
        await asyncio.wait_for(handler._tasks[123], timeout=1.0)

    asyncio.run(run())
    assert clients[0].closed
    notification = handler._server.broadcast.call_args.args[0]
    assert isinstance(notification, ClientNotificationConnectionFailed)
    assert "timed out" in notification.reason


def test_shutdown_cancels_live_connections(handler, monkeypatch):
    async def run():
        started = asyncio.Event()

        async def wait_forever(*_args):
            started.set()
            await asyncio.Future()

        monkeypatch.setattr(handler, "create_connection_internal", wait_forever)
        datagram(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.DATA, 1000))
        await started.wait()
        await handler.shutdown()

    asyncio.run(run())
    assert not handler._tasks
    assert not handler._queues


def test_request_during_teardown_creates_new_connection(handler, monkeypatch):
    clients: list[FakeBleakClient] = []
    teardown = asyncio.Event()

    class SlowDisconnectClient(FakeBleakClient):
        async def __aexit__(self, *_args):
            if len(clients) == 1:
                await teardown.wait()
            self.closed = True

    def factory(*args, **kwargs):
        clients.append(SlowDisconnectClient(*args, **kwargs))
        return clients[-1]

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakClient", factory)

    async def run():
        datagram(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.DATA, 1000))
        first = handler._tasks[123]
        datagram(handler, GatewayRequestConnectionRelease(123))
        while not teardown_started():
            await asyncio.sleep(0)
        # A second client requests the device while the first connection is disconnecting.
        datagram(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.DATA, 1000))
        teardown.set()
        await first
        second = handler._tasks[123]
        assert second is not first
        await asyncio.sleep(0)
        datagram(handler, GatewayRequestConnectionRelease(123))
        await second

    def teardown_started():
        return any(isinstance(call.args[0], ClientNotificationConnectionCreated) for call in broadcasts()) and (
            handler._queues[123].empty()
        )

    def broadcasts():
        return handler._server.broadcast.call_args_list

    asyncio.run(asyncio.wait_for(run(), timeout=1.0))
    assert len(clients) == 2
    assert all(client.closed for client in clients)
    assert [type(call.args[0]) for call in broadcasts()] == [
        ClientNotificationConnectionCreated,
        ClientNotificationConnectionDropped,
        ClientNotificationConnectionCreated,
        ClientNotificationConnectionDropped,
    ]
    assert not handler._queues
    assert not handler._tasks


def test_request_queued_behind_dropped_connection_reconnects(handler, monkeypatch):
    clients = []

    def factory(*args, **kwargs):
        clients.append(FakeBleakClient(*args, **kwargs))
        return clients[-1]

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakClient", factory)

    async def run():
        datagram(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.DATA, 1000))
        first = handler._tasks[123]
        while not handler._connected:
            await asyncio.sleep(0)
        # The link drops before the connection loop handles a second client's request.
        clients[0].disconnected_callback(clients[0])
        datagram(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.DATA, 1000))
        await first
        second = handler._tasks[123]
        await asyncio.sleep(0)
        datagram(handler, GatewayRequestConnectionRelease(123))
        await second

    asyncio.run(asyncio.wait_for(run(), timeout=1.0))
    assert len(clients) == 2
    assert [type(call.args[0]) for call in handler._server.broadcast.call_args_list] == [
        ClientNotificationConnectionCreated,
        ClientNotificationConnectionDropped,
        ClientNotificationConnectionCreated,
        ClientNotificationConnectionDropped,
    ]


def test_abandoned_request_during_teardown_does_not_reconnect(handler, monkeypatch):
    clients = []

    def factory(*args, **kwargs):
        clients.append(FakeBleakClient(*args, **kwargs))
        return clients[-1]

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakClient", factory)

    async def run():
        datagram(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.DATA, 1000))
        first = handler._tasks[123]
        while not handler._connected:
            await asyncio.sleep(0)
        clients[0].disconnected_callback(clients[0])
        # The second client gave up and released its request before the gateway handled it.
        datagram(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.DATA, 1000))
        datagram(handler, GatewayRequestConnectionRelease(123))
        await first

    asyncio.run(asyncio.wait_for(run(), timeout=1.0))
    assert len(clients) == 1
    assert not handler._queues
    assert not handler._tasks


def test_shutdown_does_not_reconnect_queued_requests(handler, monkeypatch):
    clients = []

    def factory(*args, **kwargs):
        clients.append(FakeBleakClient(*args, **kwargs))
        return clients[-1]

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakClient", factory)

    async def run():
        datagram(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.DATA, 1000))
        while not handler._connected:
            await asyncio.sleep(0)
        queued = GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.DATA, 1000)
        handler._queues[123].put_nowait(queued)
        await handler.shutdown()

    asyncio.run(asyncio.wait_for(run(), timeout=1.0))
    assert len(clients) == 1
    assert not handler._tasks
    assert not handler._queues


class ObservingServer:
    """Updates gateway control from each broadcast, as `LocalServer` does."""

    def __init__(self):
        self.sent: list = []
        self.control = GatewayControl(self.sent.append)

    def broadcast(self, notification):
        self.control.observe(notification)
        self.sent.append(notification)

    def results(self):
        return [(type(n), n.operation_id) for n in self.sent if isinstance(n, ClientNotificationConnection)]


@pytest.fixture
def owned(monkeypatch):
    """A gateway with operation control, whose first Bluetooth link is slow to disconnect."""
    clients: list[FakeBleakClient] = []
    teardown = asyncio.Event()

    class SlowDisconnectClient(FakeBleakClient):
        async def __aexit__(self, *_args):
            if self is clients[0]:
                await teardown.wait()
            self.closed = True

    def factory(*args, **kwargs):
        clients.append(SlowDisconnectClient(*args, **kwargs))
        return clients[-1]

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakClient", factory)
    database = Mock()
    database.has_shared_key.return_value = True
    database.get_device_key_id.return_value = 1
    database.devices = {123: SimpleNamespace(device_key_id=1)}
    server: Any = ObservingServer()
    handler = MulticastHandler(database, server, {123: Mock()})
    return SimpleNamespace(handler=handler, server=server, clients=clients, teardown=teardown)


def send(handler, request, owner=None):
    values = request.to_json()
    if owner is not None:
        values["operation_id"] = owner
    handler.datagram_received(json.dumps(values).encode(), ("localhost", 1))


def control(handler, method, **parameters):
    send(handler, GatewayRequestControl(method, parameters))
    return handler._server.sent[-1]


def acquire(handler, owner, device_id="0x000000000000007b"):
    return control(handler, "acquire_operation", device_id=device_id, owner=owner, duration_seconds=60)


def connect(handler, owner=None):
    send(handler, GatewayRequestConnectionRequest(123, GatewayRequestConnectionRequest.DataType.COMMAND, 1000), owner)


def test_owner_reconnect_during_teardown_is_released(owned):
    handler = owned.handler

    async def run():
        assert acquire(handler, "A").ok
        connect(handler, "A")
        first = handler._tasks[123]
        while not handler._connected:
            await asyncio.sleep(0)
        send(handler, GatewayRequestConnectionRelease(123), "A")
        while not handler._queues[123].empty():
            await asyncio.sleep(0)
        # The owner reconnects while its first link is disconnecting, so native_bt creates a new link.
        connect(handler, "A")
        owned.teardown.set()
        await first
        second = handler._tasks[123]
        while 123 not in handler._connected:
            await asyncio.sleep(0)
        send(handler, GatewayRequestConnectionRelease(123), "A")
        await second
        assert control(handler, "release_operation", owner="A").ok
        assert acquire(handler, "C", "0x000000000000007c").ok

    asyncio.run(asyncio.wait_for(run(), timeout=1.0))
    created, dropped = ClientNotificationConnectionCreated, ClientNotificationConnectionDropped
    assert owned.server.results() == [(created, "A"), (dropped, "A"), (created, "A"), (dropped, "A")]
    assert len(owned.clients) == 2
    assert all(client.closed for client in owned.clients)
    assert not handler._tasks


def test_operation_waits_for_released_legacy_link(owned):
    handler = owned.handler

    async def run():
        connect(handler)
        first = handler._tasks[123]
        while not handler._connected:
            await asyncio.sleep(0)
        send(handler, GatewayRequestConnectionRelease(123))
        # Results from the disconnecting link must not reach a new owner.
        assert acquire(handler, "A").code == "device_busy"
        owned.teardown.set()
        await first
        assert acquire(handler, "A").ok
        connect(handler, "A")
        second = handler._tasks[123]
        while 123 not in handler._connected:
            await asyncio.sleep(0)
        send(handler, GatewayRequestConnectionRelease(123), "A")
        await second
        assert control(handler, "release_operation", owner="A").ok

    asyncio.run(asyncio.wait_for(run(), timeout=1.0))
    created, dropped = ClientNotificationConnectionCreated, ClientNotificationConnectionDropped
    assert owned.server.results() == [(created, None), (dropped, None), (created, "A"), (dropped, "A")]
    assert all(client.closed for client in owned.clients)
    assert not handler._tasks


def test_legacy_reconnect_during_teardown_blocks_operations(owned):
    handler = owned.handler

    async def run():
        connect(handler)
        first = handler._tasks[123]
        while not handler._connected:
            await asyncio.sleep(0)
        send(handler, GatewayRequestConnectionRelease(123))
        while not handler._queues[123].empty():
            await asyncio.sleep(0)
        # A second legacy client connects while the first link is disconnecting.
        connect(handler)
        owned.teardown.set()
        await first
        second = handler._tasks[123]
        while 123 not in handler._connected:
            await asyncio.sleep(0)
        assert acquire(handler, "A").code == "device_busy"
        send(handler, GatewayRequestConnectionRelease(123))
        await second
        assert acquire(handler, "A").ok

    asyncio.run(asyncio.wait_for(run(), timeout=1.0))
    created, dropped = ClientNotificationConnectionCreated, ClientNotificationConnectionDropped
    assert owned.server.results() == [(created, None), (dropped, None), (created, None), (dropped, None)]
    assert all(client.closed for client in owned.clients)
    assert not handler._tasks


@pytest.fixture
def gateway(monkeypatch):
    """The native Bluetooth gateway command, without sockets, credentials or an adapter."""
    monkeypatch.setattr("infuse_iot.tools.native_bt.LocalServer", lambda _address: ObservingServer())
    monkeypatch.setattr("infuse_iot.tools.native_bt.DeviceDatabase", Mock())
    monkeypatch.setattr("infuse_iot.tools.native_bt.Console.init", lambda: None)
    return NativeBt(argparse.Namespace(root=None, server_sock=("224.1.1.1", 1), report_interval=0))


def advertise(command, address, name=None, manufacturer=None, services=()):
    device = BLEDevice(address, name, None)
    data = AdvertisementData(name, manufacturer or {}, {}, list(services), None, -60, ())
    command.simple_callback(device, data)


def query(command, method, parameters):
    """Send a control request and decode the reply, as datagrams are."""
    request = json.loads(json.dumps(GatewayRequestControl(method, parameters).to_json()))
    command.server.control.accept(GatewayRequest.from_json(request))
    return ClientNotification.from_json(json.loads(json.dumps(command.server.sent[-1].to_json())))


def test_gateway_serves_raw_observations(gateway):
    advertise(gateway, "60:fc:f1:00:61:61", "CT Logger", {0x004C: b"\x01"})
    advertise(gateway, "60:fc:f1:00:61:61", services=[INFUSE_SERVICE])
    advertise(gateway, "aa:bb:cc:dd:ee:ff")
    capabilities = gateway.server.control.capabilities()
    assert {"raw_observations", "diagnostics"} <= set(capabilities["features"])
    reply = query(gateway, "raw_observations", {"max_age_seconds": 20, "cursor": None, "limit": 1})
    assert reply.ok
    (row,) = reply.result["items"]
    assert (row["identifier"], row["name"], row["infuse_candidate"]) == ("60:FC:F1:00:61:61", "CT Logger", True)
    assert reply.result["gateway"] == {
        "instance_id": capabilities["instance_id"],
        "version": capabilities["version"],
        "gateway_kind": "native_bt",
        "protocol_version": 2,
    }
    following = query(gateway, "raw_observations", {"max_age_seconds": 20, "cursor": reply.result["next_cursor"]})
    assert [row["identifier"] for row in following.result["items"]] == ["AA:BB:CC:DD:EE:FF"]
    expired = query(gateway, "raw_observations", {"max_age_seconds": 20, "cursor": "deadbeef:1"})
    assert (expired.ok, expired.code) == (False, "snapshot_expired")


@pytest.mark.parametrize(
    "parameters, code, message",
    [
        ({"cursor": 5}, "invalid_cursor", "cursor"),
        ({"max_age_seconds": 10**400}, "invalid_request", "max_age_seconds"),
        ({"max_age_seconds": "20"}, "invalid_request", "max_age_seconds"),
        ({"limit": True}, "invalid_request", "limit"),
        ({"limit": 201}, "invalid_request", "limit"),
        ({"infuse_only": "yes"}, "invalid_request", "infuse_only"),
        ({"max_bytes": 60000}, "invalid_request", "Unknown parameters: max_bytes"),
    ],
)
def test_gateway_rejects_invalid_observation_parameters(gateway, parameters, code, message):
    reply = query(gateway, "raw_observations", parameters)
    assert (reply.ok, reply.code) == (False, code)
    assert message in reply.result["message"]


def test_gateway_counts_decryption_failures(gateway, monkeypatch):
    header = SimpleNamespace(device_id=123, flags=0, key_metadata=0xCE7E50, gps_time=0, sequence=1, type=InfuseType.TDF)
    decrypt = Mock(side_effect=[UnknownNetworkError(0x123456), InvalidTag(), (header, b"")])
    monkeypatch.setattr("infuse_iot.tools.native_bt.CtypeBtAdvFrame.decrypt", decrypt)
    for _ in range(3):
        advertise(gateway, "60:fc:f1:00:61:61", manufacturer={0x0DE4: b"\x00" * 16})
    advertise(gateway, "aa:bb:cc:dd:ee:ff", manufacturer={0x004C: b"\x01"})
    reply = query(gateway, "diagnostics", {})
    assert reply.result == {
        "infuse_advertisements": 3,
        "decrypted_packets": 1,
        "unknown_network_packets": 1,
        "invalid_tag_packets": 1,
        "advertisements": 4,
        "gateway_kind": "native_bt",
    }
    assert isinstance(gateway.server.sent[0], ClientNotificationEpacketReceived)
    assert query(gateway, "diagnostics", {"reset": True}).code == "invalid_request"
