import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from bleak.exc import BleakBluetoothNotAvailableError, BleakBluetoothNotAvailableReason, BleakError

from infuse_iot.common import InfuseBluetoothUUID
from infuse_iot.socket_comms import (
    ClientNotificationConnectionCreated,
    ClientNotificationConnectionDropped,
    ClientNotificationConnectionFailed,
    GatewayRequestConnectionRelease,
    GatewayRequestConnectionRequest,
)
from infuse_iot.tools.native_bt import InfuseGattReadResponse, MulticastHandler, SubCommand


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


def test_release_by_user_of_dropped_connection_does_not_cancel_queued_request(handler, monkeypatch):
    clients = []

    def factory(*args, **kwargs):
        clients.append(FakeBleakClient(*args, **kwargs))
        return clients[-1]

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakClient", factory)
    data = GatewayRequestConnectionRequest.DataType.DATA

    async def run():
        datagram(handler, GatewayRequestConnectionRequest(123, data, 1000, 1))
        datagram(handler, GatewayRequestConnectionRequest(123, data, 1000, 2))
        first = handler._tasks[123]
        while handler._server.broadcast.call_count < 2:
            await asyncio.sleep(0)
        # The link drops before the connection loop handles a third client's request and a user's release.
        clients[0].disconnected_callback(clients[0])
        datagram(handler, GatewayRequestConnectionRequest(123, data, 1000, 3))
        datagram(handler, GatewayRequestConnectionRelease(123, 2))
        await first
        second = handler._tasks[123]
        await asyncio.sleep(0)
        datagram(handler, GatewayRequestConnectionRelease(123, 3))
        await second

    asyncio.run(asyncio.wait_for(run(), timeout=1.0))
    assert len(clients) == 2
    notifications = [call.args[0] for call in handler._server.broadcast.call_args_list]
    assert [(type(n), getattr(n, "request_id", None)) for n in notifications] == [
        (ClientNotificationConnectionCreated, 1),
        (ClientNotificationConnectionCreated, 2),
        (ClientNotificationConnectionDropped, None),
        (ClientNotificationConnectionCreated, 3),
        (ClientNotificationConnectionDropped, None),
    ]


def test_cancelled_queued_request_during_teardown_does_not_reconnect(handler, monkeypatch):
    clients = []

    def factory(*args, **kwargs):
        clients.append(FakeBleakClient(*args, **kwargs))
        return clients[-1]

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakClient", factory)
    data = GatewayRequestConnectionRequest.DataType.DATA

    async def run():
        datagram(handler, GatewayRequestConnectionRequest(123, data, 1000, 1))
        first = handler._tasks[123]
        while not handler._connected:
            await asyncio.sleep(0)
        clients[0].disconnected_callback(clients[0])
        # The second client gives up on its request, while the first client's release has nothing to release.
        datagram(handler, GatewayRequestConnectionRequest(123, data, 1000, 2))
        datagram(handler, GatewayRequestConnectionRelease(123, 1))
        datagram(handler, GatewayRequestConnectionRelease(123, 2))
        await first

    asyncio.run(asyncio.wait_for(run(), timeout=1.0))
    assert len(clients) == 1
    assert not handler._queues
    assert not handler._tasks


@pytest.fixture
def scanner_tool(monkeypatch):
    # Avoid opening real Bluetooth sockets or loading the user's device database.
    tool = object.__new__(SubCommand)
    tool.bleak_mapping = {123: Mock()}
    tool.infuse_manu = 0x0DE4
    tool.report_count = 0
    tool.infuse_report_count = 0
    tool.report_interval = 0
    tool.SCAN_CHECK_INTERVAL = 0
    tool.SCAN_RETRY_DELAY = 0
    tool.SCAN_RETRY_MAX_DELAY = 0
    tool.SCAN_OPERATION_TIMEOUT = 0.01
    monkeypatch.setattr("infuse_iot.tools.native_bt.wake_time", Mock(return_value=(100, 0)))
    monkeypatch.setattr("infuse_iot.tools.native_bt.assert_mta", AsyncMock(), raising=False)
    return tool


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("wake", "Mac woke from sleep"),
        ("powered_off", "Bluetooth adapter state changed"),
        ("resetting", "Bluetooth adapter state changed"),
        ("stopped", "CoreBluetooth stopped scanning"),
    ],
)
def test_quiet_scanner_restarts_only_for_native_state_changes(scanner_tool, monkeypatch, change, reason):
    monkeypatch.setattr("infuse_iot.tools.native_bt.sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr("infuse_iot.tools.native_bt.CBManagerStatePoweredOn", 5, raising=False)
    manager = Mock()
    manager.state.return_value = 5
    manager.isScanning.return_value = True
    scanner = SimpleNamespace(_backend=SimpleNamespace(_manager=SimpleNamespace(central_manager=manager)))
    wake = Mock(return_value=(100, 0))
    monkeypatch.setattr("infuse_iot.tools.native_bt.wake_time", wake)

    async def run():
        task = asyncio.create_task(scanner_tool._wait_for_scanner_restart(scanner, (100, 0)))
        # No device callbacks at all. Healthy native scanning must remain running indefinitely.
        for _ in range(10):
            await asyncio.sleep(0)
        assert not task.done()
        if change == "wake":
            wake.return_value = (200, 0)
        elif change == "powered_off":
            manager.state.return_value = 4
        elif change == "resetting":
            manager.state.return_value = 1
        else:
            manager.isScanning.return_value = False
        assert await asyncio.wait_for(task, 1.0) == reason

    asyncio.run(run())


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_other_platforms_do_not_query_macos_or_restart_for_silence(scanner_tool, monkeypatch, platform):
    monkeypatch.setattr("infuse_iot.tools.native_bt.sys", SimpleNamespace(platform=platform))
    wake = Mock(side_effect=AssertionError("macOS query on another platform"))
    monkeypatch.setattr("infuse_iot.tools.native_bt.wake_time", wake)

    async def run():
        task = asyncio.create_task(scanner_tool._wait_for_scanner_restart(Mock(), None))
        for _ in range(10):
            await asyncio.sleep(0)
        assert not task.done()
        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1.0)

    asyncio.run(run())
    wake.assert_not_called()


def test_wake_recreates_backend_and_discards_old_devices(scanner_tool, monkeypatch):
    scanners = []

    def factory(*_args, **_kwargs):
        scanner = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
        scanners.append(scanner)
        assert not scanner_tool.bleak_mapping
        return scanner

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakScanner", factory)

    async def run():
        restarted = asyncio.Event()

        async def wait_for_restart(_scanner, _started_wake):
            if len(scanners) == 1:
                scanner_tool.bleak_mapping[123] = Mock()
                return "Mac woke from sleep"
            restarted.set()
            await asyncio.Future()

        monkeypatch.setattr(scanner_tool, "_wait_for_scanner_restart", wait_for_restart)
        task = asyncio.create_task(scanner_tool.scanner_handler())
        await asyncio.wait_for(restarted.wait(), 1.0)
        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1.0)

    asyncio.run(run())
    assert len(scanners) == 2
    for scanner in scanners:
        scanner.start.assert_awaited_once()
        scanner.stop.assert_awaited_once()


@pytest.mark.parametrize(
    "failure", ["start", "powered_off", "start_os_error", "start_timeout", "stop", "stop_assert", "stop_timeout"]
)
def test_scanner_retries_when_bluetooth_is_unavailable(scanner_tool, monkeypatch, failure):
    scanners = []
    attempts = 0

    async def never_completes():
        await asyncio.Future()

    def factory(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        scanner = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
        if attempts == 1:
            if failure in ("start", "stop"):
                getattr(scanner, failure).side_effect = BleakError("Bluetooth resetting")
            elif failure == "powered_off":
                scanner.start.side_effect = BleakBluetoothNotAvailableError(
                    "Bluetooth is off", BleakBluetoothNotAvailableReason.POWERED_OFF
                )
            elif failure == "start_os_error":
                scanner.start.side_effect = OSError("D-Bus unavailable")
            elif failure == "start_timeout":
                scanner.start.side_effect = never_completes
            elif failure == "stop_assert":
                # WinRT asserts when stopping a watcher that does not exist
                scanner.stop.side_effect = AssertionError()
            elif failure == "stop_timeout":
                scanner.stop.side_effect = never_completes
        scanners.append(scanner)
        return scanner

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakScanner", factory)

    async def run():
        recovered = asyncio.Event()

        async def wait_for_restart(_scanner, _started_wake):
            if attempts == 1:
                return
            recovered.set()
            await asyncio.Future()

        monkeypatch.setattr(scanner_tool, "_wait_for_scanner_restart", wait_for_restart)
        task = asyncio.create_task(scanner_tool.scanner_handler())
        await asyncio.wait_for(recovered.wait(), 1.0)
        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1.0)

    asyncio.run(run())
    assert attempts == 2
    # Ordinary exceptions and timeouts can both leave partially allocated scanner resources.
    scanners[0].stop.assert_awaited_once()
    scanners[1].stop.assert_awaited_once()


@pytest.mark.parametrize("allocated", [False, True])
def test_winrt_failed_start_cleans_up_allocated_watcher(scanner_tool, monkeypatch, allocated):
    monkeypatch.setattr("infuse_iot.tools.native_bt.sys", SimpleNamespace(platform="win32"))
    handlers: set[str] = set()
    scanners: list[SimpleNamespace] = []
    watchers: list[SimpleNamespace] = []

    def factory(*_args, **_kwargs):
        backend = SimpleNamespace(watcher=None, _received_token=None, _stopped_token=None)
        watcher = SimpleNamespace(
            stop=Mock(),
            status=SimpleNamespace(name="STOPPED"),
            remove_received=Mock(side_effect=handlers.remove),
            remove_stopped=Mock(side_effect=handlers.remove),
        )
        watchers.append(watcher)

        async def start():
            if len(scanners) == 1:
                if allocated:
                    backend.watcher = watcher
                    backend._received_token = "received"
                    backend._stopped_token = "stopped"
                    handlers.update(("received", "stopped"))
                raise BleakError("Failed to start scanner. Is Bluetooth turned on?")
            backend.watcher = watcher

        scanner = SimpleNamespace(_backend=backend, start=AsyncMock(side_effect=start), stop=AsyncMock())
        scanners.append(scanner)
        return scanner

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakScanner", factory)

    async def run():
        recovered = asyncio.Event()

        async def wait_for_restart(_scanner, _started_wake):
            # No native registrations from the failed attempt may survive into the next session.
            assert not handlers
            recovered.set()
            await asyncio.Future()

        monkeypatch.setattr(scanner_tool, "_wait_for_scanner_restart", wait_for_restart)
        task = asyncio.create_task(scanner_tool.scanner_handler())
        try:
            await asyncio.wait_for(recovered.wait(), 1.0)
        finally:
            task.cancel()
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1.0)

    asyncio.run(run())
    assert len(scanners) == 2
    assert watchers[0].stop.call_count == int(allocated)
    watchers[1].stop.assert_called_once()
    for scanner in scanners:
        scanner.stop.assert_not_awaited()
    assert not handlers


def test_windows_com_configuration_failure_is_not_retried(scanner_tool, monkeypatch):
    monkeypatch.setattr("infuse_iot.tools.native_bt.sys", SimpleNamespace(platform="win32"))
    check = AsyncMock(side_effect=BleakError("Thread is configured for Windows GUI but callbacks are not working."))
    monkeypatch.setattr("infuse_iot.tools.native_bt.assert_mta", check)
    factory = Mock()
    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakScanner", factory)

    with pytest.raises(BleakError, match="callbacks are not working"):
        asyncio.run(asyncio.wait_for(scanner_tool.scanner_handler(), 1.0))
    check.assert_awaited_once()
    factory.assert_not_called()


@pytest.mark.parametrize("failure", ["registration", "stop_timeout", "remove_received", "remove_stopped"])
def test_winrt_cleanup_releases_handlers_when_normal_stop_fails(scanner_tool, monkeypatch, failure):
    monkeypatch.setattr("infuse_iot.tools.native_bt.sys", SimpleNamespace(platform="win32"))
    handlers: set[int] = set()
    scanners: list[SimpleNamespace] = []

    def factory(*_args, **_kwargs):
        backend = SimpleNamespace(
            watcher=None, _received_token=None, _stopped_token=None, _stopped_event=asyncio.Event()
        )
        failed_once = set()

        def remove(token):
            if (failure, token) in (("remove_received", 0), ("remove_stopped", 1)) and token not in failed_once:
                failed_once.add(token)
                raise OSError("Transient event removal failure")
            handlers.remove(token)

        watcher = SimpleNamespace(
            stop=Mock(),
            status=SimpleNamespace(name="STOPPED"),
            remove_received=Mock(side_effect=remove),
            remove_stopped=Mock(side_effect=remove),
        )

        async def start():
            backend.watcher = watcher
            if len(scanners) == 1:
                backend._received_token = 0  # A registration token may be falsey, but still needs releasing.
                handlers.add(0)
                if failure == "registration":
                    raise OSError("add_stopped failed after add_received succeeded")
                backend._stopped_token = 1
                handlers.add(1)
                if failure == "stop_timeout":
                    watcher.status.name = "STOPPING"
                raise BleakError("Scanner aborted after registering both callbacks")

        scanner = SimpleNamespace(_backend=backend, start=AsyncMock(side_effect=start), stop=AsyncMock())
        scanners.append(scanner)
        return scanner

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakScanner", factory)

    async def run():
        recovered = asyncio.Event()

        async def wait_for_restart(_scanner, _started_wake):
            assert not handlers
            assert scanners[0]._backend.watcher is None
            recovered.set()
            await asyncio.Future()

        monkeypatch.setattr(scanner_tool, "_wait_for_scanner_restart", wait_for_restart)
        task = asyncio.create_task(scanner_tool.scanner_handler())
        try:
            await asyncio.wait_for(recovered.wait(), 1.0)
        finally:
            task.cancel()
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1.0)

    asyncio.run(run())
    assert len(scanners) == 2
    assert not handlers
    assert scanners[0]._backend._received_token is None
    assert scanners[0]._backend._stopped_token is None
    for scanner in scanners:
        scanner.stop.assert_not_awaited()


def test_winrt_unreleasable_handler_stops_retrying(scanner_tool, monkeypatch):
    monkeypatch.setattr("infuse_iot.tools.native_bt.sys", SimpleNamespace(platform="win32"))
    watcher = SimpleNamespace(
        stop=Mock(),
        status=SimpleNamespace(name="STOPPED"),
        remove_received=Mock(side_effect=OSError("Cannot release received handler")),
        remove_stopped=Mock(),
    )
    backend = SimpleNamespace(watcher=watcher, _received_token=1, _stopped_token=2)
    scanner = SimpleNamespace(
        _backend=backend, start=AsyncMock(side_effect=BleakError("Scanner aborted")), stop=AsyncMock()
    )
    factory = Mock(return_value=scanner)
    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakScanner", factory)

    with pytest.raises(BleakError, match="Unable to release Bluetooth scanner event handlers"):
        asyncio.run(asyncio.wait_for(scanner_tool.scanner_handler(), 1.0))
    factory.assert_called_once()
    assert watcher.remove_received.call_count == 2
    watcher.remove_stopped.assert_called_once_with(2)
    assert backend._received_token == 1
    assert backend._stopped_token is None


def test_scanner_constructor_errors_are_not_retried(scanner_tool, monkeypatch):
    factory = Mock(side_effect=BleakError("passive scanning mode requires bluez or_patterns"))
    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakScanner", factory)

    with pytest.raises(BleakError, match="or_patterns"):
        asyncio.run(asyncio.wait_for(scanner_tool.scanner_handler(), 1.0))
    factory.assert_called_once()


@pytest.mark.parametrize(
    "reason",
    [
        BleakBluetoothNotAvailableReason.DENIED_BY_USER,
        BleakBluetoothNotAvailableReason.DENIED_BY_SYSTEM,
        BleakBluetoothNotAvailableReason.DENIED_BY_UNKNOWN,
        BleakBluetoothNotAvailableReason.NO_BLE_CENTRAL_ROLE,
    ],
)
def test_scanner_permanent_errors_are_not_retried(scanner_tool, monkeypatch, reason):
    scanner = SimpleNamespace(
        start=AsyncMock(side_effect=BleakBluetoothNotAvailableError("Bluetooth access is denied", reason)),
        stop=AsyncMock(),
    )
    factory = Mock(return_value=scanner)
    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakScanner", factory)

    with pytest.raises(BleakBluetoothNotAvailableError):
        asyncio.run(asyncio.wait_for(scanner_tool.scanner_handler(), 1.0))
    factory.assert_called_once()
    scanner.stop.assert_awaited_once()


def test_scanner_retries_back_off_and_report_each_error_once(scanner_tool, monkeypatch):
    scanner_tool.SCAN_RETRY_DELAY = 5
    scanner_tool.SCAN_RETRY_MAX_DELAY = 20
    errors = [BleakError("Bluetooth is off")] * 4 + [BleakError("Bluetooth resetting"), None]
    log_error = Mock()
    log_info = Mock()
    monkeypatch.setattr("infuse_iot.tools.native_bt.Console.log_error", log_error)
    monkeypatch.setattr("infuse_iot.tools.native_bt.Console.log_info", log_info)
    monkeypatch.setattr(
        "infuse_iot.tools.native_bt.BleakScanner",
        lambda *_args, **_kwargs: SimpleNamespace(start=AsyncMock(side_effect=errors.pop(0)), stop=AsyncMock()),
    )
    delays = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay):
        if delay:
            delays.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    async def run():
        recovered = asyncio.Event()

        async def wait_for_restart(_scanner, _started_wake):
            recovered.set()
            await asyncio.Future()

        monkeypatch.setattr(scanner_tool, "_wait_for_scanner_restart", wait_for_restart)
        task = asyncio.create_task(scanner_tool.scanner_handler())
        await asyncio.wait_for(recovered.wait(), 1.0)
        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1.0)

    asyncio.run(run())
    assert delays == [5, 10, 20, 20, 20]
    assert [c.args[0] for c in log_error.call_args_list] == [
        "Bluetooth scanner unavailable, retrying: Bluetooth is off",
        "Bluetooth scanner unavailable, retrying: Bluetooth resetting",
    ]
    assert [c.args[0] for c in log_info.call_args_list] == ["Starting scanner", "Bluetooth scanner recovered"]


def test_scanner_start_timeout_is_reported(scanner_tool, monkeypatch):
    log_error = Mock()
    monkeypatch.setattr("infuse_iot.tools.native_bt.Console.log_error", log_error)
    attempts = 0

    async def never_completes():
        await asyncio.Future()

    def factory(*_args, **_kwargs):
        nonlocal attempts
        attempts += 1
        return SimpleNamespace(
            start=AsyncMock(side_effect=never_completes if attempts == 1 else None), stop=AsyncMock()
        )

    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakScanner", factory)

    async def run():
        recovered = asyncio.Event()

        async def wait_for_restart(_scanner, _started_wake):
            recovered.set()
            await asyncio.Future()

        monkeypatch.setattr(scanner_tool, "_wait_for_scanner_restart", wait_for_restart)
        task = asyncio.create_task(scanner_tool.scanner_handler())
        await asyncio.wait_for(recovered.wait(), 1.0)
        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1.0)

    asyncio.run(run())
    log_error.assert_called_once_with("Bluetooth scanner unavailable, retrying: timed out starting scanner")


def test_wake_time_failure_does_not_stop_scanning(scanner_tool, monkeypatch):
    monkeypatch.setattr("infuse_iot.tools.native_bt.sys", SimpleNamespace(platform="darwin"))
    wake = Mock(side_effect=OSError(2, "No such file or directory", "kern.waketime"))
    monkeypatch.setattr("infuse_iot.tools.native_bt.wake_time", wake)
    log_error = Mock()
    monkeypatch.setattr("infuse_iot.tools.native_bt.Console.log_error", log_error)
    scanner = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakScanner", Mock(return_value=scanner))

    async def run():
        scanning = asyncio.Event()

        async def wait_for_restart(_scanner, started_wake):
            assert started_wake is None
            scanning.set()
            await asyncio.Future()

        monkeypatch.setattr(scanner_tool, "_wait_for_scanner_restart", wait_for_restart)
        task = asyncio.create_task(scanner_tool.scanner_handler())
        await asyncio.wait_for(scanning.wait(), 1.0)
        # Later queries are skipped rather than logging on every check
        assert scanner_tool._wake_time() is None
        task.cancel()
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1.0)

    asyncio.run(run())
    scanner.start.assert_awaited_once()
    wake.assert_called_once()
    log_error.assert_called_once()


def test_wake_time_failure_while_scanning_keeps_scanner(scanner_tool, monkeypatch):
    monkeypatch.setattr("infuse_iot.tools.native_bt.sys", SimpleNamespace(platform="darwin"))
    monkeypatch.setattr("infuse_iot.tools.native_bt.CBManagerStatePoweredOn", 5, raising=False)
    monkeypatch.setattr("infuse_iot.tools.native_bt.Console.log_error", Mock())
    manager = Mock()
    manager.state.return_value = 5
    manager.isScanning.return_value = True
    scanner = SimpleNamespace(_backend=SimpleNamespace(_manager=SimpleNamespace(central_manager=manager)))
    monkeypatch.setattr("infuse_iot.tools.native_bt.wake_time", Mock(side_effect=OSError("kern.waketime")))

    async def run():
        task = asyncio.create_task(scanner_tool._wait_for_scanner_restart(scanner, (100, 0)))
        for _ in range(10):
            await asyncio.sleep(0)
        assert not task.done()
        # Scanner state is still monitored without wake detection
        manager.isScanning.return_value = False
        assert await asyncio.wait_for(task, 1.0) == "CoreBluetooth stopped scanning"

    asyncio.run(run())


def test_missing_corebluetooth_internals_still_detect_wake(scanner_tool, monkeypatch):
    monkeypatch.setattr("infuse_iot.tools.native_bt.sys", SimpleNamespace(platform="darwin"))
    log_error = Mock()
    monkeypatch.setattr("infuse_iot.tools.native_bt.Console.log_error", log_error)
    wake = Mock(return_value=(100, 0))
    monkeypatch.setattr("infuse_iot.tools.native_bt.wake_time", wake)

    async def run():
        task = asyncio.create_task(scanner_tool._wait_for_scanner_restart(SimpleNamespace(), (100, 0)))
        for _ in range(10):
            await asyncio.sleep(0)
        assert not task.done()
        wake.return_value = (200, 0)
        assert await asyncio.wait_for(task, 1.0) == "Mac woke from sleep"

    asyncio.run(run())
    log_error.assert_called_once()


@pytest.mark.parametrize("server_fails", [False, True])
def test_receiver_cleans_up_tasks_on_shutdown_or_server_failure(scanner_tool, monkeypatch, server_fails):
    scanner_tool.report_interval = 5.0
    started = set()
    stopped = set()

    async def run():
        ready = asyncio.Event()
        fail = asyncio.Event()

        async def worker(name):
            started.add(name)
            if len(started) == 3:
                ready.set()
            try:
                if name == "server" and server_fails:
                    await fail.wait()
                    raise OSError("local server failed")
                await asyncio.Future()
            finally:
                stopped.add(name)

        monkeypatch.setattr(scanner_tool, "server_handler", lambda: worker("server"))
        monkeypatch.setattr(scanner_tool, "scanner_handler", lambda: worker("scanner"))
        monkeypatch.setattr(scanner_tool, "report_counter", lambda: worker("reports"))
        task = asyncio.create_task(scanner_tool.async_bt_receiver())
        await asyncio.wait_for(ready.wait(), 1.0)
        if server_fails:
            fail.set()
            with pytest.raises(OSError, match="local server failed"):
                await asyncio.wait_for(task, 1.0)
        else:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(run())
    assert started == stopped == {"server", "scanner", "reports"}


@pytest.mark.parametrize("already_stopping", [False, True])
def test_receiver_cancellation_allows_async_scanner_cleanup(scanner_tool, monkeypatch, already_stopping):
    scanner_tool.SCAN_OPERATION_TIMEOUT = 1.0
    scanner = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakScanner", Mock(return_value=scanner))

    async def run():
        scanning = asyncio.Event()
        stop_entered = asyncio.Event()
        stop_allowed = asyncio.Event()
        stop_completed = asyncio.Event()

        async def server():
            await asyncio.Future()

        async def wait_for_restart(_scanner, _started_wake):
            scanning.set()
            if already_stopping:
                return "Mac woke from sleep"
            await asyncio.Future()

        async def stop():
            stop_entered.set()
            await stop_allowed.wait()
            stop_completed.set()

        scanner.stop.side_effect = stop
        monkeypatch.setattr(scanner_tool, "server_handler", server)
        monkeypatch.setattr(scanner_tool, "_wait_for_scanner_restart", wait_for_restart)
        task = asyncio.create_task(scanner_tool.async_bt_receiver())
        try:
            await asyncio.wait_for(scanning.wait(), 1.0)
            if already_stopping:
                await asyncio.wait_for(stop_entered.wait(), 1.0)
            task.cancel()
            await asyncio.wait_for(stop_entered.wait(), 1.0)
            for _ in range(10):
                await asyncio.sleep(0)
            still_waiting_for_cleanup = not task.done()
        finally:
            stop_allowed.set()
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 1.0)
        assert still_waiting_for_cleanup
        assert stop_completed.is_set()

    asyncio.run(run())
    scanner.stop.assert_awaited_once()


@pytest.mark.parametrize(("platform", "mode"), [("darwin", "active"), ("linux", "active"), ("win32", "passive")])
def test_scanning_mode_is_supported_by_platform(scanner_tool, monkeypatch, platform, mode):
    monkeypatch.setattr("infuse_iot.tools.native_bt.sys", SimpleNamespace(platform=platform))
    factory = Mock(side_effect=BleakError("stop after constructor"))
    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakScanner", factory)

    with pytest.raises(BleakError):
        asyncio.run(asyncio.wait_for(scanner_tool.scanner_handler(), 1.0))
    assert factory.call_args.kwargs["scanning_mode"] == mode


def test_bluez_accepts_scanner_configuration(scanner_tool, monkeypatch):
    bluez = pytest.importorskip("bleak.backends.bluezdbus.scanner")
    monkeypatch.setattr("infuse_iot.tools.native_bt.sys", SimpleNamespace(platform="linux"))
    factory = Mock(side_effect=BleakError("stop after constructor"))
    monkeypatch.setattr("infuse_iot.tools.native_bt.BleakScanner", factory)
    with pytest.raises(BleakError):
        asyncio.run(asyncio.wait_for(scanner_tool.scanner_handler(), 1.0))

    # BlueZ rejects unsupported arguments, such as passive scanning without `or_patterns`, in the constructor
    kwargs = factory.call_args.kwargs
    bluez.BleakScannerBlueZDBus(None, None, kwargs["scanning_mode"], bluez=kwargs["bluez"])
