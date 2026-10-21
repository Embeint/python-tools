#!/usr/bin/env python3

import json
import os
import threading
from unittest.mock import Mock

import pytest

import infuse_iot.socket_comms as comms
from infuse_iot.common import InfuseID
from infuse_iot.gateway_control import GatewayControl

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
    client._operation_id = None
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
    assert 0 < select.call_args.args[3] <= 0.2


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


def undecodable_client(monkeypatch, datagrams):
    client = comms.LocalClient.__new__(comms.LocalClient)
    client._input_sock = Mock()
    client._rx_lock = threading.Lock()
    client.ignored_notifications = 0
    client._input_sock.gettimeout.return_value = 0.2
    pending = list(datagrams)
    client._input_sock.recvfrom.side_effect = lambda size: (pending.pop(0), None)
    select = Mock(side_effect=lambda *args: ([client._input_sock] if pending else [], [], []))
    monkeypatch.setattr(comms.select, "select", select)
    return client, select


def test_receive_skips_unknown_and_malformed_notifications(monkeypatch):
    # Gateway notifications are additive, so a newer gateway must not abort an older client's wait.
    reply = comms.ClientNotificationCommsCheck({"protocol_version": 2, "features": []}, "probe")
    datagrams = [b"\xffnot json", b"[]", json.dumps({"type": 99}).encode(), json.dumps({"type": 0}).encode()]
    client, _ = undecodable_client(monkeypatch, [*datagrams, json.dumps(reply.to_json()).encode()])
    received = client.receive(timeout=1.0)
    assert isinstance(received, comms.ClientNotificationCommsCheck)
    assert received.capabilities == reply.capabilities
    assert client.ignored_notifications == len(datagrams)


@pytest.mark.parametrize("timeout", [None, 0.05])
def test_receive_ends_at_deadline_after_undecodable_notifications(monkeypatch, timeout):
    client, select = undecodable_client(monkeypatch, [json.dumps({"type": 99}).encode()])
    assert client.receive(timeout=timeout) is None
    assert client.ignored_notifications == 1
    waits = [call.args[3] for call in select.call_args_list]
    assert len(waits) == 2 and all(0 <= wait <= (timeout or 0.2) for wait in waits)


def test_capability_probe_survives_unknown_gateway_notifications():
    address = comms.default_multicast_address(28853)
    server = comms.LocalServer(address)
    stop = threading.Event()
    reply = server.control._broadcast

    def broadcast(notification):
        if isinstance(notification, comms.ClientNotificationCommsCheck):
            # A newer gateway announces something this client has never heard of first.
            server._output_sock.sendto(json.dumps({"type": 42}).encode(), server._output_addr)
            server._output_sock.sendto(b"{truncated", server._output_addr)
        reply(notification)

    server.control._broadcast = broadcast

    def serve():
        while not stop.is_set():
            server.receive()

    thread = threading.Thread(target=serve)
    client = comms.LocalClient(address)
    thread.start()
    try:
        assert "operation_ownership" in client.capabilities(timeout=2.0)["features"]
        assert client.ignored_notifications == 2
    finally:
        client.close()
        stop.set()
        thread.join(timeout=2)
        server.close()
    assert not thread.is_alive()


def test_connection_dropped_matches_only_current_connection(client):
    assert not client.connection_dropped(comms.ClientNotificationConnectionDropped(123))
    client._connection_id = 123
    assert client.connection_dropped(comms.ClientNotificationConnectionDropped(123))
    assert not client.connection_dropped(comms.ClientNotificationConnectionDropped(999))
    assert not client.connection_dropped(comms.ClientNotificationConnectionCreated(123, 128))
    assert not client.connection_dropped(None)


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


def test_server_ignores_malformed_requests():
    server = comms.LocalServer.__new__(comms.LocalServer)
    server.control = GatewayControl(Mock())
    server._pending_control = []
    server._input_sock = Mock()
    malformed = [
        {"type": 0, "epacket": {"infuse_id": 1, "auth": 0, "type": 0, "payload": 5}},
        {"type": 0, "epacket": []},
        {"type": 9},
    ]
    for request in malformed:
        server._input_sock.recvfrom.return_value = (json.dumps(request).encode(), None)
        assert server.receive() is None


def test_control_request_reports_gateway_error(client):
    def reply(timeout):
        request = client.send.call_args.args[0]
        result = {"message": "Another operation is active"}
        return comms.ClientNotificationControl(request.request_id, False, result, "device_busy")

    client.receive.side_effect = reply
    with pytest.raises(comms.GatewayControlError) as error:
        client.control_request("acquire_operation", {})
    assert (error.value.code, error.value.message) == ("device_busy", "Another operation is active")
    # Callers comparing the code or catching `RuntimeError` are unaffected.
    assert str(error.value) == "device_busy"
    assert isinstance(error.value, RuntimeError)


def probe_replies(client, monkeypatch, replies):
    clock = [0.0]
    monkeypatch.setattr(comms.time, "monotonic", lambda: clock[0])

    def receive(timeout):
        if timeout == 0:
            # No stale notifications to discard
            return None
        clock[0] += 0.1
        return replies.pop(0) if replies else None

    client.receive.side_effect = receive
    return clock


def test_capability_probe_waits_past_other_clients_comms_checks(client, monkeypatch):
    capabilities = {"protocol_version": 2, "features": ["operation_ownership"]}
    replies = [comms.ClientNotificationCommsCheck(), comms.ClientNotificationCommsCheck(capabilities, "probe")]
    probe_replies(client, monkeypatch, replies)
    assert client.capabilities() == capabilities


def test_capability_probe_detects_legacy_gateway_at_deadline(client, monkeypatch):
    clock = probe_replies(client, monkeypatch, [comms.ClientNotificationCommsCheck()])
    assert client.capabilities(timeout=1.0) == {"protocol_version": 1, "features": []}
    assert clock[0] >= 1.0


def test_capability_probe_times_out_without_gateway(client, monkeypatch):
    probe_replies(client, monkeypatch, [])
    with pytest.raises(TimeoutError):
        client.capabilities()


def test_operation_rejects_gateway_alias(client):
    with pytest.raises(ValueError, match="InfuseID.GATEWAY"), client.operation(InfuseID.GATEWAY):
        pytest.fail("Operation acquired without a device ID")
    client.send.assert_not_called()


def test_capability_probe_ignores_buffered_comms_check_reply():
    address = comms.default_multicast_address(28851)
    server = comms.LocalServer(address)
    stop = threading.Event()

    def serve():
        # Answer ordinary comms checks as both gateways do.
        while not stop.is_set():
            if isinstance(server.receive(), comms.GatewayRequestCommsCheck):
                server.broadcast(comms.ClientNotificationCommsCheck())

    thread = threading.Thread(target=serve)
    clients = [comms.LocalClient(address), comms.LocalClient(address)]
    thread.start()
    try:
        assert "operation_ownership" in clients[0].capabilities()["features"]
        # Another tool's comms check leaves a plain reply in every client's socket buffer.
        assert clients[1].comms_check()
        with clients[0].operation(123) as owner:
            assert owner
    finally:
        for client in clients:
            client.close()
        stop.set()
        thread.join(timeout=2)
        server.close()
    assert not thread.is_alive()
