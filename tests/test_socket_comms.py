#!/usr/bin/env python3

import os
import threading
from unittest.mock import Mock

import pytest

import infuse_iot.socket_comms as comms

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def test_socket_comms():
    # Ensure notifications can be sent from the server to the client, and requests sent in reverse
    multicast_addr = comms.default_multicast_address()
    # Increment port by 1 so we can run the tests in parallel with a real instance
    test_addr = (multicast_addr[0], multicast_addr[1] + 1)

    # Create the server first
    server = comms.LocalServer(test_addr)

    # Send a message before any client is connected
    broadcast_msg = comms.ClientNotificationObservedDevices({})
    server.broadcast(broadcast_msg)

    # Create a client that receives from the server, shouldn't receive the broadcast message
    client = comms.LocalClient(test_addr)
    assert client.receive() is None

    # Send request to server
    request = comms.GatewayRequestCommsCheck()
    client.send(request)

    # Server receives request, responds
    recv_req = server.receive()
    assert isinstance(recv_req, comms.GatewayRequestCommsCheck)
    response = comms.ClientNotificationCommsCheck()
    server.broadcast(response)

    # Client receives the response
    recv_rsp = client.receive()
    assert isinstance(recv_rsp, comms.ClientNotificationCommsCheck)
    client.close()
    server.close()


@pytest.fixture
def client(monkeypatch):
    client = comms.LocalClient.__new__(comms.LocalClient)
    client._connection_id = None
    monkeypatch.setattr(client, "send", Mock())
    monkeypatch.setattr(client, "receive", Mock())
    return client


def test_connection_ignores_other_devices(client):
    client.receive.side_effect = [
        comms.ClientNotificationConnectionFailed(999, "Other device failure"),
        comms.ClientNotificationConnectionCreated(999, 12),
        comms.ClientNotificationConnectionCreated(123, 128),
    ]
    with client.connection(123, comms.GatewayRequestConnectionRequest.DataType.COMMAND) as mtu:
        assert mtu == 128
    requests = [call.args[0] for call in client.send.call_args_list]
    assert len(requests) == 2
    assert isinstance(requests[1], comms.GatewayRequestConnectionRelease)
    assert requests[1].infuse_id == 123


def test_rejected_connection_is_not_released(client):
    client.receive.return_value = comms.ClientNotificationConnectionFailed(123, "Device key query failed")
    with (
        pytest.raises(ConnectionRefusedError, match="Device key query failed"),
        client.connection(123, comms.GatewayRequestConnectionRequest.DataType.DATA),
    ):
        pytest.fail("Rejected connection must not enter the context")
    assert client._connection_id is None
    assert client.send.call_count == 1


def test_connection_timeout_cancels_pending_request(client, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(comms.time, "monotonic", lambda: clock[0])

    def receive(timeout):
        clock[0] += timeout
        return None

    client.receive.side_effect = receive
    with pytest.raises(TimeoutError):
        client.connection_create(123, comms.GatewayRequestConnectionRequest.DataType.DATA, 50)
    # Gateways may finish security setup after the Bluetooth connection timeout.
    assert clock[0] == pytest.approx(0.05 + client.CONNECTION_RESPONSE_MARGIN_S)
    assert client._connection_id is None
    assert isinstance(client.send.call_args.args[0], comms.GatewayRequestConnectionRelease)


def test_receive_deadline_leaves_shared_socket_timeout_unchanged(monkeypatch):
    client = comms.LocalClient.__new__(comms.LocalClient)
    client._input_sock = Mock()
    client._rx_lock = threading.Lock()
    client._input_sock.gettimeout.return_value = 1.0
    select = Mock(return_value=([], [], []))
    monkeypatch.setattr(comms.select, "select", select)
    assert client.receive(timeout=0.05) is None
    assert 0 < select.call_args.args[3] <= 0.05
    client._input_sock.settimeout.assert_not_called()
    client._input_sock.recvfrom.assert_not_called()


def test_receive_deadline_is_capped_by_socket_timeout(monkeypatch):
    client = comms.LocalClient.__new__(comms.LocalClient)
    client._input_sock = Mock()
    client._rx_lock = threading.Lock()
    client._input_sock.gettimeout.return_value = 0.2
    select = Mock(return_value=([], [], []))
    monkeypatch.setattr(comms.select, "select", select)
    assert client.receive(timeout=5.0) is None
    assert select.call_args.args[3] == 0.2


def test_receive_deadline_waits_for_concurrent_reader(monkeypatch):
    # A reader holding the socket could consume the datagram that select reported.
    client = comms.LocalClient.__new__(comms.LocalClient)
    client._input_sock = Mock()
    client._rx_lock = threading.Lock()
    select = Mock(return_value=([client._input_sock], [], []))
    monkeypatch.setattr(comms.select, "select", select)
    with client._rx_lock:
        assert client.receive(timeout=0.05) is None
    select.assert_not_called()
    client._input_sock.recvfrom.assert_not_called()


def test_client_close_releases_zero_id_and_closes_both_sockets(client):
    client._connection_id = 0
    client._input_sock = Mock()
    client._output_sock = Mock()
    client.send.side_effect = OSError
    with pytest.raises(OSError):
        client.close()
    assert client.send.call_args.args[0].infuse_id == 0
    client._input_sock.close.assert_called_once()
    client._output_sock.close.assert_called_once()


def test_connection_failed_notification_json_round_trip():
    notification = comms.ClientNotificationConnectionFailed(0x0123456789ABCDEF, "Failed to query device shared keys")

    decoded = comms.ClientNotification.from_json(notification.to_json())

    assert isinstance(decoded, comms.ClientNotificationConnectionFailed)
    assert decoded.infuse_id == notification.infuse_id
    assert decoded.reason == notification.reason
