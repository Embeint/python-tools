#!/usr/bin/env python3

"""Infuse-IoT cloud interaction"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

from http import HTTPStatus
from json import loads

from tabulate import tabulate

from infuse_iot.api_client import Client
from infuse_iot.api_client.api.default import (
    create_board,
    create_organisation,
    get_all_organisations,
    get_boards,
)
from infuse_iot.api_client.models import NewBoard, NewOrganisation
from infuse_iot.commands import InfuseCommand
from infuse_iot.credentials import get_api_key


class CloudSubCommand:
    def __init__(self, args):
        self.args = args

    def run(self):
        """Run cloud sub-command"""

    def client(self):
        """Get API client object ready to use"""
        return Client(base_url="https://api.dev.infuse-iot.com").with_headers({"x-api-key": f"Bearer {get_api_key()}"})


class Organisations(CloudSubCommand):
    @classmethod
    def add_parser(cls, parser):
        parser_orgs = parser.add_parser("orgs", help="Infuse-IoT organisations")
        parser_orgs.set_defaults(command_class=cls)

        tool_parser = parser_orgs.add_subparsers(title="commands", metavar="<command>", required=True)

        list_parser = tool_parser.add_parser("list")
        list_parser.set_defaults(command_fn=cls.list)

        create_parser = tool_parser.add_parser("create")
        create_parser.add_argument("--name", "-n", type=str, required=True)
        create_parser.set_defaults(command_fn=cls.create)

    def run(self):
        with self.client() as client:
            self.args.command_fn(self, client)

    def list(self, client):
        org_list = []

        orgs = get_all_organisations.sync(client=client)
        for o in orgs:
            org_list.append([o.name, o.id])

        print(
            tabulate(
                org_list,
                headers=["Name", "ID"],
            )
        )

    def create(self, client):
        rsp = create_organisation.sync_detailed(
            client=client,
            body=NewOrganisation(self.args.name),
        )

        if rsp.status_code == HTTPStatus.CREATED:
            print(f"Created organisation {rsp.parsed.name} with ID {rsp.parsed.id}")
        else:
            c = loads(rsp.content.decode("utf-8"))
            print(f"<{rsp.status_code}>: {c['message']}")


class Boards(CloudSubCommand):
    @classmethod
    def add_parser(cls, parser):
        parser_boards = parser.add_parser("boards", help="Infuse-IoT hardware platforms")
        parser_boards.set_defaults(command_class=cls)

        tool_parser = parser_boards.add_subparsers(title="commands", metavar="<command>", required=True)

        list_parser = tool_parser.add_parser("list")
        list_parser.set_defaults(command_fn=cls.list)

        create_parser = tool_parser.add_parser("create")
        create_parser.add_argument("--name", "-n", type=str, required=True, help="New board name")
        create_parser.add_argument("--org", "-o", type=str, required=True, help="Organisation ID")
        create_parser.add_argument("--soc", "-s", type=str, required=True, help="Board system on chip")
        create_parser.add_argument("--desc", "-d", type=str, required=True, help="Board description")
        create_parser.set_defaults(command_fn=cls.create)

    def run(self):
        with self.client() as client:
            self.args.command_fn(self, client)

    def list(self, client):
        board_list = []

        orgs = get_all_organisations.sync(client=client)
        for org in orgs:
            boards = get_boards.sync(client=client, organisation_id=org.id)

            for b in boards:
                board_list.append([b.name, b.id, b.soc, org.name, b.description])

        print(
            tabulate(
                board_list,
                headers=["Name", "ID", "SoC", "Organisation", "Description"],
            )
        )

    def create(self, client):
        rsp = create_board.sync_detailed(
            client=client,
            body=NewBoard(
                name=self.args.name,
                description=self.args.desc,
                soc=self.args.soc,
                organisation_id=self.args.org,
            ),
        )
        if rsp.status_code == HTTPStatus.CREATED:
            print(f"Created board {rsp.parsed.name} with ID {rsp.parsed.id}")
        else:
            c = loads(rsp.content.decode("utf-8"))
            print(f"<{rsp.status_code}>: {c['message']}")


class SubCommand(InfuseCommand):
    NAME = "cloud"
    HELP = "Infuse-IoT cloud interaction"
    DESCRIPTION = "Infuse-IoT cloud interaction"

    @classmethod
    def add_parser(cls, parser):
        subparser = parser.add_subparsers(title="commands", metavar="<command>", required=True)

        Organisations.add_parser(subparser)
        Boards.add_parser(subparser)

    def __init__(self, args):
        self.tool = args.command_class(args)

    def run(self):
        self.tool.run()
