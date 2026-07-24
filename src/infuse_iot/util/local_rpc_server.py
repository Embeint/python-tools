#!/usr/bin/env python3

"""Simple local RPC server implementation"""

import ctypes
import random
import typing
from collections.abc import Callable

import infuse_iot.definitions.rpc as defs
import infuse_iot.epacket.interface as interface
from infuse_iot import rpc
from infuse_iot.common import InfuseType
from infuse_iot.database import DeviceDatabase
from infuse_iot.epacket.packet import (
    Auth,
    HopOutput,
    PacketOutputRouted,
    PacketReceived,
)
from infuse_iot.util.console import Console

RpcCallback = Callable[[PacketReceived, int, bytes, typing.Any], None]


class LocalRpcServer:
    """Basic class supporting locally generated commands"""

    def __init__(self, database: DeviceDatabase):
        self._cnt = random.randint(0, 2**31)
        self._ddb = database
        self._queued: dict[int, tuple[RpcCallback | None, typing.Any]] = {}

    def generate(
        self, command: int, args: bytes, auth: Auth, cb: RpcCallback | None, cb_ctx: typing.Any
    ) -> PacketOutputRouted:
        """Generate RPC packet from arguments"""
        cmd_bytes = bytes(rpc.RequestHeader(self._cnt, command)) + args
        cmd_pkt = PacketOutputRouted(
            [HopOutput.serial(auth)],
            InfuseType.RPC_CMD,
            cmd_bytes,
        )
        assert self._ddb.gateway is not None
        cmd_pkt.route[0].infuse_id = self._ddb.gateway
        self._queued[self._cnt] = (cb, cb_ctx)
        self._cnt += 1
        return cmd_pkt

    def generate_remote_bt(
        self, remote: int, command: int, args: bytes, auth: Auth, cb: RpcCallback | None, cb_ctx: typing.Any
    ) -> PacketOutputRouted:
        """Generate RPC packet for Bluetooth remote from arguments"""
        cmd_bytes = bytes(rpc.RequestHeader(self._cnt, command)) + args

        assert self._ddb.gateway is not None
        serial = HopOutput(self._ddb.gateway, interface.ID.SERIAL, Auth.DEVICE)
        bt = HopOutput(remote, interface.ID.BT_CENTRAL, auth)
        self._queued[self._cnt] = (cb, cb_ctx)
        self._cnt += 1
        return PacketOutputRouted(
            [serial, bt],
            InfuseType.RPC_CMD,
            cmd_bytes,
        )

    def handle(self, pkt: PacketReceived):
        """Handle received packets"""
        # Only care about RPC responses
        if pkt.ptype != InfuseType.RPC_RSP:
            return

        # Inspect the response header
        header = rpc.ResponseHeader.from_buffer_copy(pkt.payload)

        # Was this a BT connect response with key information?
        if header.command_id == defs.bt_connect_infuse.COMMAND_ID:
            resp = defs.bt_connect_infuse.response.from_buffer_copy(pkt.payload[ctypes.sizeof(header) :])
            if_addr = interface.Address.BluetoothLeAddr.from_rpc_struct(resp.peer)
            infuse_id = self._ddb.infuse_id_from_bluetooth(if_addr)
            if infuse_id is None:
                Console.log_error(f"Infuse ID of {if_addr} not known")

        # Determine if the response is to a command we initiated
        if header.request_id not in self._queued:
            return

        # Run the callback
        (cb, cb_ctx) = self._queued.pop(header.request_id)
        if cb is not None:
            cb(pkt, header.return_code, pkt.payload[ctypes.sizeof(header) :], cb_ctx)
