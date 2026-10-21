from types import SimpleNamespace
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


def request(tx):
    tx._handle_conn_request(GatewayRequestConnectionRequest(DEVICE, GatewayRequestConnectionRequest.DataType.DATA, 10))


def complete(tx, rc=0):
    tx._bt_connect_cb(Mock(), rc, bytes(defs.bt_connect_infuse.response()), None)


def disconnects(tx):
    calls = tx._common.rpc.generate_serial.call_args_list
    return [call for call in calls if call.args[0] == defs.bt_disconnect.COMMAND_ID]


def notifications(tx):
    return [type(call.args[0]) for call in tx._common.notification_broadcast.call_args_list]


def test_release_of_pending_request_keeps_existing_user_connected(tx):
    request(tx)
    complete(tx)
    # A second client times out while its request is pending and releases it.
    request(tx)
    tx._handle_conn_release(GatewayRequestConnectionRelease(DEVICE))
    assert not disconnects(tx)
    complete(tx)
    assert tx._connected == {DEVICE: 1}
    assert not tx._pending and not tx._deferred_releases
    # The original user still owns the connection and is the last to release it.
    tx._handle_conn_release(GatewayRequestConnectionRelease(DEVICE))
    assert len(disconnects(tx)) == 1
    assert not tx._connected


def test_late_success_after_release_disconnects_unowned_connection(tx):
    request(tx)
    tx._handle_conn_release(GatewayRequestConnectionRelease(DEVICE))
    complete(tx)
    assert not tx._connected
    assert len(disconnects(tx)) == 1
    assert ClientNotificationConnectionCreated not in notifications(tx)


def test_failed_pending_request_applies_deferred_release_to_existing_user(tx):
    request(tx)
    complete(tx)
    request(tx)
    # Users are interchangeable: this may be the existing user releasing while the request is pending.
    tx._handle_conn_release(GatewayRequestConnectionRelease(DEVICE))
    complete(tx, rc=-1)
    assert notifications(tx)[-1] is ClientNotificationConnectionFailed
    assert not tx._connected
    assert len(disconnects(tx)) == 1


def test_release_during_key_query_suppresses_success(tx):
    tx._common.ddb.has_shared_key.return_value = False
    request(tx)
    complete(tx)
    on_key_query = tx._common.query_device_key.call_args.kwargs["cb"]
    # The only user gives up while the device key is being queried.
    tx._handle_conn_release(GatewayRequestConnectionRelease(DEVICE))
    on_key_query(True, None)
    assert len(disconnects(tx)) == 1
    assert ClientNotificationConnectionCreated not in notifications(tx)


def test_release_during_public_key_query_suppresses_success(tx):
    tx._common.ddb.has_local_root = True
    request(tx)
    complete(tx)
    tx._handle_conn_release(GatewayRequestConnectionRelease(DEVICE))
    tx._pub_keys_cb(SimpleNamespace(route=[SimpleNamespace(infuse_id=DEVICE)]), -1, b"", None)
    assert len(disconnects(tx)) == 1
    assert ClientNotificationConnectionCreated not in notifications(tx)


class ObservingServer:
    """Updates gateway control from each broadcast, as `LocalServer` does."""

    def __init__(self):
        self.sent: list = []
        self.control = GatewayControl(self.sent.append)

    def broadcast(self, notification):
        self.control.observe(notification)
        self.sent.append(notification)


@pytest.fixture
def owned():
    return make_tx(ObservingServer())


def deliver(tx, request, owner=None):
    """Authorize and handle a request, as `LocalServer.receive` and the transmit thread do."""
    request.operation_id = owner
    control = tx._common.server.control
    if control.accept(request):
        if isinstance(request, GatewayRequestConnectionRequest):
            tx._handle_conn_request(request)
        elif isinstance(request, GatewayRequestConnectionRelease):
            tx._handle_conn_release(request)
    for release in control.cleanup():
        tx._handle_conn_release(release)
    return tx._common.server.sent[-1] if tx._common.server.sent else None


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
    assert owned._connected == {DEVICE: 1}
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
