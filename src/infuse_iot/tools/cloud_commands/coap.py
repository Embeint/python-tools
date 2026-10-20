#!/usr/bin/env python3

"""Infuse-IoT cloud interaction"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"


from infuse_iot.api_client import Client
from infuse_iot.api_client.api.coap import get_coap_files
from infuse_iot.util.argparse import (
    add_subparsers_with_list,
)

from .base import CloudSubCommand, require_response


class Coap(CloudSubCommand):
    @classmethod
    def add_parser(cls, parser):
        parser_coap = parser.add_parser("coap", help="CoAP file server")
        parser_coap.set_defaults(command_class=cls)

        tool_parser = add_subparsers_with_list(parser_coap, dest="_cloud_coap_command")

        list_parser = tool_parser.add_parser("list", help="List all CoAP files")
        list_parser.set_defaults(command_fn=cls.list)

    def list(self, client: Client):
        files = get_coap_files.sync(client=client)

        files = require_response(files, "CoAP file query")
        sorted_list: list[str] = sorted(files.filenames)
        print("CoAP Files:")
        print("\t" + "\n\t".join(sorted_list))
