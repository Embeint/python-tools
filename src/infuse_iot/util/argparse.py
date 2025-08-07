#!/usr/bin/env python3

import argparse
import pathlib
import re
from typing import cast

import yaml

from infuse_iot.definitions.rpc import rpc_enum_bt_le_addr_type, rpc_struct_bt_addr_le
from infuse_iot.util.ctypes import bytes_to_uint8


class ValidFile:
    """Filesystem path that exists"""

    def __new__(cls, string) -> pathlib.Path:  # type: ignore
        p = pathlib.Path(string)
        if p.exists():
            return p
        else:
            raise argparse.ArgumentTypeError(f"{string} does not exist")


class ValidDir:
    """Filesystem directory that exists"""

    def __new__(cls, string) -> pathlib.Path:  # type: ignore
        p = pathlib.Path(string)
        if not p.exists():
            raise argparse.ArgumentTypeError(f"{string} does not exist")
        if not p.is_dir():
            raise argparse.ArgumentTypeError(f"{string} is not a directory")
        return p


class ValidRelease:
    """Infuse-IoT release folder"""

    def __init__(self, string):
        p: pathlib.Path = ValidDir(string)  # type: ignore
        metadata = p / "manifest.yaml"
        if not metadata.exists():
            raise argparse.ArgumentTypeError(f"{string} is not an Infuse-IoT release")
        self.dir = p
        metadata = self.dir / "manifest.yaml"
        with open(metadata, encoding="utf-8") as f:
            self.metadata = yaml.safe_load(f.read())


class BtLeAddress:
    """Bluetooth Low-Energy address"""

    def __new__(cls, string) -> int:  # type: ignore
        pattern = r"((([0-9a-fA-F]{2}):){5})([0-9a-fA-F]{2})"

        if re.match(pattern, string):
            mac_cleaned = string.replace(":", "").replace("-", "")
            addr = int(mac_cleaned, 16)
        else:
            try:
                addr = int(string, 16)
            except ValueError:
                raise argparse.ArgumentTypeError(f"{string} is not a Bluetooth address") from None
        return addr

    @classmethod
    def to_ctype(cls, addr_type: rpc_enum_bt_le_addr_type, value: int) -> rpc_struct_bt_addr_le:
        """Get a ctype representation of the Bluetooth address"""
        return rpc_struct_bt_addr_le(
            addr_type,
            bytes_to_uint8(value.to_bytes(6, "little")),
        )

    @classmethod
    def integer_value(cls, string) -> int:
        """Integer value from address string"""
        return cast(int, cls(string))
