import json
from collections import Counter, deque
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

import infuse_iot.definitions.rpc as defs
from infuse_iot.common import InfuseID
from infuse_iot.epacket import interface
from infuse_iot.gateway_control import LOCAL_IDLE_S, GatewayControl
from infuse_iot.socket_comms import (
    ClientNotificationConnectionCreated,
    ClientNotificationConnectionDropped,
    ClientNotificationConnectionFailed,
    GatewayRequestConnectionRelease,
    GatewayRequestConnectionRequest,
    GatewayRequestControl,
    LocalServer,
)
from infuse_iot.tools.gateway import SerialTxThread, SubCommand

DEVICE = 123
GATEWAY = 1


def make_tx(server=None):
    ddb = Mock()
    ddb.gateway = GATEWAY
    ddb.has_local_root = False
    ddb.has_shared_key.return_value = True
    ddb.devices = {DEVICE: SimpleNamespace(bt_addr=interface.Address.BluetoothLeAddr(0, 0x010203040506))}
    ddb.infuse_id_from_bluetooth.return_value = DEVICE
    common = Mock(ddb=ddb)
    if server is not None:
        common.server = server
        common.notification_broadcast.side_effect = server.broadcast
    common.rpc.generate_serial.return_value.to_serial.return_value = b"frame"
    common.rpc.generate_remote_bt.return_value.to_serial.return_value = b"frame"
    thread = SerialTxThread(common)
    return thread


@pytest.fixture
def tx():
    return make_tx()


def request(tx, request_id):
    tx._handle_conn_request(
        GatewayRequestConnectionRequest(DEVICE, GatewayRequestConnectionRequest.DataType.DATA, 10, request_id)
    )


def release(tx, request_id):
    tx._handle_conn_release(GatewayRequestConnectionRelease(DEVICE, request_id))


def complete(tx, request_id=None, rc=0):
    tx._bt_connect_cb(Mock(), rc, bytes(defs.bt_connect_infuse.response()), request_id)


def disconnects(tx):
    calls = tx._common.rpc.generate_serial.call_args_list
    return [call for call in calls if call.args[0] == defs.bt_disconnect.COMMAND_ID]


def broadcasts(tx):
    return [call.args[0] for call in tx._common.notification_broadcast.call_args_list]


def notifications(tx):
    return [type(notification) for notification in broadcasts(tx)]


def test_results_identify_the_request(tx):
    request(tx, 1)
    complete(tx, 1)
    request(tx, 2)
    complete(tx, 2, rc=-1)
    created, failed = broadcasts(tx)
    assert isinstance(created, ClientNotificationConnectionCreated) and created.request_id == 1
    assert isinstance(failed, ClientNotificationConnectionFailed) and failed.request_id == 2


def test_release_of_pending_request_keeps_existing_user_connected(tx):
    request(tx, 1)
    complete(tx, 1)
    # A second client times out while its request is pending and releases it.
    request(tx, 2)
    release(tx, 2)
    assert not disconnects(tx)
    complete(tx, 2)
    assert tx._connected == {DEVICE: Counter({1: 1})}
    assert not tx._pending and not tx._cancelled
    # The original user still owns the connection and is the last to release it.
    release(tx, 1)
    assert len(disconnects(tx)) == 1
    assert not tx._connected


def test_late_success_after_release_disconnects_unowned_connection(tx):
    request(tx, 1)
    release(tx, 1)
    complete(tx, 1)
    assert not tx._connected
    assert len(disconnects(tx)) == 1
    assert ClientNotificationConnectionCreated not in notifications(tx)


def test_failed_cancelled_request_keeps_existing_user_connected(tx):
    request(tx, 1)
    complete(tx, 1)
    request(tx, 2)
    # The second client gives up on its request, which then fails.
    release(tx, 2)
    complete(tx, 2, rc=-1)
    assert notifications(tx)[-1] is ClientNotificationConnectionFailed
    assert tx._connected == {DEVICE: Counter({1: 1})}
    assert not disconnects(tx)


def test_release_by_existing_user_keeps_connection_for_pending_request(tx):
    request(tx, 1)
    complete(tx, 1)
    request(tx, 2)
    release(tx, 1)
    assert not disconnects(tx)
    complete(tx, 2)
    assert tx._connected == {DEVICE: Counter({2: 1})}
    assert broadcasts(tx)[-1].request_id == 2
    release(tx, 2)
    assert len(disconnects(tx)) == 1


def test_failed_request_disconnects_connection_kept_open_for_it(tx):
    request(tx, 1)
    complete(tx, 1)
    request(tx, 2)
    release(tx, 1)
    complete(tx, 2, rc=-1)
    assert not tx._connected
    assert len(disconnects(tx)) == 1


def test_connection_without_users_subscribes_requested_characteristics(tx):
    request(tx, 1)
    complete(tx, 1)
    request(tx, 2)
    # The connection is kept open for the pending request, without any users.
    release(tx, 1)
    request(tx, 3)
    connect_args = tx._common.rpc.generate_serial.call_args.args[1]
    subscribe = defs.bt_connect_infuse.request.from_buffer_copy(connect_args).subscribe
    assert subscribe == defs.rpc_enum_infuse_bt_characteristic.DATA


def test_release_of_unknown_request_is_ignored(tx):
    request(tx, 1)
    complete(tx, 1)
    release(tx, 2)
    assert tx._connected == {DEVICE: Counter({1: 1})}
    assert not disconnects(tx)


def test_release_during_key_query_suppresses_success(tx):
    tx._common.ddb.has_shared_key.return_value = False
    request(tx, 1)
    complete(tx, 1)
    on_key_query = tx._common.query_device_key.call_args.kwargs["cb"]
    # The only user gives up while the device key is being queried.
    release(tx, 1)
    on_key_query(True, None)
    assert len(disconnects(tx)) == 1
    assert ClientNotificationConnectionCreated not in notifications(tx)


def test_release_during_public_key_query_suppresses_success(tx):
    tx._common.ddb.has_local_root = True
    request(tx, 1)
    complete(tx, 1)
    release(tx, 1)
    tx._pub_keys_cb(SimpleNamespace(route=[SimpleNamespace(infuse_id=DEVICE)]), -1, b"", 1)
    assert len(disconnects(tx)) == 1
    assert ClientNotificationConnectionCreated not in notifications(tx)


class Inbox(deque):
    """Requests waiting at the server's input socket."""

    def recvfrom(self, _size):
        if not self:
            raise TimeoutError
        return self.popleft(), ("localhost", 1)


class ObservingServer(LocalServer):
    """A `LocalServer` whose sockets are replaced by an inbox of requests and a list of sent notifications."""

    def __init__(self):
        self.sent: list = []
        self.inbox = Inbox()
        self.control = GatewayControl(self._broadcast_raw)
        self._pending_control = []
        self._input_sock: Any = self.inbox

    def _broadcast_raw(self, notification):
        self.sent.append(notification)


@pytest.fixture
def owned():
    return make_tx(ObservingServer())


def deliver(tx, request, owner=None):
    """Send a request to the server and run the transmit loop until it and any cleanup it caused are handled."""
    values = request.to_json()
    if owner is not None:
        values["operation_id"] = owner
    server = tx._common.server
    server.inbox.append(json.dumps(values).encode())
    # A rejected request ends one pass of the loop, so run another for cleanup queued by its expiry check.
    while server.inbox or server._pending_control:
        tx._iter()
    tx._iter()
    return server.sent[-1] if server.sent else None


def connection(device):
    return GatewayRequestConnectionRequest(device, GatewayRequestConnectionRequest.DataType.COMMAND, 1000)


def acquire(tx, owner, device):
    parameters = {"device_id": f"0x{device:016x}", "owner": owner}
    return deliver(tx, GatewayRequestControl("acquire_operation", parameters))


def test_operation_on_gateway_device_needs_no_teardown(owned):
    assert acquire(owned, "A", GATEWAY).ok
    created = deliver(owned, connection(GATEWAY), "A")
    assert isinstance(created, ClientNotificationConnectionCreated)
    assert created.operation_id == "A"
    deliver(owned, GatewayRequestConnectionRelease(GATEWAY), "A")
    assert deliver(owned, GatewayRequestControl("release_operation", {"owner": "A"})).ok
    # The gateway never reports its own device dropped.
    assert acquire(owned, "B", DEVICE).ok
    assert not disconnects(owned)


def test_killed_legacy_client_of_gateway_device_expires(owned, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("infuse_iot.gateway_control.time.monotonic", lambda: clock[0])
    deliver(owned, connection(InfuseID.GATEWAY))
    assert acquire(owned, "A", DEVICE).code == "device_busy"
    clock[0] = LOCAL_IDLE_S
    assert acquire(owned, "A", DEVICE).ok


def test_deferred_legacy_release_does_not_disconnect_new_owner(owned):
    # A client stops waiting for its pending connection and releases it.
    deliver(owned, connection(DEVICE))
    deliver(owned, GatewayRequestConnectionRelease(DEVICE))
    assert acquire(owned, "A", DEVICE).code == "device_busy"
    # The connection completes and the deferred release disconnects it, which the gateway later reports.
    complete(owned)
    assert len(disconnects(owned)) == 1
    owned._connection_dropped(DEVICE)
    owned._common.notification_broadcast(ClientNotificationConnectionDropped(DEVICE))
    assert acquire(owned, "A", DEVICE).ok
    deliver(owned, connection(DEVICE), "A")
    complete(owned)
    created = owned._common.server.sent[-1]
    assert isinstance(created, ClientNotificationConnectionCreated)
    assert created.operation_id == "A"
    assert owned._connected == {DEVICE: Counter({None: 1})}
    assert len(disconnects(owned)) == 1
    deliver(owned, GatewayRequestConnectionRelease(DEVICE), "A")
    assert len(disconnects(owned)) == 2


def make_command(log=None):
    command = object.__new__(SubCommand)
    command.port = Mock()
    command.log = log
    command.server = Mock()
    command._threads = []
    return command


def test_close_waits_for_threads_before_closing_server_and_log():
    log = Mock()
    command = make_command(log)
    thread = Mock()
    thread.is_alive.return_value = False
    command._threads = [thread]
    command.close()
    command.port.close.assert_called_once()
    thread.join.assert_called_once_with(command.THREAD_EXIT_TIMEOUT_S)
    log.close.assert_called_once()
    command.server.close.assert_called_once()


def test_close_leaves_resources_open_for_running_threads():
    log = Mock()
    command = make_command(log)
    thread = Mock()
    thread.name = "rx"
    thread.is_alive.return_value = True
    command._threads = [thread]
    command.close()
    command.port.close.assert_called_once()
    log.close.assert_not_called()
    command.server.close.assert_not_called()


@pytest.mark.parametrize("established", [False, True])
def test_operation_cleanup_releases_identified_serial_request(owned, established):
    assert acquire(owned, "A", DEVICE).ok
    request = connection(DEVICE)
    request.request_id = 7
    deliver(owned, request, "A")
    if established:
        complete(owned, 7)
    assert deliver(owned, GatewayRequestControl("release_operation", {"owner": "A"})).ok
    if not established:
        complete(owned, 7)
    assert not owned._connected and not owned._pending
    assert len(disconnects(owned)) == 1


def test_legacy_request_pending_at_drop_stays_tracked(owned):
    first, second = connection(DEVICE), connection(DEVICE)
    first.request_id, second.request_id = 1, 2
    deliver(owned, first)
    complete(owned, 1)
    deliver(owned, second)
    # The link drops while the second request's connection is pending, which then connects.
    owned._connection_dropped(DEVICE)
    owned._common.notification_broadcast(ClientNotificationConnectionDropped(DEVICE))
    complete(owned, 2)
    assert owned._connected == {DEVICE: Counter({2: 1})}
    assert acquire(owned, "A", GATEWAY).code == "device_busy"
    deliver(owned, GatewayRequestConnectionRelease(DEVICE, 2))
    assert len(disconnects(owned)) == 1
    owned._connection_dropped(DEVICE)
    owned._common.notification_broadcast(ClientNotificationConnectionDropped(DEVICE))
    assert acquire(owned, "A", GATEWAY).ok


def test_failed_setup_of_released_request_ends_closing(owned):
    request = connection(DEVICE)
    request.request_id = 1
    deliver(owned, request)
    # The client stops waiting for its connection, whose setup then fails.
    deliver(owned, GatewayRequestConnectionRelease(DEVICE, 1))
    assert acquire(owned, "A", DEVICE).code == "device_busy"
    complete(owned, 1, rc=-1)
    assert not disconnects(owned)
    assert acquire(owned, "A", DEVICE).ok
