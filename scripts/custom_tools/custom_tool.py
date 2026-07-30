#!/usr/bin/env python3

"""Provide a minimal example of an out-of-tree Infuse command.

The command registers a custom subcommand that accepts an ``--echo`` argument
and prints it back, demonstrating the shape expected by ``InfuseCommand``
plugins without depending on project-specific behavior.
"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2025, Embeint Holdings Pty Ltd"

from infuse_iot.commands import InfuseCommand


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--echo", "-e", required=True, type=str)

    def __init__(self, args):
        self.echo_string = args.echo

    def run(self):
        print("Echoing provided string:")
        print(self.echo_string)
