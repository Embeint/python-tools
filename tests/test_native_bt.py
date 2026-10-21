import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from bleak.exc import BleakError

from infuse_iot.common import InfuseBluetoothUUID
from infuse_iot.gateway_control import GatewayControl
from infuse_iot.socket_comms import (
    ClientNotificationConnection,
    ClientNotificationConnectionCreated,
    ClientNotificationConnectionDropped,
    ClientNotificationConnectionFailed,
    GatewayRequestConnectionRelease,
    GatewayRequestConnectionRequest,
    GatewayRequestControl,
)
from infuse_iot.tools.native_bt import InfuseGattReadResponse, MulticastHandler


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
