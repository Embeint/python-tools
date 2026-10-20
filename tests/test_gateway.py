from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import infuse_iot.definitions.rpc as defs
from infuse_iot.epacket import interface
from infuse_iot.socket_comms import (
    ClientNotificationConnectionCreated,
    ClientNotificationConnectionFailed,
    GatewayRequestConnectionRelease,
    GatewayRequestConnectionRequest,
)
from infuse_iot.tools.gateway import SerialTxThread

DEVICE = 123


@pytest.fixture
def tx():
    ddb = Mock()
    ddb.gateway = 1
    ddb.has_local_root = False
    ddb.has_shared_key.return_value = True
    ddb.devices = {DEVICE: SimpleNamespace(bt_addr=interface.Address.BluetoothLeAddr(0, 0x010203040506))}
    ddb.infuse_id_from_bluetooth.return_value = DEVICE
    common = Mock(ddb=ddb)
    common.rpc.generate_serial.return_value.to_serial.return_value = b"frame"
    common.rpc.generate_remote_bt.return_value.to_serial.return_value = b"frame"
    thread = SerialTxThread(common)
    return thread


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
