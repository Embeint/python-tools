#!/usr/bin/env python3

"""Run remote procedure calls on devices"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import argparse
import ctypes
import importlib
import pkgutil
import random

import infuse_iot.rpc_wrappers as wrappers
from infuse_iot import rpc
from infuse_iot.commands import InfuseCommand, InfuseRpcCommand
from infuse_iot.common import InfuseID, InfuseType
from infuse_iot.epacket.packet import PacketOutput
from infuse_iot.socket_comms import (
    ClientNotificationConnectionDropped,
    ClientNotificationEpacketReceived,
    GatewayRequestEpacketSend,
    LocalClient,
    default_multicast_address,
)


class SubCommand(InfuseCommand):
    NAME = "rpc"
    HELP = "Run remote procedure calls on devices"
    DESCRIPTION = "Run remote procedure calls on devices"

    @classmethod
    def add_parser(cls, parser):
        addr_group = parser.add_mutually_exclusive_group(required=True)
        addr_group.add_argument("--gateway", action="store_true", help="Run command on local gateway")
        addr_group.add_argument("--id", type=lambda x: int(x, 0), help="Infuse ID to run command on")
        command_list_parser = parser.add_subparsers(title="commands", metavar="<command>", required=True)

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

    def __init__(self, args: argparse.Namespace):
        self._args = args
        self._client = LocalClient(default_multicast_address(), 10.0)
        self._command: InfuseRpcCommand = args.rpc_class(args)
        self._request_id = random.randint(0, 2**32 - 1)
        if args.gateway:
            self._id = InfuseID.GATEWAY
        else:
            self._id = args.id

    def _wait_data_ack(self):
        while rsp := self._client.receive():
            if not isinstance(rsp, ClientNotificationEpacketReceived):
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
            if not isinstance(rsp, ClientNotificationEpacketReceived):
                continue
            # RPC response packet
            if rsp.epacket.ptype != InfuseType.RPC_RSP:
                continue
            rsp_header = rpc.ResponseHeader.from_buffer_copy(rsp.epacket.payload)
            # Response to the request we sent
            if rsp_header.request_id != self._request_id:
                continue
            # Convert response bytes back to struct form
            rsp_payload = rsp.epacket.payload[ctypes.sizeof(rpc.ResponseHeader) :]
            rsp_data = self._command.response.from_buffer_copy(rsp_payload)  # type: ignore
            # Handle the response
            print(f"INFUSE ID: {rsp.epacket.route[0].infuse_id:016x}")
            self._command.handle_response(rsp_header.return_code, rsp_data)
            break

    def _run_data_send_cmd(self):
        ack_period = 1
        header = rpc.RequestHeader(self._request_id, self._command.COMMAND_ID)  # type: ignore
        params = self._command.request_struct()
        data = self._command.data_payload()
        data_hdr = rpc.RequestDataHeader(len(data), ack_period)

        request_packet = bytes(header) + bytes(data_hdr) + bytes(params)
        pkt = PacketOutput(
            self._id,
            self._command.auth_level(),
            InfuseType.RPC_CMD,
            request_packet,
        )
        req = GatewayRequestEpacketSend(pkt)
        self._client.send(req)

        # Wait for initial ACK
        self._wait_data_ack()

        # Send data payloads (384 byte chunks for now)
        ack_cnt = -ack_period
        offset = 0
        size = 192
        while len(data) > 0:
            size = min(size, len(data))
            payload = data[:size]

            hdr = rpc.DataHeader(self._request_id, offset)
            pkt_bytes = bytes(hdr) + payload
            pkt = PacketOutput(
                self._id,
                self._command.auth_level(),
                InfuseType.RPC_DATA,
                pkt_bytes,
            )
            self._client.send(GatewayRequestEpacketSend(pkt))
            ack_cnt += 1

            # Wait for ACKs at the period
            if ack_cnt == ack_period:
                self._wait_data_ack()
                ack_cnt = 0

            offset += size
            data = data[size:]
            self._command.data_progress_cb(offset)

        self._wait_rpc_rsp()

    def _run_data_recv_cmd(self):
        header = rpc.RequestHeader(self._request_id, self._command.COMMAND_ID)  # type: ignore
        params = self._command.request_struct()
        data_hdr = rpc.RequestDataHeader(0xFFFFFFFF, 0)

        request_packet = bytes(header) + bytes(data_hdr) + bytes(params)
        pkt = PacketOutput(
            self._id,
            self._command.auth_level(),
            InfuseType.RPC_CMD,
            request_packet,
        )
        req = GatewayRequestEpacketSend(pkt)
        self._client.send(req)

        while rsp := self._client.receive():
            if isinstance(rsp, ClientNotificationConnectionDropped):
                break
            if not isinstance(rsp, ClientNotificationEpacketReceived):
                continue
            if rsp.epacket.ptype == InfuseType.RPC_RSP:
                rsp_header = rpc.ResponseHeader.from_buffer_copy(rsp.epacket.payload)
                # Response to the request we sent
                if rsp_header.request_id != self._request_id:
                    continue
                # Convert response bytes back to struct form
                rsp_payload = rsp.epacket.payload[ctypes.sizeof(rpc.ResponseHeader) :]
                rsp_data = self._command.response.from_buffer_copy(rsp_payload)  # type: ignore
                # Handle the response
                self._command.handle_response(rsp_header.return_code, rsp_data)
                break

            if rsp.epacket.ptype != InfuseType.RPC_DATA:
                continue
            data = rpc.DataHeader.from_buffer_copy(rsp.epacket.payload)
            # Response to the request we sent
            if data.request_id != self._request_id:
                continue

            self._command.data_recv_cb(data.offset, rsp.epacket.payload[ctypes.sizeof(rpc.DataHeader) :])

    def _run_standard_cmd(self):
        header = rpc.RequestHeader(self._request_id, self._command.COMMAND_ID)  # type: ignore
        params = self._command.request_struct()

        request_packet = bytes(header) + bytes(params)
        pkt = PacketOutput(
            self._id,
            self._command.auth_level(),
            InfuseType.RPC_CMD,
            request_packet,
        )
        req = GatewayRequestEpacketSend(pkt)
        self._client.send(req)
        self._wait_rpc_rsp()

    def run(self):
        try:
            self._client.connection_create(self._id)
            if self._command.RPC_DATA_SEND:
                self._run_data_send_cmd()
            elif self._command.RPC_DATA_RECEIVE:
                self._run_data_recv_cmd()
            else:
                self._run_standard_cmd()
        except ConnectionRefusedError:
            print(f"Unable to connect to {self._id:016x}")
        finally:
            self._client.connection_release()
