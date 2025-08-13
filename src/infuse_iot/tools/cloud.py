#!/usr/bin/env python3

"""Infuse-IoT cloud interaction"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import sys
from http import HTTPStatus
from json import loads
from typing import Any

from tabulate import tabulate

from infuse_iot.api_client import Client
from infuse_iot.api_client.api.board import (
    create_board,
    get_board_by_id,
    get_boards,
)
from infuse_iot.api_client.api.device import (
    get_device_by_device_id,
    get_device_last_route_by_device_id,
    get_device_state_by_id,
)
from infuse_iot.api_client.api.organisation import (
    create_organisation,
    get_all_organisations,
    get_organisation_by_id,
)
from infuse_iot.api_client.models import Error, NewBoard, NewOrganisation
from infuse_iot.commands import InfuseCommand
from infuse_iot.credentials import get_api_key


class CloudSubCommand:
    def __init__(self, args):
        self.args = args

    def run(self):
        """Run cloud sub-command"""

    def client(self):
        """Get API client object ready to use"""
        return Client(base_url="https://api.infuse-iot.com").with_headers({"x-api-key": f"Bearer {get_api_key()}"})


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
        if isinstance(orgs, Error) or orgs is None:
            sys.exit(f"Organisation query failed {orgs}")
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
            assert rsp.parsed is not None
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
        if isinstance(orgs, Error) or orgs is None:
            sys.exit(f"Organisation query failed {orgs}")
        for org in orgs:
            boards = get_boards.sync(client=client, organisation_id=org.id)
            if isinstance(boards, Error) or boards is None:
                sys.exit(f"Boards query failed {boards}")

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
            assert rsp.parsed is not None
            print(f"Created board {rsp.parsed.name} with ID {rsp.parsed.id}")
        else:
            c = loads(rsp.content.decode("utf-8"))
            print(f"<{rsp.status_code}>: {c['message']}")


class Device(CloudSubCommand):
    @classmethod
    def add_parser(cls, parser):
        parser_boards = parser.add_parser("device", help="Infuse-IoT devices")
        parser_boards.set_defaults(command_class=cls)

        tool_parser = parser_boards.add_subparsers(title="commands", metavar="<command>", required=True)

        info_parser = tool_parser.add_parser("info")
        info_parser.set_defaults(command_fn=cls.info)
        info_parser.add_argument("--id", type=str, help="Infuse-IoT device ID")

    def run(self):
        with self.client() as client:
            self.args.command_fn(self, client)

    def info(self, client):
        id_int = int(self.args.id, 0)
        id_str = f"{id_int:016x}"
        info = get_device_by_device_id.sync(client=client, device_id=id_str)
        if info is None:
            sys.exit(f"No device with Infuse-IoT ID {id_str} found")
        metadata: list[tuple[str, Any]] = []
        if info.metadata:
            metadata = [(f"Metadata.{k}", v) for k, v in info.metadata.additional_properties.items()]

        org = get_organisation_by_id.sync(client=client, id=info.organisation_id)
        board = get_board_by_id.sync(client=client, id=info.board_id)
        state = get_device_state_by_id.sync(client=client, id=info.id)
        route = get_device_last_route_by_device_id.sync(client=client, device_id=id_str)

        table: list[tuple[str, Any]] = [
            ("UUID", info.id),
            ("MCU ID", info.mcu_id),
            ("Organisation", f"{info.organisation_id} ({org.name if org else 'Unknown'})"),
            ("Board", f"{info.board_id} ({board.name if board else 'Unknown'})"),
            ("Created", info.created_at),
            ("Updated", info.updated_at),
            *metadata,
        ]
        if state is not None:
            v = state.application_version

            table += [
                ("~~~State~~~", ""),
                ("Updated", state.updated_at),
            ]
            if state.application_id:
                table += [("Application ID", f"0x{state.application_id:08x}")]
            if v:
                table += [("Version", f"{v.major}.{v.minor}.{v.revision}+{v.build_num:08x}")]
        if route is not None:
            table += [
                ("~~~Latest Route~~~", ""),
                ("Interface", route.interface.upper()),
            ]
            if route.bt_adv:
                table += [("BT Address", f"{route.bt_adv.address} ({route.bt_adv.type_})")]

        print(tabulate(table))


class SubCommand(InfuseCommand):
    NAME = "cloud"
    HELP = "Infuse-IoT cloud interaction"
    DESCRIPTION = "Infuse-IoT cloud interaction"

    @classmethod
    def add_parser(cls, parser):
        subparser = parser.add_subparsers(title="commands", metavar="<command>", required=True)

        Organisations.add_parser(subparser)
        Boards.add_parser(subparser)
        Device.add_parser(subparser)

    def __init__(self, args):
        self.tool = args.command_class(args)

    def run(self):
        self.tool.run()
