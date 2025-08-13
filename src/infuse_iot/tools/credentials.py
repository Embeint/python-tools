#!/usr/bin/env python3

"""Manage Infuse-IoT credentials"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import yaml

from infuse_iot import credentials
from infuse_iot.commands import InfuseCommand
from infuse_iot.util.argparse import ValidDir, ValidFile


class SubCommand(InfuseCommand):
    NAME = "credentials"
    HELP = "Manage Infuse-IoT credentials"
    DESCRIPTION = "Manage Infuse-IoT credentials"

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--api-key", type=str, help="Set Infuse-IoT API key")
        parser.add_argument("--api-key-print", action="store_true", help="Print Infuse-IoT API key")
        parser.add_argument("--network", type=ValidFile, help="Load network credentials from file")
        parser.add_argument("--custom-tools", type=ValidDir, help="Location of custom tools")
        parser.add_argument("--custom-definitions", type=ValidDir, help="Location of custom definitions")

    def __init__(self, args):
        self.args = args

    def run(self):
        if self.args.api_key is not None:
            credentials.set_api_key(self.args.api_key)
        if self.args.api_key_print:
            try:
                print(f"API Key: {credentials.get_api_key()}")
            except FileNotFoundError:
                print("API Key: N/A")
        if self.args.network is not None:
            # Read the file
            with self.args.network.open("r") as f:
                content = f.read()
            # Validate it is valid yaml
            network_info = yaml.safe_load(content)
            credentials.save_network(network_info["id"], content)
        if self.args.custom_tools:
            credentials.set_custom_tool_path(str(self.args.custom_tools.absolute()))
        if self.args.custom_definitions:
            credentials.set_custom_definitions_path(str(self.args.custom_definitions.absolute()))
