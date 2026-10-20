#!/usr/bin/env python3

"""Infuse-IoT cloud interaction"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"


import sys

from tabulate import tabulate

import infuse_iot.api_client.models as models
from infuse_iot.api_client import Client
from infuse_iot.api_client.api.organisation import (
    create_organisation,
    get_all_organisations,
)
from infuse_iot.util.api import fetch_all
from infuse_iot.util.argparse import (
    add_subparsers_with_list,
)

from .base import CloudSubCommand


class Organisations(CloudSubCommand):
    @classmethod
    def add_parser(cls, parser):
        parser_orgs = parser.add_parser("orgs", help="Infuse-IoT organisations")
        parser_orgs.set_defaults(command_class=cls)

        tool_parser = add_subparsers_with_list(parser_orgs, dest="_cloud_orgs_command")

        list_parser = tool_parser.add_parser("list", help="List all organisations")
        list_parser.set_defaults(command_fn=cls.list)

        create_parser = tool_parser.add_parser("create", help="Create new organisation")
        create_parser.add_argument("--name", "-n", type=str, required=True)
        create_parser.set_defaults(command_fn=cls.create)

    def list(self, client: Client):
        org_list = []

        orgs = fetch_all(get_all_organisations, client=client)
        if isinstance(orgs, models.Error) or orgs is None:
            sys.exit(f"Organisation query failed {orgs}")
        for o in orgs:
            org_list.append([o.name, o.id])

        print(
            tabulate(
                org_list,
                headers=["Name", "ID"],
            )
        )

    def create(self, client: Client):
        rsp = create_organisation.sync_detailed(
            client=client,
            body=models.NewOrganisation(self.args.name),
        )

        if rsp.parsed is None:
            print(f"<{rsp.status_code}>: {rsp.content.decode('utf-8')}")
        elif isinstance(rsp.parsed, models.Error):
            print(f"<{rsp.status_code}>: {rsp.parsed.message}")
        else:
            print(f"Created organisation {rsp.parsed.name} with ID {rsp.parsed.id}")
