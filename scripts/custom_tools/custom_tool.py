#!/usr/bin/env python3

"""Example out-of-tree tool"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2025, Embeint Inc"

from infuse_iot.commands import InfuseCommand


class SubCommand(InfuseCommand):
    NAME = "custom_tool"
    HELP = "Test out-of-tree tool"
    DESCRIPTION = "Test out-of-tree tool"

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--echo", "-e", required=True, type=str)

    def __init__(self, args):
        self.echo_string = args.echo

    def run(self):
        print("Echoing provided string:")
        print(self.echo_string)
