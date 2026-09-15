#!/usr/bin/env python3

"""Manage Infuse-IoT profiles."""

import argparse
import json
import sys

from tabulate import tabulate

from infuse_iot.commands import InfuseCommand
from infuse_iot.profile import (
    configure_profile,
    get_active_profile_name,
    load_profiles,
    load_raw_profile_config,
    set_active_profile,
)
from infuse_iot.tools.registry import load_extension_tools
from infuse_iot.util.argparse import ValidDir, add_subparsers_with_list, print_subcommands_if_missing


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser):
        subcommands = add_subparsers_with_list(
            parser,
            dest="_profile_command",
            title="profile commands",
        )

        list_parser = subcommands.add_parser("list", help="List profiles")
        list_parser.set_defaults(profile_command="list")

        configure_parser = subcommands.add_parser("configure", help="Create or update a profile")
        configure_parser.add_argument("--name", "-n", required=True, help="Profile name")
        configure_parser.add_argument("--custom-tools", type=ValidDir, help="Location of custom tools")
        configure_parser.add_argument("--custom-definitions", type=ValidDir, help="Location of custom definitions")
        configure_parser.set_defaults(profile_command="configure")

        set_parser = subcommands.add_parser("set", help="Set active profile")
        set_parser.add_argument("--name", "-n", required=True, help="Profile name")
        set_parser.set_defaults(profile_command="set")

        dump_parser = subcommands.add_parser("dump", help="Dump profile configuration")
        dump_parser.set_defaults(profile_command="dump")

    def __init__(self, args: argparse.Namespace):
        self._args = args

    def run(self) -> None:
        if print_subcommands_if_missing(self._args):
            return

        if self._args.profile_command == "list":
            self._run_list()
        elif self._args.profile_command == "configure":
            self._run_configure()
        elif self._args.profile_command == "set":
            self._run_set()
        elif self._args.profile_command == "dump":
            self._run_dump()

    def _run_list(self) -> None:
        active_profile = get_active_profile_name()
        rows = [
            [
                name,
                "yes" if name == active_profile else "no",
                profile.custom_tools if profile.custom_tools is not None else "",
                profile.custom_definitions if profile.custom_definitions is not None else "",
            ]
            for name, profile in sorted(load_profiles().items())
        ]
        print(tabulate(rows, headers=["Name", "Active", "Custom Tools", "Custom Definitions"]))

    def _run_configure(self) -> None:
        custom_tools, custom_definitions = self._profile_path_args()
        _, created = configure_profile(
            self._args.name,
            custom_tools=custom_tools,
            custom_definitions=custom_definitions,
        )
        action = "Created" if created else "Updated"
        print(f"{action} profile {self._args.name}")

    def _run_set(self) -> None:
        try:
            set_active_profile(self._args.name)
        except ValueError as err:
            print(f"error: {err}", file=sys.stderr)
            raise SystemExit(1) from None

        print(f"Active profile set to {self._args.name}")

    def _run_dump(self) -> None:
        raw_profile_config = load_raw_profile_config()
        if raw_profile_config is None:
            print("No profiles configured")
        else:
            print(json.dumps(raw_profile_config, indent=2, sort_keys=True))

    def _profile_path_args(self) -> tuple[str | None, str | None]:
        custom_tools = self._args.custom_tools
        if custom_tools:
            load_extension_tools(custom_tools)

        return (
            str(custom_tools.absolute()) if custom_tools else None,
            str(self._args.custom_definitions.absolute()) if self._args.custom_definitions else None,
        )
