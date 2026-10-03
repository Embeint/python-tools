#!/usr/bin/env python3

"""Infuse-IoT cloud interaction"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

from uuid import UUID

from tabulate import tabulate

import infuse_iot.api_client.models as models
from infuse_iot.api_client import Client
from infuse_iot.api_client.api.board import (
    create_board,
    get_boards,
)
from infuse_iot.api_client.api.organisation import (
    get_all_organisations,
)
from infuse_iot.util.api import fetch_all
from infuse_iot.util.argparse import (
    add_subparsers_with_list,
)

from .base import CloudSubCommand, require_response


class Boards(CloudSubCommand):
    @classmethod
    def add_parser(cls, parser):
        parser_boards = parser.add_parser("boards", help="Infuse-IoT hardware platforms")
        parser_boards.set_defaults(command_class=cls)

        tool_parser = add_subparsers_with_list(parser_boards, dest="_cloud_boards_command")

        list_parser = tool_parser.add_parser("list", help="List all hardware platforms")
        list_parser.add_argument(
            "--no-public",
            action="store_true",
            help="Only list boards owned by your organisations, omitting public reference boards",
        )
        list_parser.set_defaults(command_fn=cls.list)

        create_parser = tool_parser.add_parser("create", help="Create new hardware platform")
        create_parser.add_argument("--name", "-n", type=str, required=True, help="New board name")
        create_parser.add_argument("--org", "-o", type=str, required=True, help="Organisation ID")
        create_parser.add_argument("--soc", "-s", type=str, required=True, help="Board system on chip")
        create_parser.add_argument("--desc", "-d", type=str, required=True, help="Board description")
        create_parser.add_argument("--public", action="store_true", help="Public board (globally visible)")
        create_parser.set_defaults(command_fn=cls.create)

    def list(self, client: Client):
        orgs = fetch_all(get_all_organisations, client=client)
        orgs = require_response(orgs, "Organisation query")
        org_names = {o.id: o.name for o in orgs}

        boards: dict[UUID, models.Board] = {}
        for org in orgs:
            found = fetch_all(
                get_boards,
                client=client,
                organisation_id=org.id,
                include_public=not self.args.no_public,
            )
            found = require_response(found, "Boards query")
            # `include_public` also returns other organisations' public boards,
            # so the same board comes back once per organisation queried
            boards.update({b.id: b for b in found})

        board_list = [
            [
                b.name,
                b.id,
                b.soc,
                # Only organisations we are a member of can be resolved to a name
                org_names.get(b.organisation_id, b.organisation_id),
                "yes" if b.public else "no",
                b.description,
            ]
            for b in boards.values()
        ]

        print(
            tabulate(
                board_list,
                headers=["Name", "ID", "SoC", "Organisation", "Public", "Description"],
            )
        )

    def create(self, client: Client):
        rsp = create_board.sync_detailed(
            client=client,
            body=models.NewBoard(
                name=self.args.name,
                description=self.args.desc,
                soc=self.args.soc,
                organisation_id=self.args.org,
                public=self.args.public,
            ),
        )

        board = require_response(rsp, "Create board")
        print(f"Created board {board.name} with ID {board.id}")
