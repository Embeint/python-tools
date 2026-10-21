#!/usr/bin/env python3

import ctypes
from unittest.mock import Mock

import pytest

import infuse_iot.socket_comms as comms
from infuse_iot import rpc
from infuse_iot.common import InfuseType
from infuse_iot.epacket import interface
from infuse_iot.epacket.packet import Auth, HopReceived, PacketReceived
from infuse_iot.rpc_client import RpcClient

DEVICE = 123
OTHER = 456


class Response(ctypes.LittleEndianStructure):
    _fields_ = [("value", ctypes.c_uint32)]


def notification(ptype, payload):
    hop = HopReceived(
        DEVICE,
        interface.ID.BT_ADV,
        interface.Address(interface.Address.BluetoothLeAddr(0, 0)),
        Auth.NETWORK,
        0,
        0,
        0,
        -60,
    )
    return comms.ClientNotificationEpacketReceived(PacketReceived([hop], ptype, payload))


@pytest.fixture
def rpc_client():
    local = Mock(spec=comms.LocalClient)
    local.connection_dropped.return_value = False
    client = RpcClient(local, 128, DEVICE)
    client._request_id = 10
    client.set_timeout(1.0)
    return client


def test_data_recv_aborts_only_on_loss_of_own_connection(monkeypatch):
    client = comms.LocalClient.__new__(comms.LocalClient)
    client._connection_id = DEVICE
    receive = Mock(
        side_effect=[
            comms.ClientNotificationConnectionDropped(OTHER),
            comms.ClientNotificationConnectionDropped(DEVICE),
        ]
    )
    monkeypatch.setattr(client, "send", Mock())
    monkeypatch.setattr(client, "receive", receive)
    rpc_client = RpcClient(client, 128, DEVICE)
    with pytest.raises(ConnectionAbortedError):
        rpc_client.run_data_recv_cmd(1, Auth.DEVICE, b"", 0, Mock(), Mock())
    # The other device's connection loss was skipped
    assert receive.call_count == 2


@pytest.mark.parametrize("mode", ["standard", "send", "receive"])
def test_rpc_inactivity_timeout(rpc_client, monkeypatch, mode):
    clock = [0.0]
    monkeypatch.setattr("infuse_iot.rpc_client.time.monotonic", lambda: clock[0])

    def receive(timeout):
        clock[0] += timeout
        return None

    rpc_client._client.receive.side_effect = receive
    if mode == "standard":
        result = rpc_client.run_standard_cmd(1, Auth.DEVICE, b"", Response.from_buffer_copy)
    elif mode == "send":
        result = rpc_client.run_data_send_cmd(1, Auth.DEVICE, b"", b"data", None, Response.from_buffer_copy)
    else:
        result = rpc_client.run_data_recv_cmd(1, Auth.DEVICE, b"", 0, Mock(), Response.from_buffer_copy)
    assert result == (None, None)
    assert clock[0] == 1.0


def test_download_error_preserves_return_code(rpc_client):
    rpc_client._client.receive.return_value = notification(InfuseType.RPC_RSP, bytes(rpc.ResponseHeader(11, 1, -22)))
    header, response = rpc_client.run_data_recv_cmd(1, Auth.DEVICE, b"", 0, Mock(), Response.from_buffer_copy)
    assert header.return_code == -22
    assert response is None


def test_download_timeout_resets_on_matching_data(rpc_client, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("infuse_iot.rpc_client.time.monotonic", lambda: clock[0])
    messages = iter(
        [
            notification(InfuseType.RPC_DATA, bytes(rpc.DataHeader(11, 0)) + b"first"),
            notification(InfuseType.RPC_DATA, bytes(rpc.DataHeader(11, 5)) + b"last"),
            notification(InfuseType.RPC_RSP, bytes(rpc.ResponseHeader(11, 1, 0)) + bytes(Response(42))),
        ]
    )

    def receive(timeout):
        clock[0] += 0.6
        return next(messages)

    rpc_client._client.receive.side_effect = receive
    callback = Mock()
    header, response = rpc_client.run_data_recv_cmd(1, Auth.DEVICE, b"", 9, callback, Response.from_buffer_copy)
    assert header.return_code == 0
    assert response.value == 42
    assert clock[0] > 1.0
    assert [call.args for call in callback.call_args_list] == [(0, b"first"), (5, b"last")]


def test_unrelated_data_does_not_extend_timeout(rpc_client, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("infuse_iot.rpc_client.time.monotonic", lambda: clock[0])

    def receive(timeout):
        clock[0] += 0.6
        return notification(InfuseType.RPC_DATA, bytes(rpc.DataHeader(999, 0)) + b"other")

    rpc_client._client.receive.side_effect = receive
    callback = Mock()
    assert rpc_client.run_data_recv_cmd(1, Auth.DEVICE, b"", 0, callback, Response.from_buffer_copy) == (None, None)
    callback.assert_not_called()


def test_command_response_wait_aborts_on_loss_of_own_connection(monkeypatch):
    client = comms.LocalClient.__new__(comms.LocalClient)
    client._connection_id = DEVICE
    receive = Mock(
        side_effect=[
            comms.ClientNotificationConnectionDropped(OTHER),
            comms.ClientNotificationConnectionDropped(DEVICE),
        ]
    )
    monkeypatch.setattr(client, "send", Mock())
    monkeypatch.setattr(client, "receive", receive)
    rpc_client = RpcClient(client, 128, DEVICE)
    rpc_client.set_timeout(1.0)
    with pytest.raises(ConnectionAbortedError):
        rpc_client.run_standard_cmd(1, Auth.DEVICE, b"", Response.from_buffer_copy)
    assert receive.call_count == 2


def test_matching_request_id_from_another_device_is_ignored(rpc_client):
    wrong = notification(InfuseType.RPC_RSP, bytes(rpc.ResponseHeader(11, 1, 0)) + bytes(Response(99)))
    wrong.epacket.route[0].infuse_id = 999
    right = notification(InfuseType.RPC_RSP, bytes(rpc.ResponseHeader(11, 1, 0)) + bytes(Response(42)))
    rpc_client._client.receive.side_effect = [wrong, right]
    header, response = rpc_client.run_standard_cmd(1, Auth.DEVICE, b"", Response.from_buffer_copy)
    assert header.return_code == 0
    assert response.value == 42
