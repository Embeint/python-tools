#!/usr/bin/env python3

"""Infuse-IoT cloud interaction."""

from infuse_iot.commands import InfuseCommand
from infuse_iot.tools.cloud_commands.applications import Applications as Applications
from infuse_iot.tools.cloud_commands.base import CloudSubCommand as CloudSubCommand
from infuse_iot.tools.cloud_commands.boards import Boards as Boards
from infuse_iot.tools.cloud_commands.coap import Coap as Coap
from infuse_iot.tools.cloud_commands.device import Device as Device
from infuse_iot.tools.cloud_commands.organisations import Organisations as Organisations
from infuse_iot.util.argparse import add_subparsers_with_list, print_subcommands_if_missing


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--api-key", type=str, help="Cloud API key to use instead of stored credentials")
        subparser = add_subparsers_with_list(parser, dest="_cloud_command")

        Organisations.add_parser(subparser)
        Boards.add_parser(subparser)
        Device.add_parser(subparser)
        Coap.add_parser(subparser)
        Applications.add_parser(subparser)

    def __init__(self, args):
        self.args = args
        self.tool = args.command_class(args) if hasattr(args, "command_class") else None

    def run(self):
        if print_subcommands_if_missing(self.args):
            return
        assert self.tool is not None
        self.tool.run()
