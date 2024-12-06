#!/usr/bin/env python3

"""Manage RPCs through Infuse-IoT cloud"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import argparse
import importlib
import json
import pkgutil
import sys
from uuid import UUID

import infuse_iot.rpc_wrappers as wrappers
from infuse_iot.api_client import Client
from infuse_iot.api_client.api.rpc import get_rpc_by_id, send_rpc
from infuse_iot.api_client.models import Error, NewRPCMessage, NewRPCReq, RPCParams, RpcRsp
from infuse_iot.api_client.models.downlink_message_status import DownlinkMessageStatus
from infuse_iot.commands import InfuseCommand, InfuseRpcCommand
from infuse_iot.credentials import get_api_key


class SubCommand(InfuseCommand):
    NAME = "rpc_cloud"
    HELP = "Manage remote procedure calls through Infuse-IoT cloud"
    DESCRIPTION = "Manage remote procedure calls through Infuse-IoT cloud"

    @classmethod
    def add_parser(cls, parser):
        subparser = parser.add_subparsers(title="commands", metavar="<command>", required=True)

        parser_queue = subparser.add_parser("queue", help="Queue a RPC to be sent")
        parser_queue.set_defaults(action="queue")
        parser_queue.add_argument("--id", required=True, type=lambda x: int(x, 0), help="Infuse ID to run command on")
        parser_queue.add_argument("--timeout", type=int, default=600, help="Timeout to send command in seconds")
        command_list_parser = parser_queue.add_subparsers(title="commands", metavar="<command>", required=True)

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

        parser_query = subparser.add_parser("query", help="Query the state of a previously queued RPC")
        parser_query.set_defaults(action="query")
        parser_query.add_argument("--id", required=True, type=str, help="RPC ID from `infuse rpc_cloud queue`")

    def __init__(self, args: argparse.Namespace):
        self._args = args

    def queue(self, client: Client):
        infuse_id = f"{self._args.id:016x}"
        command: InfuseRpcCommand = self._args.rpc_class(self._args)
        timeout_ms = 1000 * self._args.timeout

        assert hasattr(command, "COMMAND_ID")

        try:
            params = RPCParams.from_dict(command.request_json())
        except NotImplementedError:
            sys.exit(f"Command '{command.__class__.__name__}' has not implemented cloud support")
        req = NewRPCMessage(infuse_id, NewRPCReq(command.COMMAND_ID, params=params), timeout_ms)
        rsp = send_rpc.sync(client=client, body=req)
        if isinstance(rsp, Error) or rsp is None:
            sys.exit(f"Failed to queue RPC ({rsp})")
        print(f"Queued RPC ID: {rsp.id}")

    def query(self, client: Client):
        rsp = get_rpc_by_id.sync(client=client, id=UUID(self._args.id))
        if isinstance(rsp, Error) or rsp is None:
            sys.exit(f"Failed to query RPC state ({rsp})")
        print(f"RPC State: {rsp.downlink_message.status}")
        if rsp.downlink_message.status == DownlinkMessageStatus.COMPLETED:
            rpc_rsp = rsp.downlink_message.rpc_rsp
            assert isinstance(rpc_rsp, RpcRsp)
            assert isinstance(rpc_rsp.params, RPCParams)

            print(f"   Result: {rpc_rsp.return_code}")
            print(json.dumps(rpc_rsp.params.additional_properties, indent=4))

    def run(self):
        with Client(base_url="https://api.infuse-iot.com").with_headers(
            {"x-api-key": f"Bearer {get_api_key()}"}
        ) as client:
            if self._args.action == "queue":
                self.queue(client)
            elif self._args.action == "query":
                self.query(client)
