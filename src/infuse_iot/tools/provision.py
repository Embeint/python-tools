#!/usr/bin/env python3

"""Provision device on Infuse Cloud"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import ctypes

from pynrfjprog import LowLevel, Parameters

from infuse_iot.commands import InfuseCommand


class ProvisioningStruct(ctypes.LittleEndianStructure):
    _fields_ = [
        ("device_id", ctypes.c_uint64),
        ("device_secret", 16 * ctypes.c_char),
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
        parser.add_argument(
            "--id", type=int, required=True, help="Infuse device ID to provision as"
        )

    def __init__(self, args):
        self._snr = args.snr
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

        for desc in api.read_memory_descriptors():
            if desc.type == Parameters.MemoryType.UICR:
                uicr_addr = desc.start + customer_offsets[family]
            if desc.type == Parameters.MemoryType.FICR:
                dev_id_addr = desc.start + device_id_offsets[family]
                dev_id_bytes = bytes(api.read(dev_id_addr, 8))
                dev_id = int.from_bytes(dev_id_bytes, "big")

        return dev_id, uicr_addr

    def run(self):
        with LowLevel.API() as api:
            if self._snr is None:
                api.connect_to_emu_without_snr()
            else:
                api.connect_to_emu_with_snr(self._snr)

            hardware_id, uicr_addr = self.nrf_device_info(api)
            # Query Infuse cloud for device here
            device_secret = 16 * b"\x01"

            current_bytes = bytes(
                api.read(uicr_addr, ctypes.sizeof(ProvisioningStruct))
            )
            desired = ProvisioningStruct(self._id, device_secret)
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
