#!/usr/bin/env python3

import ctypes
from unittest.mock import Mock

import pytest

import infuse_iot.socket_comms as comms
from infuse_iot.epacket.packet import Auth
from infuse_iot.rpc_client import RpcClient

DEVICE = 123
OTHER = 456


class Response(ctypes.LittleEndianStructure):
    _fields_ = [("value", ctypes.c_uint32)]


@pytest.fixture
def rpc_client():
    client = RpcClient(Mock(spec=comms.LocalClient), 128, DEVICE)
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


@pytest.mark.parametrize("mode", ["standard", "send"])
def test_rpc_inactivity_timeout(rpc_client, monkeypatch, mode):
    clock = [0.0]
    monkeypatch.setattr("infuse_iot.rpc_client.time.monotonic", lambda: clock[0])

    def receive(timeout):
        clock[0] += timeout
        return None

    rpc_client._client.receive.side_effect = receive
    if mode == "standard":
        result = rpc_client.run_standard_cmd(1, Auth.DEVICE, b"", Response.from_buffer_copy)
    else:
        result = rpc_client.run_data_send_cmd(1, Auth.DEVICE, b"", b"data", None, Response.from_buffer_copy)
    assert result == (None, None)
    assert clock[0] == 1.0
