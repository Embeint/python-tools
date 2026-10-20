import ctypes
from unittest.mock import Mock

import pytest

from infuse_iot.epacket.packet import Auth
from infuse_iot.rpc_client import RpcClient
from infuse_iot.socket_comms import LocalClient


class Response(ctypes.LittleEndianStructure):
    _fields_ = [("value", ctypes.c_uint32)]


@pytest.fixture
def rpc_client():
    client = RpcClient(Mock(spec=LocalClient), 128, 123)
    client._request_id = 10
    client.set_timeout(1.0)
    return client


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
