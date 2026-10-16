#!/usr/bin/env python3

"""Provision device on Infuse Cloud"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import ctypes
import sys
from http import HTTPStatus
from uuid import UUID

from infuse_iot.api_client import Client
from infuse_iot.api_client.api.board import get_board_by_id, get_boards
from infuse_iot.api_client.api.device import (
    create_device,
    get_device_by_soc_and_mcu_id,
)
from infuse_iot.api_client.api.organisation import get_all_organisations
from infuse_iot.api_client.models import Board, Device, DeviceMetadata, Error, NewDevice
from infuse_iot.commands import InfuseCommand
from infuse_iot.credentials import get_api_auth_header
from infuse_iot.util.api import fetch_all
from infuse_iot.util.argparse import InfuseDeviceId
from infuse_iot.util.console import choose_one
from infuse_iot.util.soc import nrf, rpi, soc, stm


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser):
        vendor_group = parser.add_mutually_exclusive_group(required=True)
        vendor_group.add_argument(
            "--nrf", dest="vendor", action="store_const", const="nrf", help="Nordic Semiconductor SoC"
        )
        vendor_group.add_argument(
            "--stm", dest="vendor", action="store_const", const="stm", help="ST Microelectronics SoC"
        )
        vendor_group.add_argument(
            "--rpi", dest="vendor", action="store_const", const="rpi", help="Raspberry Pi Pico over USB BOOTSEL"
        )
        parser.add_argument("--usb-serial", help="Select one Pico by its BOOTSEL USB serial number")
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
            type=InfuseDeviceId,
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
        parser.add_argument(
            "--dry-run", action="store_true", help="Generate the request that would be sent, but do not send it"
        )

    def __init__(self, args):
        self._vendor: str = args.vendor
        self._snr: int | None = args.snr
        self._usb_serial: str | None = args.usb_serial
        if self._usb_serial and self._vendor != "rpi":
            sys.exit("--usb-serial is only supported with --rpi")
        if self._snr is not None and self._vendor == "rpi":
            sys.exit("Use --usb-serial, not --snr, to select a Pico")
        try:
            self._board = UUID(args.board) if args.board else None
        except ValueError:
            sys.exit(f"Board ID: '{args.board}' is not a valid UUID")
        try:
            self._org = UUID(args.organisation) if args.organisation else None
        except ValueError:
            sys.exit(f"Organisation ID: '{args.organisation}' is not a valid UUID")
        self._id: int | None = args.id
        if self._vendor == "rpi" and self._id is not None:
            if not 0 <= self._id <= rpi.UINT64_MAX:
                sys.exit("Infuse ID must fit in an unsigned 64-bit integer")
            try:
                rpi.encode_record(self._id.to_bytes(8, "little"))
            except ValueError as exc:
                sys.exit(str(exc))
        self._dry_run: bool | None = args.dry_run
        self._metadata = {}
        if args.metadata:
            for meta in args.metadata:
                key, val = meta.strip().split("=", 1)
                self._metadata[key.strip()] = val

    def create_device(self, client: Client, soc_name: str, hardware_id_str: str):
        if self._org is None:
            orgs = fetch_all(get_all_organisations, client=client)
            if isinstance(orgs, Error) or orgs is None:
                sys.exit(f"Organisation query failed {orgs}")
            options = [f"{o.name:20s} ({o.id})" for o in orgs]

            idx, _val = choose_one("Organisation", options)
            self._org = orgs[idx].id

        if self._board is None:
            boards = fetch_all(get_boards, client=client, organisation_id=self._org, include_public=True)
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

        if self._dry_run:
            print(new_board)
            return

        response = create_device.sync_detailed(client=client, body=new_board)
        if response.status_code != HTTPStatus.CREATED:
            sys.exit(f"Failed to create device:\n\t<{response.status_code}> {response.content.decode('utf-8')}")

    def run(self):
        interface: soc.ProvisioningInterface
        if self._vendor == "nrf":
            interface = nrf.Interface(self._snr)
        elif self._vendor == "stm":
            interface = stm.Interface()
        elif self._vendor == "rpi":
            interface = rpi.Interface(self._usb_serial)
        else:
            raise NotImplementedError(f"Unhandled vendor '{self._vendor}'")

        try:
            self._run(interface)
        except ValueError as exc:
            sys.exit(f"Provisioning failed: {exc}")
        finally:
            interface.close(reset=not self._dry_run)

    def _run(self, interface: soc.ProvisioningInterface):
        hardware_id = interface.unique_device_id()
        hardware_id_str = f"{hardware_id:0{2 * interface.unique_device_id_len}x}"
        # Validate local storage before creating a cloud device. In particular,
        # Pico must not provision over an occupied or damaged flash sector.
        current_bytes = interface.read_provisioned_data(ctypes.sizeof(interface.DefaultProvisioningStruct))
        stored_id = None if current_bytes == b"\xff" * len(current_bytes) else int.from_bytes(current_bytes, "little")
        if stored_id is not None and self._id is not None and stored_id != self._id:
            sys.exit(f"Hardware already stores Infuse ID 0x{stored_id:016x}; refusing to replace it")

        client = Client(base_url="https://api.infuse-iot.com").with_headers(get_api_auth_header())

        # Get existing device or create new device
        with client as client:
            response = get_device_by_soc_and_mcu_id.sync_detailed(
                client=client, soc=interface.soc_name, mcu_id=hardware_id_str
            )
            if isinstance(response.parsed, Device):
                # Device found, fall through
                assert isinstance(response.parsed.device_id, str)
                self._org = response.parsed.organisation_id
                self._board = response.parsed.board_id
                cloud_id = int(response.parsed.device_id, 16)
                if self._id and (self._id != cloud_id):
                    # ID provided on the command line but device already provisioned as another ID
                    err = f"HW ID 0x{hardware_id:016x} provisioned as 0x{cloud_id:016x} on the cloud"
                    err += f" but CLI requested 0x{self._id:016x}"
                    sys.exit(err)
                pass
            elif response.status_code == HTTPStatus.NOT_FOUND:
                # Create new device here
                if self._id is None and stored_id is not None:
                    self._id = stored_id
                self.create_device(client, interface.soc_name, hardware_id_str)
                # Exit if dry run only
                if self._dry_run:
                    return
                # Query information back out
                response = get_device_by_soc_and_mcu_id.sync_detailed(
                    client=client, soc=interface.soc_name, mcu_id=hardware_id_str
                )
                if isinstance(response.parsed, Error):
                    err = "Failed to query device after creation:\n"
                    err += f"\t<{response.status_code}> {response.parsed.message}"
                    sys.exit(err)
                elif response.parsed is None:
                    err = "Failed to query device after creation:\n"
                    err += f"\t<{response.status_code}> {response.content.decode('utf-8')}"
                    sys.exit(err)
            else:
                err = "Failed to query device information:\n"
                err += f"\t<{response.status_code}> {response.content.decode('utf-8')}"
                sys.exit(err)

        assert isinstance(response.parsed.device_id, str)
        # Compare current flash contents to desired flash contents
        cloud_id = int(response.parsed.device_id, 16)
        desired = interface.DefaultProvisioningStruct(cloud_id)
        desired_bytes = bytes(desired)

        if current_bytes == desired_bytes:
            print(f"HW ID 0x{hardware_id:016x} already provisioned as 0x{desired.device_id:016x}")
        else:
            if current_bytes != len(current_bytes) * b"\xff":
                sys.exit(
                    f"HW ID 0x{hardware_id:016x} already has different provisioning info; refusing to overwrite it"
                )

            if self._dry_run:
                print(f"Would provision HW ID 0x{hardware_id:016x} as 0x{desired.device_id:016x}; no data written")
                return
            interface.write_provisioning_data(desired_bytes)
            print(f"HW ID 0x{hardware_id:016x} now provisioned as 0x{desired.device_id:016x}")

        example_cmd = f"infuse provision --organisation {self._org} --board {self._board} --{self._vendor}"
        print("To provision more devices like this:")
        print(f"\t {example_cmd}")
