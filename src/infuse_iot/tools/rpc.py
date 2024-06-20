#!/usr/bin/env python3

"""Run remote procedure calls on devices"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import argparse
import random
import ctypes
import importlib
import pkgutil

from infuse_iot.epacket import ePacket, ePacketOut, ePacketHopOut
from infuse_iot.commands import InfuseCommand, InfuseRpcCommand
from infuse_iot.socket_comms import LocalClient, default_multicast_address

import infuse_iot.rpc_wrappers as wrappers


class SubCommand(InfuseCommand):
    NAME = "rpc"
    HELP = "Run remote procedure calls on devices"
    DESCRIPTION = "Run remote procedure calls on devices"

    class rpc_request_header(ctypes.LittleEndianStructure):
        """Serial packet header"""

        _fields_ = [
            ("request_id", ctypes.c_uint32),
            ("command_id", ctypes.c_uint16),
        ]
        _pack_ = 1

    class rpc_response_header(ctypes.LittleEndianStructure):
        """Serial packet header"""

        _fields_ = [
            ("request_id", ctypes.c_uint32),
            ("command_id", ctypes.c_uint16),
            ("return_code", ctypes.c_int16),
        ]
        _pack_ = 1

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

    def run(self):
        header = self.rpc_request_header(self._request_id, self._command.COMMAND_ID)
        params = self._command.request_struct()

        request_packet = bytes(header) + bytes(params)
        pkt = ePacketOut(
            [ePacketHopOut.serial(self._command.auth_level())],
            ePacket.types.RPC_CMD,
            request_packet,
        )
        self._client.send(pkt)
        # Wait for responses
        while rsp := self._client.receive():
            # RPC response packet
            if rsp.ptype != ePacket.types.RPC_RSP:
                continue
            rsp_header = self.rpc_response_header.from_buffer_copy(rsp.payload)
            # Response to the request we sent
            if rsp_header.request_id != self._request_id:
                continue
            # Convert response bytes back to struct form
            rsp_data = self._command.response.from_buffer_copy(
                rsp.payload[ctypes.sizeof(self.rpc_response_header) :]
            )
            # Handle the response
            print(f"ADDR: {rsp.route[0].address}")
            self._command.handle_response(rsp_header.return_code, rsp_data)
            break
