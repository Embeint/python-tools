import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from bleak.exc import BleakError

from infuse_iot.common import InfuseBluetoothUUID
from infuse_iot.socket_comms import (
    ClientNotificationConnectionCreated,
    ClientNotificationConnectionDropped,
    ClientNotificationConnectionFailed,
    GatewayRequestConnectionRelease,
    GatewayRequestConnectionRequest,
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
    assert isinstance(handler._server.broadcast.call_args.args[0], ClientNotificationConnectionFailed)


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
