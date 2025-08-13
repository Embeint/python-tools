# Copyright (c) 2020 Teslabs Engineering S.L.
# Copyright (c) 2025 Embeint Holdings Pty Ltd
#
# SPDX-License-Identifier: Apache-2.0

import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from infuse_iot.util.soc.soc import ProvisioningInterface


class STM32Family:
    UID_ADDRESS: int
    OTP_ADDRESS: int
    SOC: str


class STM32L4X(STM32Family):
    UID_ADDRESS = 0x1FFF7590
    OTP_ADDRESS = 0x1FFF7000
    SOC = "stm32l4x"


DEVICE_ID_MAPPING = {
    0x435: STM32L4X,
    0x462: STM32L4X,
    0x464: STM32L4X,
}


class Interface(ProvisioningInterface):
    @staticmethod
    def programmer_path() -> Path:
        """
        Obtain path of the STM32CubeProgrammer CLI tool.
        From Zephyr runner file: stm32cubeprogrammer.py
        """

        if platform.system() == "Linux":
            cmd = shutil.which("STM32_Programmer_CLI")
            if cmd is not None:
                return Path(cmd)

            return (
                Path.home()
                / "STMicroelectronics"
                / "STM32Cube"
                / "STM32CubeProgrammer"
                / "bin"
                / "STM32_Programmer_CLI"
            )

        if platform.system() == "Windows":
            cli = Path("STMicroelectronics") / "STM32Cube" / "STM32CubeProgrammer" / "bin" / "STM32_Programmer_CLI.exe"
            x86_path = Path(os.environ["PROGRAMFILES(X86)"]) / cli
            if x86_path.exists():
                return x86_path

            return Path(os.environ["PROGRAMW6432"]) / cli

        if platform.system() == "Darwin":
            return (
                Path("/Applications")
                / "STMicroelectronics"
                / "STM32Cube"
                / "STM32CubeProgrammer"
                / "STM32CubeProgrammer.app"
                / "Contents"
                / "MacOs"
                / "bin"
                / "STM32_Programmer_CLI"
            )

        raise NotImplementedError("Could not determine STM32_Programmer_CLI path")

    @staticmethod
    def _get_device_id() -> int:
        """Retrieve STM32 device ID (SoC series identifier)"""
        stm_path = Interface.programmer_path()

        cmd_base = [str(stm_path), "--connect", "port=SWD"]

        # Get the device identifier (SoC Series)
        res = subprocess.run(cmd_base, capture_output=True, check=True)
        output = res.stdout.decode("utf-8")

        match = re.search(r"Device ID *: (0x[0-9a-fA-F]*)", output, re.MULTILINE)
        if match is None:
            raise RuntimeError("No match for 'Device ID' found in output")
        return int(match.group(1), 16)

    def __init__(self):
        # Get the device identifier (SoC Series)
        self._device_id = self._get_device_id()
        self._family = DEVICE_ID_MAPPING[self._device_id]
        self._cli = Interface.programmer_path()

    @property
    def soc_name(self) -> str:
        return self._family.SOC

    @property
    def unique_device_id_len(self) -> int:
        return 12

    def unique_device_id(self) -> int:
        """Retrieve 96 bit STM32 unique device ID"""
        cmd_base = [str(self._cli), "--connect", "port=SWD"]

        # Read the 96 bit (12 byte) UID
        cmd_read = cmd_base + ["-r32", hex(self._family.UID_ADDRESS), "12"]
        res = subprocess.run(cmd_read, capture_output=True, check=True)
        output = res.stdout.decode("utf-8")

        match = re.search(r"([0-9a-fA-F]{8}) ([0-9a-fA-F]{8}) ([0-9a-fA-F]{8})", output, re.MULTILINE)
        if match is None:
            raise RuntimeError("Unique device ID not found in output")

        word0 = int(match.group(1), 16)
        word1 = int(match.group(2), 16)
        word2 = int(match.group(3), 16)

        # Byte order matches that returned by `hwinfo_stm32`
        id_bytes = word2.to_bytes(4, "big") + word1.to_bytes(4, "big") + word0.to_bytes(4, "big")
        return int.from_bytes(id_bytes, "big")

    @staticmethod
    def unique_device_id_fields(uid: int) -> dict:
        uid_bytes = uid.to_bytes(12, "big")
        fields = {
            "wafer_x": int.from_bytes(uid_bytes[10:12], "big"),
            "wafer_y": int.from_bytes(uid_bytes[8:10], "big"),
            "wafer_number": uid_bytes[7],
            "lot_number": uid_bytes[0:7].decode("utf-8"),
        }
        return fields

    def read_provisioned_data(self, num: int) -> bytes:
        cmd_base = [str(self._cli), "--connect", "port=SWD"]

        cmd_read = cmd_base + ["-r32", hex(self._family.OTP_ADDRESS), str(num)]
        res = subprocess.run(cmd_read, capture_output=True, check=True)
        output = res.stdout.decode("utf-8")

        # Searching for patterns like the following:
        #
        # 0x1FFF7000 : FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF
        # 0x1FFF7010 : FFFFFFFF FFFFFFFF FFFFFFFF FFFFFFFF
        # 0x1FFF7020 : FFFFFFFF FFFFFFFF
        byte_re = re.compile(
            r"0x[0-9a-fA-F]{8} : ([0-9a-fA-F]{8}) ?([0-9a-fA-F]{8})? ?([0-9a-fA-F]{8})? ?([0-9a-fA-F]{8})?",
            re.MULTILINE,
        )
        byte_string_lines = byte_re.findall(output)

        # Parse into a byte string
        byte_output = b""
        for line in byte_string_lines:
            for chunk in line:
                if chunk == "":
                    continue
                # Byte order needs to be reversed
                big_endian = bytes.fromhex(chunk)
                byte_output += bytes(reversed(big_endian))

        # Return the requested number of bytes
        return byte_output[:num]

    def write_provisioning_data(self, data: bytes):
        cmd_base = [str(self._cli), "--connect", "port=SWD"]

        # Pad to 32bit alignment
        if mod := len(data) % 4:
            data += b"\xff" * (4 - mod)

        # Convert bytes to 4 byte words
        words = [int.from_bytes(data[i : i + 4], "little") for i in range(0, len(data), 4)]

        cmd_write = cmd_base + ["-w32", hex(self._family.OTP_ADDRESS)] + [f"0x{w:08x}" for w in words]
        subprocess.run(cmd_write, capture_output=True, check=True)

    def close(self):
        cmd_reset = [str(self._cli), "--connect", "port=SWD", "-rst"]
        subprocess.run(cmd_reset, capture_output=True, check=True)
