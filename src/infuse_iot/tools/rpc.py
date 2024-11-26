#!/usr/bin/env python3

"""Run remote procedure calls on devices"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import argparse
import random
import ctypes
import importlib
import pkgutil

from infuse_iot.common import InfuseType, InfuseID
from infuse_iot.epacket.packet import PacketOutput
from infuse_iot.commands import InfuseCommand, InfuseRpcCommand
from infuse_iot.socket_comms import (
    LocalClient,
    ClientNotification,
    GatewayRequest,
    default_multicast_address,
)
from infuse_iot import rpc

import infuse_iot.rpc_wrappers as wrappers


class SubCommand(InfuseCommand):
    NAME = "rpc"
    HELP = "Run remote procedure calls on devices"
    DESCRIPTION = "Run remote procedure calls on devices"

    @classmethod
    def add_parser(cls, parser):
        command_list_parser = parser.add_subparsers(
            title="commands", metavar="<command>", required=True
        )

        for _, name, _ in pkgutil.walk_packages(wrappers.__path__):
            full_name = f"{wrappers.__name__}.{name}"
            module = importlib.import_module(full_name)

            # Add RPC wrapper to parser
            cmd_cls = getattr(module, name)
            cmd_parser = command_list_parser.add_parser(
                name,
                help=cmd_cls.HELP,
                description=cmd_cls.DESCRIPTION,
                formatter_class=argparse.RawDescriptionHelpFormatter,
            )
            cmd_parser.set_defaults(rpc_class=cmd_cls)
            cmd_cls.add_parser(cmd_parser)

    def __init__(self, args):
        self._args = args
        self._client = LocalClient(default_multicast_address(), 10.0)
        self._command: InfuseRpcCommand = args.rpc_class(args)
        self._request_id = random.randint(0, 2**32 - 1)

    def _wait_data_ack(self):
        while rsp := self._client.receive():
            if rsp.type != ClientNotification.Type.EPACKET_RECV:
                continue
            if rsp.epacket.ptype != InfuseType.RPC_DATA_ACK:
                continue
            data_ack = rpc.DataAck.from_buffer_copy(rsp.epacket.payload)
            # Response to the request we sent
            if data_ack.request_id != self._request_id:
                continue
            break

    def _wait_rpc_rsp(self):
        # Wait for responses
        while rsp := self._client.receive():
            if rsp.type != ClientNotification.Type.EPACKET_RECV:
                continue
            # RPC response packet
            if rsp.epacket.ptype != InfuseType.RPC_RSP:
                continue
            rsp_header = rpc.ResponseHeader.from_buffer_copy(rsp.epacket.payload)
            # Response to the request we sent
            if rsp_header.request_id != self._request_id:
                continue
            # Convert response bytes back to struct form
            rsp_data = self._command.response.from_buffer_copy(
                rsp.epacket.payload[ctypes.sizeof(rpc.ResponseHeader) :]
            )
            # Handle the response
            print(f"INFUSE ID: {rsp.epacket.route[0].infuse_id:016x}")
            self._command.handle_response(rsp_header.return_code, rsp_data)
            break

    def _run_data_cmd(self):
        ack_period = 1
        header = rpc.RequestHeader(self._request_id, self._command.COMMAND_ID)
        params = self._command.request_struct()
        data = self._command.data_payload()
        data_hdr = rpc.RequestDataHeader(len(data), ack_period)

        request_packet = bytes(header) + bytes(data_hdr) + bytes(params)
        pkt = PacketOutput(
            InfuseID.GATEWAY,
            self._command.auth_level(),
            InfuseType.RPC_CMD,
            request_packet,
        )
        req = GatewayRequest(GatewayRequest.Type.EPACKET_SEND, epacket=pkt)
        self._client.send(req)

        # Wait for initial ACK
        self._wait_data_ack()

        # Send data payloads (384 byte chunks for now)
        ack_cnt = -ack_period
        offset = 0
        size = 384
        while len(data) > 0:
            size = min(size, len(data))
            payload = data[:size]

            hdr = rpc.DataHeader(self._request_id, offset)
            pkt_bytes = bytes(hdr) + payload
            pkt = PacketOutput(
                InfuseID.GATEWAY,
                self._command.auth_level(),
                InfuseType.RPC_DATA,
                pkt_bytes,
            )
            self._client.send(pkt)
            ack_cnt += 1

            # Wait for ACKs at the period
            if ack_cnt == ack_period:
                self._wait_data_ack()
                ack_cnt = 0

            offset += size
            data = data[size:]
            self._command.data_progress_cb(offset)

        self._wait_rpc_rsp()

    def _run_standard_cmd(self):
        header = rpc.RequestHeader(self._request_id, self._command.COMMAND_ID)
        params = self._command.request_struct()

        request_packet = bytes(header) + bytes(params)
        pkt = PacketOutput(
            InfuseID.GATEWAY,
            self._command.auth_level(),
            InfuseType.RPC_CMD,
            request_packet,
        )
        req = GatewayRequest(GatewayRequest.Type.EPACKET_SEND, epacket=pkt)
        self._client.send(req)
        self._wait_rpc_rsp()

    def run(self):
        if self._command.RPC_DATA:
            self._run_data_cmd()
        else:
            self._run_standard_cmd()
