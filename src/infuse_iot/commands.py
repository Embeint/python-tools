#!/usr/bin/env python3

"""Infuse-IoT SDK meta-tool command parent class"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import argparse
import ctypes
from abc import ABCMeta, abstractmethod
from typing import Any

import infuse_iot.rpc_wrappers as wrappers
from infuse_iot.epacket.packet import Auth


def wrapper_from_command_id(command_id: int):
    import importlib
    import pkgutil

    for _, name, _ in pkgutil.walk_packages(wrappers.__path__):
        full_name = f"{wrappers.__name__}.{name}"
        module = importlib.import_module(full_name)

        # Add RPC wrapper to parser
        cmd_cls = getattr(module, name)
        if command_id == cmd_cls.COMMAND_ID:
            return cmd_cls
    return None


class InfuseCommand(metaclass=ABCMeta):
    """Infuse-IoT SDK meta-tool command parent class"""

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser):
        """Add arguments for sub-command"""
        return

    def __init__(self, args: argparse.Namespace):
        return

    @abstractmethod
    def run(self) -> None:
        """Run the subcommand"""

    @property
    @abstractmethod
    def NAME(self) -> str:
        pass

    @property
    @abstractmethod
    def HELP(self) -> str:
        pass

    @property
    @abstractmethod
    def DESCRIPTION(self) -> str:
        pass


class InfuseRpcCommand:
    RPC_DATA_SEND: bool = False
    RPC_DATA_SEND_CHUNKED: bool = False
    RPC_DATA_RECEIVE: bool = False

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser) -> None:
        raise NotImplementedError

    def __init__(self, **kwargs):
        pass

    def auth_level(self) -> Auth:
        """Authentication level to run command with"""
        return Auth.DEVICE

    def command_timeout_ms(self) -> int:
        """Duration to wait for the RPC response in milliseconds"""
        return 10000

    def request_struct(self) -> ctypes.LittleEndianStructure | bytes:
        """RPC_CMD request structure"""
        raise NotImplementedError

    def request_json(self) -> dict[str, Any]:
        """RPC_CMD json structure (cloud)"""
        raise NotImplementedError

    def data_payload(self) -> bytes:
        """Payload to send with RPC_DATA"""
        raise NotImplementedError

    def data_payload_chunked(self) -> list[bytes]:
        """Payloads to send with RPC_DATA"""
        raise NotImplementedError

    def data_payload_recv_len(self) -> int:
        """Length of payload to receive with RPC_DATA"""
        return 0xFFFFFFFF

    def data_recv_cb(self, offset: int, data: bytes) -> None:
        """Data received callback"""
        raise NotImplementedError

    def data_progress_cb(self, offset: int) -> None:
        """Progress callback"""
        raise NotImplementedError

    def handle_response(self, return_code: int, response: ctypes.LittleEndianStructure | None) -> None:
        """Handle RPC_RSP"""
        raise NotImplementedError

    @classmethod
    def handle_json_response(cls, response: dict) -> None:
        """Handle json response from cloud"""
        raise NotImplementedError
