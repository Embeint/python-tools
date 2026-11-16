from collections import Counter
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
from infuse_iot.tools.gateway import SerialTxThread, SubCommand

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


def request(tx, request_id):
    tx._handle_conn_request(
        GatewayRequestConnectionRequest(DEVICE, GatewayRequestConnectionRequest.DataType.DATA, 10, request_id)
    )


def release(tx, request_id):
    tx._handle_conn_release(GatewayRequestConnectionRelease(DEVICE, request_id))


def complete(tx, request_id, rc=0):
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


def test_announce_updates_application_state():
    from infuse_iot.database import DeviceDatabase
    from infuse_iot.definitions.tdf import readings
    from infuse_iot.tools.gateway import SerialRxThread

    ddb = DeviceDatabase(None)
    rx = SerialRxThread(Mock(ddb=ddb, server=None), Mock(), Mock())
    announce = readings.announce_v2()
    announce.application = 0x12345678
    announce.version.major = 1
    announce.version.minor = 2
    announce.version.revision = 3
    announce.version.build_num = 0xABCD
    rx._tdf_decoder = Mock()
    rx._tdf_decoder.decode.return_value = [SimpleNamespace(data=[announce])]
    # Announce relayed through the gateway is attributed to the original source
    rx._handle_tdf(
        Mock(route=[SimpleNamespace(infuse_id=DEVICE, interface=interface.ID.BT_ADV), SimpleNamespace(infuse_id=1)])
    )
    state = ddb.devices[DEVICE]
    assert state.application_id == 0x12345678
    assert state.application_version == "1.2.3+0000abcd"


def test_known_devices_reports_activity_and_application(tx):
    from infuse_iot.database import DeviceDatabase
    from infuse_iot.definitions.tdf import readings
    from infuse_iot.socket_comms import ClientNotification, ClientNotificationObservedDevices

    ddb = DeviceDatabase(None)
    ddb.observe_device(1, network_id=5)
    ddb.observe_heard(1, 100.0)
    ddb.observe_heard(DEVICE, 200.5)
    announce = readings.announce()
    announce.application = 0x12345678
    announce.version.major = 1
    announce.version.minor = 2
    announce.version.revision = 3
    announce.version.build_num = 0xABCD
    ddb.observe_announce(DEVICE, announce)
    tx._common.ddb = ddb
    tx._handle_observed_devices()
    (notification,) = broadcasts(tx)
    # Values survive the JSON round trip to clients
    decoded = ClientNotification.from_json(notification.to_json())
    assert isinstance(decoded, ClientNotificationObservedDevices)
    assert decoded.devices == {
        1: {"network_id": 5, "last_heard": 100.0, "gateway": True},
        DEVICE: {"last_heard": 200.5, "application_id": 0x12345678, "application_version": "1.2.3+0000abcd"},
    }


RELAY = 456
RELAY_ADDR = interface.Address.BluetoothLeAddr(0, 0x0A0B0C0D0E0F)


@pytest.fixture
def relay_tx(tx, monkeypatch):
    # Timeouts waiting for relays to disconnect from devices are run explicitly
    tx.relay_disconnect_timer = Mock()
    monkeypatch.setattr("infuse_iot.tools.gateway.threading.Timer", tx.relay_disconnect_timer)
    ddb = tx._common.ddb
    ddb.devices[RELAY] = SimpleNamespace(bt_addr=RELAY_ADDR)
    ddb.infuse_id_from_bluetooth.side_effect = lambda addr: RELAY if addr == RELAY_ADDR else DEVICE
    tx._common.rpc.generate_addressed.return_value.to_serial.return_value = b"frame"
    return tx


def relay_request(tx, request_id, relay=RELAY):
    tx._handle_conn_request(
        GatewayRequestConnectionRequest(
            DEVICE, GatewayRequestConnectionRequest.DataType.COMMAND, 10, request_id, relay=relay
        )
    )


def relay_complete(tx, request_id, rc=0):
    """Gateway connection to the relay completes"""
    response = defs.bt_connect_infuse.response()
    response.peer = RELAY_ADDR.to_rpc_struct()
    tx._bt_connect_cb(Mock(), rc, bytes(response), request_id)


def relay_rpcs(tx, command_id):
    calls = tx._common.rpc.generate_addressed.call_args_list
    return [call for call in calls if call.args[0] == RELAY and call.args[1] == command_id]


def device_complete(tx, rc=0):
    """Relay connection to the device completes"""
    connect = relay_rpcs(tx, defs.bt_connect_infuse.COMMAND_ID)[-1]
    tx._relay_connect_cb(Mock(), rc, bytes(defs.bt_connect_infuse.response()), connect.args[5])


def relay_disconnect_complete(tx, timeout=False):
    """Relay responds to the request to disconnect from the device, or the response times out"""
    if timeout:
        tx.relay_disconnect_timer.call_args.args[1]()
    else:
        disconnect = relay_rpcs(tx, defs.bt_disconnect.COMMAND_ID)[-1]
        disconnect.args[4](Mock(), 0, b"", disconnect.args[5])


def relay_state_clear(tx):
    return not (tx._connected or tx._pending or tx._cancelled or tx._relay_requests or tx._relay_users) and not (
        tx._relay_routes
    )


def test_relayed_connection_lifecycle(relay_tx):
    relay_request(relay_tx, 1)
    # Gateway connects to the relay first
    relay_args = defs.bt_connect_infuse.request.from_buffer_copy(relay_tx._common.rpc.generate_serial.call_args.args[1])
    assert interface.Address.BluetoothLeAddr.from_rpc_struct(relay_args.peer) == RELAY_ADDR
    bt_char = defs.rpc_enum_infuse_bt_characteristic
    assert relay_args.subscribe == bt_char.COMMAND | bt_char.DATA
    relay_complete(relay_tx, 1)
    assert not broadcasts(relay_tx)
    # Then the relay connects to the device
    (connect,) = relay_rpcs(relay_tx, defs.bt_connect_infuse.COMMAND_ID)
    device_args = defs.bt_connect_infuse.request.from_buffer_copy(connect.args[2])
    assert (
        interface.Address.BluetoothLeAddr.from_rpc_struct(device_args.peer)
        == relay_tx._common.ddb.devices[DEVICE].bt_addr
    )
    device_complete(relay_tx)
    (created,) = broadcasts(relay_tx)
    assert isinstance(created, ClientNotificationConnectionCreated)
    assert created.infuse_id == DEVICE and created.request_id == 1
    assert created.max_payload == SerialTxThread.RELAYED_MAX_PAYLOAD
    # Releasing the device disconnects it from the relay, then disconnects the relay
    release(relay_tx, 1)
    assert len(relay_rpcs(relay_tx, defs.bt_disconnect.COMMAND_ID)) == 1
    assert not disconnects(relay_tx)
    relay_disconnect_complete(relay_tx)
    assert len(disconnects(relay_tx)) == 1
    assert relay_state_clear(relay_tx)
    # Late timeouts have no effect
    relay_disconnect_complete(relay_tx, timeout=True)
    assert len(disconnects(relay_tx)) == 1


def test_relay_released_if_device_disconnect_times_out(relay_tx):
    relay_request(relay_tx, 1)
    relay_complete(relay_tx, 1)
    device_complete(relay_tx)
    release(relay_tx, 1)
    assert not disconnects(relay_tx)
    relay_disconnect_complete(relay_tx, timeout=True)
    assert len(disconnects(relay_tx)) == 1
    assert relay_state_clear(relay_tx)
    # Late responses have no effect
    relay_disconnect_complete(relay_tx)
    assert len(disconnects(relay_tx)) == 1


def test_relayed_connection_requires_request_id(relay_tx):
    relay_request(relay_tx, None)
    (failed,) = broadcasts(relay_tx)
    assert isinstance(failed, ClientNotificationConnectionFailed)
    assert not relay_tx._common.rpc.generate_serial.called
    assert relay_state_clear(relay_tx)


def test_relayed_device_key_is_queried_through_relay(relay_tx):
    relay_tx._common.ddb.has_shared_key.side_effect = lambda infuse_id: infuse_id != DEVICE
    relay_request(relay_tx, 1)
    relay_complete(relay_tx, 1)
    device_complete(relay_tx)
    query = relay_tx._common.query_device_key.call_args
    assert query.args[0] == DEVICE and query.kwargs["relay"] == RELAY
    query.kwargs["cb"](True, None)
    assert notifications(relay_tx) == [ClientNotificationConnectionCreated]


def test_failed_relayed_connection_releases_relay(relay_tx):
    relay_request(relay_tx, 1)
    relay_complete(relay_tx, 1)
    device_complete(relay_tx, rc=-1)
    (failed,) = broadcasts(relay_tx)
    assert isinstance(failed, ClientNotificationConnectionFailed)
    assert failed.infuse_id == DEVICE and failed.request_id == 1
    assert len(disconnects(relay_tx)) == 1
    assert relay_state_clear(relay_tx)


def test_failed_relay_connection_fails_device_request(relay_tx):
    relay_request(relay_tx, 1)
    relay_complete(relay_tx, 1, rc=-1)
    (failed,) = broadcasts(relay_tx)
    assert isinstance(failed, ClientNotificationConnectionFailed)
    assert failed.infuse_id == DEVICE and failed.request_id == 1
    assert not relay_rpcs(relay_tx, defs.bt_connect_infuse.COMMAND_ID)
    assert relay_state_clear(relay_tx)


def test_release_while_connecting_to_relay(relay_tx):
    relay_request(relay_tx, 1)
    release(relay_tx, 1)
    assert not disconnects(relay_tx)
    relay_complete(relay_tx, 1)
    # The relay is not asked to connect to the device, and is disconnected
    assert not relay_rpcs(relay_tx, defs.bt_connect_infuse.COMMAND_ID)
    assert len(disconnects(relay_tx)) == 1
    assert not broadcasts(relay_tx)
    assert relay_state_clear(relay_tx)


def test_release_while_relay_connects_to_device(relay_tx):
    relay_request(relay_tx, 1)
    relay_complete(relay_tx, 1)
    release(relay_tx, 1)
    device_complete(relay_tx)
    assert len(relay_rpcs(relay_tx, defs.bt_disconnect.COMMAND_ID)) == 1
    relay_disconnect_complete(relay_tx)
    assert len(disconnects(relay_tx)) == 1
    assert not broadcasts(relay_tx)
    assert relay_state_clear(relay_tx)


def test_relayed_connection_shared_by_requests(relay_tx):
    for request_id in (1, 2):
        relay_request(relay_tx, request_id)
        relay_complete(relay_tx, request_id)
        device_complete(relay_tx)
    release(relay_tx, 1)
    assert not disconnects(relay_tx) and not relay_rpcs(relay_tx, defs.bt_disconnect.COMMAND_ID)
    release(relay_tx, 2)
    relay_disconnect_complete(relay_tx)
    assert len(disconnects(relay_tx)) == 1
    assert relay_state_clear(relay_tx)


def test_relayed_device_cannot_use_other_routes(relay_tx):
    relay_request(relay_tx, 1)
    relay_complete(relay_tx, 1)
    device_complete(relay_tx)
    # Direct connection
    request(relay_tx, 2)
    # Connection through another relay
    relay_tx._common.ddb.devices[789] = SimpleNamespace(bt_addr=interface.Address.BluetoothLeAddr(0, 0x01))
    relay_request(relay_tx, 3, relay=789)
    created, direct, other = broadcasts(relay_tx)
    assert isinstance(direct, ClientNotificationConnectionFailed) and direct.request_id == 2
    assert isinstance(other, ClientNotificationConnectionFailed) and other.request_id == 3


def test_directly_connected_device_cannot_be_relayed(relay_tx):
    request(relay_tx, 1)
    complete(relay_tx, 1)
    relay_request(relay_tx, 2)
    created, failed = broadcasts(relay_tx)
    assert isinstance(failed, ClientNotificationConnectionFailed) and failed.request_id == 2


def test_relay_disconnect_drops_relayed_devices(relay_tx):
    relay_request(relay_tx, 1)
    relay_complete(relay_tx, 1)
    device_complete(relay_tx)
    assert relay_tx._connection_dropped(RELAY) == [RELAY, DEVICE]
    assert not relay_tx._connected
    # The client releases the dropped connection through the relay
    release(relay_tx, 1)
    assert len(relay_rpcs(relay_tx, defs.bt_disconnect.COMMAND_ID)) == 1
    assert relay_state_clear(relay_tx)


def test_device_disconnect_reported_by_relay(relay_tx):
    relay_request(relay_tx, 1)
    relay_complete(relay_tx, 1)
    device_complete(relay_tx)
    # Reports from other relays are ignored
    assert relay_tx._connection_dropped(DEVICE, 789) == []
    assert relay_tx._connection_dropped(DEVICE, RELAY) == [DEVICE]
    assert RELAY in relay_tx._connected and DEVICE not in relay_tx._connected
    # The client releases the dropped connection, which releases the relay
    release(relay_tx, 1)
    assert len(relay_rpcs(relay_tx, defs.bt_disconnect.COMMAND_ID)) == 1
    relay_disconnect_complete(relay_tx)
    assert len(disconnects(relay_tx)) == 1
    assert relay_state_clear(relay_tx)


def test_relayed_packets_are_routed_through_relay(relay_tx, monkeypatch):
    from infuse_iot.common import InfuseType
    from infuse_iot.epacket.packet import Auth, PacketOutput
    from infuse_iot.socket_comms import GatewayRequestEpacketSend

    routed = Mock()
    routed.return_value.route = []
    routed.return_value.to_serial.return_value = b"frame"
    monkeypatch.setattr("infuse_iot.tools.gateway.PacketOutputRouted", routed)
    pkt = PacketOutput(DEVICE, Auth.NETWORK, InfuseType.RPC_CMD, b"\x01", relay=RELAY)
    relay_tx._handle_epacket_send(GatewayRequestEpacketSend(pkt))
    route = routed.call_args.args[0]
    assert [(hop.infuse_id, hop.interface) for hop in route] == [
        (1, interface.ID.SERIAL),
        (RELAY, interface.ID.BT_CENTRAL),
        (DEVICE, interface.ID.BT_CENTRAL),
    ]
    assert route[-1].auth == Auth.NETWORK
