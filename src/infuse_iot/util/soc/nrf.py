# Copyright (c) 2025 Embeint Holdings Pty Ltd
#
# SPDX-License-Identifier: Apache-2.0

import json
import subprocess
import sys

from infuse_iot.util.soc.soc import ProvisioningInterface


class NRFFamily:
    FICR_ADDRESS: int
    DEVICE_ID_OFFSET: int
    CUSTOMER_OFFSET: int

    @staticmethod
    def soc(device_info):
        raise NotImplementedError


class nRF52(NRFFamily):
    FICR_ADDRESS = 0x10000000
    DEVICE_ID_OFFSET = 0x60
    CUSTOMER_OFFSET = 0x80

    @staticmethod
    def soc(device_info):
        version: str = device_info["jlink"]["deviceVersion"]
        if version.startswith("NRF52840"):
            return "nRF52840"
        elif version.startswith("NRF52833"):
            return "nRF52833"
        else:
            raise NotImplementedError(f"Unhandled device {version}")


class nRF53(NRFFamily):
    FICR_ADDRESS = 0x00FF0000
    DEVICE_ID_OFFSET = 0x204
    CUSTOMER_OFFSET = 0x100

    @staticmethod
    def soc(device_info):
        version: str = device_info["jlink"]["deviceVersion"]
        if version.startswith("NRF5340"):
            return "nRF5340"
        else:
            raise NotImplementedError(f"Unhandled device {version}")


class nRF54L(NRFFamily):
    FICR_ADDRESS = 0x00FFC000
    DEVICE_ID_OFFSET = 0x304
    CUSTOMER_OFFSET = 0x500

    @staticmethod
    def soc(device_info):
        version: str = device_info["jlink"]["deviceVersion"]
        if version.startswith("NRF54L15"):
            return "nRF54L15"
        elif version.startswith("NRF54L10"):
            return "nRF54L10"
        elif version.startswith("NRF54L05"):
            return "nRF54L05"
        else:
            raise NotImplementedError(f"Unhandled device {version}")


class nRF91(NRFFamily):
    FICR_ADDRESS = 0x00FF0000
    DEVICE_ID_OFFSET = 0x204
    CUSTOMER_OFFSET = 0x108

    @staticmethod
    def soc(device_info):
        version: str = device_info["jlink"]["deviceVersion"]
        if version.startswith("NRF9160"):
            return "nRF9160"
        elif version.startswith("NRF9161"):
            return "nRF9161"
        elif version.startswith("NRF9151"):
            return "nRF9151"
        else:
            raise NotImplementedError(f"Unhandled device {version}")


DEVICE_FAMILY_MAPPING: dict[str, type[NRFFamily]] = {
    "NRF52_FAMILY": nRF52,
    "NRF53_FAMILY": nRF53,
    "NRF54L_FAMILY": nRF54L,
    "NRF91_FAMILY": nRF91,
}


class Interface(ProvisioningInterface):
    def __init__(self, snr: int | None):
        self.snr = snr
        devices = self._exec(["device-info"])
        if len(devices) == 0:
            sys.exit()
        devices_info = devices[0]["devices"]

        if len(devices_info) > 1:
            serials = ",".join([d["serialNumber"] for d in devices_info])
            sys.exit(f"Multiple devices found without a SNR provided (Found: {serials})")
        self.snr = devices_info[0]["serialNumber"]
        self.device_info = devices_info[0]["deviceInfo"]
        self.core_info = self._exec(["core-info"])
        self.family = DEVICE_FAMILY_MAPPING[self.device_info["jlink"]["deviceFamily"]]
        self.uicr_base = self.core_info[0]["devices"][0]["uicrAddress"]
        self._soc_name = self.family.soc(self.device_info)

    def _exec(self, args: list[str]):
        jout_all = []
        cmd_base = ["nrfutil", "--json", "--skip-overhead", "device"]
        cmd = cmd_base + args
        if self.snr is not None:
            cmd += ["--serial-number", str(self.snr)]

        with subprocess.Popen(cmd, stdout=subprocess.PIPE) as p:
            assert p.stdout is not None
            for line in iter(p.stdout.readline, b""):
                # https://github.com/ndjson/ndjson-spec
                jout = json.loads(line.decode(sys.getdefaultencoding()))
                jout_all.append(jout)

        return jout_all

    def close(self):
        self._exec(["reset"])

    @property
    def soc_name(self) -> str:
        return self._soc_name

    @property
    def unique_device_id_len(self) -> int:
        return 8

    def unique_device_id(self) -> int:
        device_id_addr = self.family.FICR_ADDRESS + self.family.DEVICE_ID_OFFSET

        result = self._exec(["read", "--address", hex(device_id_addr), "--bytes", "8", "--direct"])
        data_bytes = result[0]["devices"][0]["memoryData"][0]["values"]
        dev_id_bytes = bytes(data_bytes)
        return int.from_bytes(dev_id_bytes, "big")

    def read_provisioned_data(self, num: int) -> bytes:
        customer_addr = self.uicr_base + self.family.CUSTOMER_OFFSET

        result = self._exec(["read", "--address", hex(customer_addr), "--bytes", str(num), "--direct"])
        data_bytes = result[0]["devices"][0]["memoryData"][0]["values"]

        return bytes(data_bytes)

    def write_provisioning_data(self, data: bytes):
        customer_addr = self.uicr_base + self.family.CUSTOMER_OFFSET

        # x-write only operates on single words
        for offset in range(0, len(data), 4):
            chunk_bytes = data[offset : offset + 4]
            if len(chunk_bytes) != 4:
                chunk_bytes += b"\xff" * (4 - len(chunk_bytes))
            data_word = int.from_bytes(chunk_bytes, byteorder="little")

            self._exec(["write", "--address", hex(customer_addr + offset), "--value", hex(data_word)])
