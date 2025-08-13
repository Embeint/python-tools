#!/usr/bin/env python3

"""Provision device on Infuse Cloud"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import ctypes
import sys
from http import HTTPStatus

from infuse_iot.api_client import Client
from infuse_iot.api_client.api.board import get_board_by_id, get_boards
from infuse_iot.api_client.api.device import (
    create_device,
    get_device_by_soc_and_mcu_id,
)
from infuse_iot.api_client.api.organisation import get_all_organisations
from infuse_iot.api_client.models import Board, DeviceMetadata, Error, NewDevice
from infuse_iot.commands import InfuseCommand
from infuse_iot.credentials import get_api_key
from infuse_iot.util.console import choose_one
from infuse_iot.util.soc import nrf, soc, stm


class ProvisioningStruct(ctypes.LittleEndianStructure):
    _fields_ = [
        ("device_id", ctypes.c_uint64),
    ]
    _pack_ = 1


class SubCommand(InfuseCommand):
    NAME = "provision"
    HELP = "Provision device on Infuse Cloud"
    DESCRIPTION = "Provision device on Infuse Cloud"

    @classmethod
    def add_parser(cls, parser):
        vendor_group = parser.add_mutually_exclusive_group(required=True)
        vendor_group.add_argument(
            "--nrf", dest="vendor", action="store_const", const="nrf", help="Nordic Semiconductor SoC"
        )
        vendor_group.add_argument(
            "--stm", dest="vendor", action="store_const", const="stm", help="ST Microelectronics SoC"
        )
        parser.add_argument(
            "--snr",
            type=int,
            default=None,
            help="JTAG serial number",
        )
        parser.add_argument("--board", "-b", type=str, help="Board ID")
        parser.add_argument("--organisation", "-o", type=str, help="Organisation ID")
        parser.add_argument(
            "--id",
            "-i",
            type=lambda x: int(x, 0),
            help="Infuse device ID to provision as",
        )
        parser.add_argument(
            "--metadata",
            "-m",
            metavar="KEY=VALUE",
            nargs="+",
            type=str,
            help="Define a number of key-value pairs for metadata",
        )

    def __init__(self, args):
        self._vendor = args.vendor
        self._snr = args.snr
        self._board = args.board
        self._org = args.organisation
        self._id = args.id
        self._metadata = {}
        if args.metadata:
            for meta in args.metadata:
                key, val = meta.strip().split("=", 1)
                self._metadata[key.strip()] = val

    def create_device(self, client: Client, soc_name: str, hardware_id_str: str):
        if self._org is None:
            orgs = get_all_organisations.sync(client=client)
            if isinstance(orgs, Error) or orgs is None:
                sys.exit(f"Organisation query failed {orgs}")
            options = [f"{o.name:20s} ({o.id})" for o in orgs]

            idx, _val = choose_one("Organisation", options)
            self._org = orgs[idx].id

        if self._board is None:
            boards = get_boards.sync(client=client, organisation_id=self._org)
            if isinstance(boards, Error) or boards is None:
                sys.exit(f"Board query failed {boards}")
            options = [f"{b.name:20s} ({b.id})" for b in boards]

            idx, _val = choose_one("Board", options)
            self._board = boards[idx].id
        board = get_board_by_id.sync(client=client, id=self._board)
        if not isinstance(board, Board):
            sys.exit(f"Board query failed {board}")
        if board.soc != soc_name:
            sys.exit(f"Found SoC '{soc_name}' but board '{board.name}' has SoC '{board.soc}'")

        new_board = NewDevice(
            mcu_id=hardware_id_str,
            organisation_id=self._org,
            board_id=self._board,
            metadata=DeviceMetadata.from_dict(self._metadata),
        )
        if self._id:
            new_board.device_id = f"{self._id:016x}"

        response = create_device.sync_detailed(client=client, body=new_board)
        if response.status_code != HTTPStatus.CREATED:
            sys.exit(f"Failed to create device:\n\t<{response.status_code}> {response.content.decode('utf-8')}")

    def run(self):
        interface: soc.ProvisioningInterface
        if self._vendor == "nrf":
            interface = nrf.Interface(self._snr)
        elif self._vendor == "stm":
            interface = stm.Interface()
        else:
            raise NotImplementedError(f"Unhandled vendor '{self._vendor}'")

        hardware_id = interface.unique_device_id()
        hardware_id_str = f"{hardware_id:0{2 * interface.unique_device_id_len}x}"

        client = Client(base_url="https://api.infuse-iot.com").with_headers({"x-api-key": f"Bearer {get_api_key()}"})

        # Get existing device or create new device
        with client as client:
            response = get_device_by_soc_and_mcu_id.sync_detailed(
                client=client, soc=interface.soc_name, mcu_id=hardware_id_str
            )
            if response.status_code == HTTPStatus.OK:
                # Device found, fall through
                pass
            elif response.status_code == HTTPStatus.NOT_FOUND:
                # Create new device here
                self.create_device(client, interface.soc_name, hardware_id_str)
                # Query information back out
                response = get_device_by_soc_and_mcu_id.sync_detailed(
                    client=client, soc=interface.soc_name, mcu_id=hardware_id_str
                )
                if response.status_code != HTTPStatus.OK:
                    err = "Failed to query device after creation:\n"
                    err += f"\t<{response.status_code}> {response.content.decode('utf-8')}"
                    sys.exit(err)
                print("To provision more devices like this:")
                print(f"\t infuse provision --organisation {self._org} --board {self._board}")
            else:
                err = "Failed to query device information:\n"
                err += f"\t<{response.status_code}> {response.content.decode('utf-8')}"
                sys.exit(err)

        assert response.parsed is not None
        assert isinstance(response.parsed.device_id, str)
        # Compare current flash contents to desired flash contents
        cloud_id = int(response.parsed.device_id, 16)
        current_bytes = interface.read_provisioned_data(ctypes.sizeof(ProvisioningStruct))
        desired = ProvisioningStruct(cloud_id)
        desired_bytes = bytes(desired)

        if current_bytes == desired_bytes:
            print(f"HW ID 0x{hardware_id:016x} already provisioned as 0x{desired.device_id:016x}")
        else:
            if current_bytes != len(current_bytes) * b"\xff":
                print(f"HW ID 0x{hardware_id:016x} already has incorrect provisioning info, recover device")
                return

            interface.write_provisioning_data(bytes(desired))
            print(f"HW ID 0x{hardware_id:016x} now provisioned as 0x{desired.device_id:016x}")

        interface.close()
