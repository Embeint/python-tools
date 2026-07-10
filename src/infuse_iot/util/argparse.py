#!/usr/bin/env python3

import argparse
import pathlib
import re
from typing import cast

import yaml

from infuse_iot.definitions.rpc import rpc_enum_bt_le_addr_type, rpc_struct_bt_addr_le
from infuse_iot.socket_comms import default_multicast_address
from infuse_iot.util.ctypes import bytes_to_uint8


class ValidFile:
    """Filesystem file that exists"""

    def __new__(cls, string: str) -> pathlib.Path:  # type: ignore
        p = pathlib.Path(string)
        if p.exists():
            if p.is_dir():
                raise argparse.ArgumentTypeError(f"{string} is a directory")
            else:
                return p
        else:
            raise argparse.ArgumentTypeError(f"{string} does not exist")


class ValidDir:
    """Filesystem directory that exists"""

    def __new__(cls, string: str) -> pathlib.Path:  # type: ignore
        p = pathlib.Path(string)
        if not p.exists():
            raise argparse.ArgumentTypeError(f"{string} does not exist")
        if not p.is_dir():
            raise argparse.ArgumentTypeError(f"{string} is not a directory")
        return p


class ValidRelease:
    """Infuse-IoT release folder"""

    def __init__(self, string: str):
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

    def __new__(cls, string: str) -> int:  # type: ignore
        pattern = r"((([0-9a-fA-F]{2}):){5})([0-9a-fA-F]{2})"

        if re.match(pattern, string):
            mac_cleaned = string.replace(":", "")
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
    def integer_value(cls, string: str) -> int:
        """Integer value from address string"""
        return cast(int, cls(string))


class InfuseDeviceId:
    """Infuse-IoT Device ID"""

    def __new__(cls, string: str) -> int:  # type: ignore
        try:
            return int(string, 16)
        except ValueError as e:
            raise argparse.ArgumentTypeError(f"{string} is not a valid hex ID") from e


class HexString:
    """Hexadecimal string"""

    def __new__(cls, string: str) -> bytes:  # type: ignore
        try:
            return bytes.fromhex(string)
        except ValueError as e:
            raise argparse.ArgumentTypeError(f"{string} is not a valid hex ID") from e

class ServerPort:
    """Server port number to socket tuple"""

    def __new__(cls, string: str) -> tuple[str, int]:  # type: ignore
        try:
            port = int(string)
        except ValueError as e:
            raise argparse.ArgumentTypeError(f"{string} is not a valid port number") from e
        if not (0 < port <= 65535):
            raise argparse.ArgumentTypeError(f"{string} is not a valid port number")
        if port % 2 == 0:
            raise argparse.ArgumentError(None, f"`--server-port` must be odd: {port}")
        return default_multicast_address(port)

def add_server_port_parser(parser: argparse.ArgumentParser, multi_port: bool = False):
    """Register `--server-port`with an argument parser. `multi_port` allows multiple port(s)"""
    parser.add_argument(
        '--server-port',
        dest='server_sock',
        default=[default_multicast_address()] if multi_port else default_multicast_address(),
        type=ServerPort,
        nargs= '+' if multi_port else None,
        help="Alternate port to use for Gateway connections (default 8751)"
    )
