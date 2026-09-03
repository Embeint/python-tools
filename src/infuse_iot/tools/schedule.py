#!/usr/bin/env python3

"""Task schedule utilities."""

import argparse
import sys

from infuse_iot.task_runner import format_description, format_schedule_python, parse_schedule
from infuse_iot.util.argparse import add_subparsers_with_list, print_subcommands_if_missing


class SubCommand:
    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser):
        subcommands = add_subparsers_with_list(
            parser,
            dest="_schedule_command",
            title="schedule commands",
        )

        decode = subcommands.add_parser(
            "decode",
            help="Decode a task schedule",
            description="Decode a task schedule from hex or base64",
        )
        decode.add_argument("--python", action="store_true", help="output Python assignment lines")
        decode.add_argument("schedule", help="task schedule encoded as hex or base64")
        decode.set_defaults(schedule_command="decode")

    def __init__(self, args: argparse.Namespace):
        self._args = args

    def run(self) -> None:
        if print_subcommands_if_missing(self._args):
            return

        if self._args.schedule_command == "decode":
            self._run_decode()

    def _run_decode(self) -> None:
        try:
            schedule = parse_schedule(self._args.schedule)
        except ValueError as err:
            print(f"error: {err}", file=sys.stderr)
            raise SystemExit(2) from None

        if self._args.python:
            print(format_schedule_python(schedule))
        else:
            print(format_description(schedule))
