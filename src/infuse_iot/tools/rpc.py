#!/usr/bin/env python3

"""Run remote procedure calls on devices"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import argparse
import importlib
import pkgutil
import random

import infuse_iot.rpc_wrappers as wrappers
from infuse_iot.commands import InfuseCommand, InfuseRpcCommand
from infuse_iot.common import InfuseID, InfuseType
from infuse_iot.rpc_client import RpcClient
from infuse_iot.socket_comms import (
    ClientNotification,
    ClientNotificationEpacketReceived,
    GatewayRequestConnectionRequest,
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
        parser.add_argument("--conn-log", action="store_true", help="Request logs from remote device")
        parser.add_argument(
            "--conn-timeout", type=int, default=10000, help="Timeout to wait for a connection to the device (ms)"
        )
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
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._command: InfuseRpcCommand = args.rpc_class(args)
        self._request_id = random.randint(0, 2**32 - 1)
        self._max_payload = 0
        if args.gateway:
            self._id = InfuseID.GATEWAY
        else:
            self._id = args.id

    def rx_handler(self, pkt: ClientNotification):
        if (
            self._args.conn_log
            and isinstance(pkt, ClientNotificationEpacketReceived)
            and pkt.epacket.ptype == InfuseType.SERIAL_LOG
        ):
            print(pkt.epacket.payload.decode("utf-8"), end="")

    def run(self):
        try:
            types = GatewayRequestConnectionRequest.DataType.COMMAND
            if self._args.conn_log:
                types |= GatewayRequestConnectionRequest.DataType.LOGGING
            with self._client.connection(self._id, types, self._args.conn_timeout) as mtu:
                self._max_payload = mtu
                rpc_client = RpcClient(self._client, mtu, self._id, self.rx_handler)
                params = bytes(self._command.request_struct())

                if hasattr(self._command.response, "vla_from_buffer_copy"):  # type: ignore
                    decode_fn = self._command.response.vla_from_buffer_copy  # type: ignore
                else:
                    decode_fn = self._command.response.from_buffer_copy  # type: ignore

                if self._command.RPC_DATA_SEND:
                    hdr, rsp = rpc_client.run_data_send_cmd(
                        self._command.COMMAND_ID,  # type: ignore
                        self._command.auth_level(),
                        params,
                        self._command.data_payload(),
                        self._command.data_progress_cb,
                        decode_fn,
                    )
                elif self._command.RPC_DATA_RECEIVE:
                    hdr, rsp = rpc_client.run_data_recv_cmd(
                        self._command.COMMAND_ID,  # type: ignore
                        self._command.auth_level(),
                        params,
                        self._command.data_payload_recv_len(),
                        self._command.data_recv_cb,
                        decode_fn,
                    )
                else:
                    hdr, rsp = rpc_client.run_standard_cmd(
                        self._command.COMMAND_ID,  # type: ignore
                        self._command.auth_level(),
                        params,
                        decode_fn,
                    )
                # Handle response
                self._command.handle_response(hdr.return_code, rsp)

                if self._args.conn_log:
                    while True:
                        if notification := self._client.receive():
                            self.rx_handler(notification)
        except ConnectionRefusedError:
            print(f"Unable to connect to {self._id:016x}")
