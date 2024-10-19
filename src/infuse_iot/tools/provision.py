#!/usr/bin/env python3

"""Provision device on Infuse Cloud"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import ctypes
from http import HTTPStatus
import sys

try:
    from simple_term_menu import TerminalMenu
except NotImplementedError:
    TerminalMenu = None

from pynrfjprog import LowLevel, Parameters

from infuse_iot.api_client import Client
from infuse_iot.api_client.api.default import (
    get_device_by_soc_and_mcu_id,
    create_device,
    get_all_organisations,
    get_boards,
    get_board_by_id,
)
from infuse_iot.api_client.models import NewDevice
from infuse_iot.credentials import get_api_key
from infuse_iot.commands import InfuseCommand


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
        parser.add_argument(
            "--snr",
            type=int,
            default=None,
            help="JTAG serial number",
        )
        parser.add_argument("--board", "-b", type=str, help="Board ID")
        parser.add_argument("--organisation", "-o", type=str, help="Organisation ID")
        parser.add_argument(
            "--id", "-i", type=int, help="Infuse device ID to provision as"
        )

    def __init__(self, args):
        self._snr = args.snr
        self._board = args.board
        self._org = args.organisation
        self._id = args.id

    def nrf_device_info(self, api: LowLevel.API) -> tuple[int, int]:
        """Retrive device ID and customer UICR address"""
        device_id_offsets = {
            # nRF52840 only
            "NRF52": 0x60,
            "NRF53": 0x204,
            "NRF91": 0x204,
        }
        customer_offsets = {
            # nRF52840 only
            "NRF52": 0x80,
            "NRF53": 0x100,
            "NRF91": 0x108,
        }
        family = api.read_device_family()
        device_info = api.read_device_info()

        if device_info[1] == Parameters.DeviceName.NRF9120:
            # Use version to determine nRF9151 vs nRF9161
            if device_info[0] == Parameters.DeviceVersion.NRF9120_xxAA_REV3:
                soc = "nRF9151"
            else:
                sys.exit(f"Unknown device: {device_info[0]}")
        else:
            socs = {
                Parameters.DeviceName.NRF52840: "nRF52840",
                Parameters.DeviceName.NRF5340: "nRF5340",
                Parameters.DeviceName.NRF9160: "nRF9160",
            }
            if device_info[1] not in socs:
                sys.exit(f"Unknown device: {device_info[1]}")
            soc = socs[device_info[1]]

        uicr_addr = None
        dev_id = None
        for desc in api.read_memory_descriptors():
            if desc.type == Parameters.MemoryType.UICR:
                uicr_addr = desc.start + customer_offsets[family]
            if desc.type == Parameters.MemoryType.FICR:
                dev_id_addr = desc.start + device_id_offsets[family]
                dev_id_bytes = bytes(api.read(dev_id_addr, 8))
                dev_id = int.from_bytes(dev_id_bytes, "big")

        return soc, uicr_addr, dev_id

    def create_device(self, client, soc, hardware_id_str):
        if self._org is None:
            orgs = get_all_organisations.sync(client=client)
            options = [f"{o.name:20s} ({o.id})" for o in orgs]

            if TerminalMenu is None:
                sys.exit(
                    "Specify organisation with --organisation:\n" + "\n".join(options)
                )

            terminal_menu = TerminalMenu(options)
            idx = terminal_menu.show()
            self._org = orgs[idx].id

        if self._board is None:
            boards = get_boards.sync(client=client, organisation_id=self._org)
            options = [f"{b.name:20s} ({b.id})" for b in boards]

            if TerminalMenu is None:
                sys.exit("Specify board with --board:\n" + "\n".join(options))

            terminal_menu = TerminalMenu(options)
            idx = terminal_menu.show()
            self._board = boards[idx].id
        board = get_board_by_id.sync(client=client, id=self._board)

        if board.soc != soc:
            sys.exit(
                f"Found SoC '{soc}' but board '{board.name}' has SoC '{board.soc}'"
            )

        new_board = NewDevice(
            mcu_id=hardware_id_str, organisation_id=self._org, board_id=self._board
        )
        if self._id:
            new_board.device_id = f"{self._id:016x}"

        response = create_device.sync_detailed(client=client, body=new_board)
        if response.status_code != HTTPStatus.CREATED:
            sys.exit(
                f"Failed to create device:\n\t<{response.status_code}> {response.content.decode('utf-8')}"
            )

    def run(self):
        with LowLevel.API() as api:
            if self._snr is None:
                api.connect_to_emu_without_snr()
            else:
                api.connect_to_emu_with_snr(self._snr)

            soc, uicr_addr, hardware_id = self.nrf_device_info(api)
            hardware_id_str = f"{hardware_id:016x}"

            client = Client(base_url="https://api.dev.infuse-iot.com").with_headers(
                {"x-api-key": f"Bearer {get_api_key()}"}
            )

            # Get existing device or create new device
            with client as client:
                response = get_device_by_soc_and_mcu_id.sync_detailed(
                    client=client, soc=soc, mcu_id=hardware_id_str
                )
                if response.status_code == HTTPStatus.OK:
                    # Device found, fall through
                    pass
                elif response.status_code == HTTPStatus.NOT_FOUND:
                    # Create new device here
                    self.create_device(client, soc, hardware_id_str)
                    # Query information back out
                    response = get_device_by_soc_and_mcu_id.sync_detailed(
                        client=client, soc=soc, mcu_id=hardware_id_str
                    )
                    if response.status_code != HTTPStatus.OK:
                        sys.exit(
                            f"Failed to query device after creation:\n\t<{response.status_code}> {response.content.decode('utf-8')}"
                        )
                    print("To provision more devices like this:")
                    print(
                        f"\t infuse provision --organisation {self._org} --board {self._board}"
                    )
                else:
                    sys.exit(
                        f"Failed to query device information:\n\t<{response.status_code}> {response.content.decode('utf-8')}"
                    )

            # Compare current flash contents to desired flash contents
            cloud_id = int(response.parsed.device_id, 16)
            current_bytes = bytes(
                api.read(uicr_addr, ctypes.sizeof(ProvisioningStruct))
            )
            desired = ProvisioningStruct(cloud_id)
            desired_bytes = bytes(desired)

            if current_bytes == desired_bytes:
                print(
                    f"HW ID 0x{hardware_id:016x} already provisioned as 0x{desired.device_id:016x}"
                )
            else:
                if current_bytes != len(current_bytes) * b"\xFF":
                    print(
                        f"HW ID 0x{hardware_id:016x} already has incorrect provisioning info, recover device"
                    )
                    return

                api.write(uicr_addr, bytes(desired), True)
                print(
                    f"HW ID 0x{hardware_id:016x} now provisioned as 0x{desired.device_id:016x}"
                )

            # Reset the MCU
            api.pin_reset()
