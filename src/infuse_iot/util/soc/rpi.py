# Copyright (c) 2026 Embeint Holdings Pty Ltd
# SPDX-License-Identifier: FSL-1.1-ALv2

"""Pico provisioning through picotool's USB BOOTSEL transport."""

import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

from infuse_iot.util.soc.soc import ProvisioningInterface

FLASH_BASE = 0x10000000
SECTOR_SIZE = 4096
KV_SIZE = 32 * 1024
MAGIC = 0x49504649  # IFPI, shared with infuse/provisioning/rpi_pico.h
VERSION = 1
RECORD = struct.Struct("<IIQQ")
UINT64_MAX = (1 << 64) - 1


def encode_record(data: bytes) -> bytes:
    if len(data) != 8:
        raise ValueError("Pico provisioning requires an eight-byte Infuse ID")
    device_id = int.from_bytes(data, "little")
    if device_id == 0 or device_id >> 48 == 0xFFFF:
        raise ValueError("Infuse ID must be nonzero and outside the locally managed ffff namespace")
    return RECORD.pack(MAGIC, VERSION, device_id, device_id ^ UINT64_MAX)


def decode_record(sector: bytes) -> bytes:
    if len(sector) != SECTOR_SIZE:
        raise ValueError("Incomplete Pico provisioning sector read")
    if sector == b"\xff" * SECTOR_SIZE:
        return b"\xff" * 8
    magic, version, device_id, inverse = RECORD.unpack_from(sector)
    if (
        magic != MAGIC
        or version != VERSION
        or device_id == 0
        or device_id >> 48 == 0xFFFF
        or inverse != device_id ^ UINT64_MAX
        or sector[RECORD.size :] != b"\xff" * (SECTOR_SIZE - RECORD.size)
    ):
        raise ValueError("Invalid or occupied Pico provisioning sector; refusing to overwrite it")
    return device_id.to_bytes(8, "little")


class Interface(ProvisioningInterface):
    def __init__(self, serial: str | None = None):
        self._cli = shutil.which("picotool")
        if self._cli is None:
            raise RuntimeError("Install Raspberry Pi picotool 2.3.1 or later, then reconnect with BOOTSEL held")
        self._selection = ["--ser", serial] if serial else []
        output = self._exec(["info", "-d"])
        # info may list multiple devices successfully. Never choose one implicitly.
        types = re.findall(r"^\s*type:\s*(RP2040|RP2350)\s*$", output, re.MULTILINE)
        if len(types) != 1:
            raise RuntimeError("Connect exactly one Pico in BOOTSEL, or select it with --usb-serial")
        self._soc_name = types[0].lower()
        field = "flash id" if self._soc_name == "rp2040" else "chipid"
        match = re.search(rf"^\s*{field}:\s*(?:0x)?([0-9a-fA-F]{{16}})\s*$", output, re.MULTILINE)
        size = re.search(r"^\s*flash size:\s*(\d+)K\s*$", output, re.MULTILINE)
        if match is None or size is None:
            raise RuntimeError(
                "picotool did not report the hardware ID and flash size. "
                "Flash Infuse firmware for this board, re-enter BOOTSEL, and retry."
            )
        self._hardware_id = int(match.group(1), 16)
        self._flash_size = int(size.group(1)) * 1024
        expected_size = 2 * 1024 * 1024 if self._soc_name == "rp2040" else 4 * 1024 * 1024
        if self._flash_size != expected_size:
            raise RuntimeError("Only Pico/Pico W (2 MiB) and Pico 2/Pico 2 W (4 MiB) layouts are supported")
        if self._hardware_id in (0, UINT64_MAX):
            raise RuntimeError("picotool returned an invalid hardware ID")
        # Both BOOTSEL serial numbers match the ID printed above. Bind all later
        # commands so reconnecting a different board cannot redirect a write.
        self._selection = ["--ser", f"{self._hardware_id:016X}"]
        self._address = FLASH_BASE + self._flash_size - KV_SIZE - SECTOR_SIZE
        self._written = False

    def _exec(self, args: list[str]) -> str:
        try:
            result = subprocess.run(
                [str(self._cli), *args, *self._selection], capture_output=True, text=True, check=True, timeout=30
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"picotool failed: {exc.stderr.strip() or exc.stdout.strip()}") from exc
        return result.stdout

    @property
    def soc_name(self) -> str:
        return self._soc_name

    @property
    def unique_device_id_len(self) -> int:
        return 8

    def unique_device_id(self) -> int:
        # Same byte order as Zephyr HWINFO and the security-state challenge.
        return self._hardware_id

    def _read_sector(self) -> bytes:
        with tempfile.TemporaryDirectory(prefix="infuse-pico-") as directory:
            path = Path(directory) / "provisioning.bin"
            self._exec(["save", "-r", hex(self._address), hex(self._address + SECTOR_SIZE), str(path), "-t", "bin"])
            data = path.read_bytes()
        if len(data) != SECTOR_SIZE:
            raise RuntimeError("picotool returned an incomplete provisioning sector")
        return data

    def read_provisioned_data(self, num: int) -> bytes:
        if num != 8:
            raise ValueError("Pico provisioning contains exactly one eight-byte Infuse ID")
        return decode_record(self._read_sector())

    def write_provisioning_data(self, data: bytes):
        record = encode_record(data)
        current = self.read_provisioned_data(8)
        if current == data:
            return
        if current != b"\xff" * 8:
            raise ValueError("Pico already has a different Infuse ID; refusing to overwrite it")
        # Supply the entire reserved erase sector. Application and KV bytes are
        # outside this range. picotool verifies the write before we read it back.
        sector = record.ljust(SECTOR_SIZE, b"\xff")
        with tempfile.TemporaryDirectory(prefix="infuse-pico-") as directory:
            path = Path(directory) / "provisioning.bin"
            path.write_bytes(sector)
            self._exec(["load", "-v", str(path), "-t", "bin", "-o", hex(self._address)])
        if self._read_sector() != sector:
            raise RuntimeError("Pico provisioning readback does not match; device left in BOOTSEL")
        self._written = True

    def close(self, *, reset: bool = True):
        if reset and self._written:
            self._exec(["reboot"])
