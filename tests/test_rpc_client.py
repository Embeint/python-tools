#!/usr/bin/env python3

from unittest.mock import Mock

import pytest

import infuse_iot.socket_comms as comms
from infuse_iot.epacket.packet import Auth
from infuse_iot.rpc_client import RpcClient

DEVICE = 123
OTHER = 456


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
