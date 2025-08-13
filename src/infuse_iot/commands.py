#!/usr/bin/env python3

"""Infuse-IoT SDK meta-tool command parent class"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import argparse
import ctypes
from abc import ABCMeta, abstractmethod
from typing import Any

from infuse_iot.epacket.packet import Auth


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
    RPC_DATA_SEND = False
    RPC_DATA_RECEIVE = False

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser):
        raise NotImplementedError

    def __init__(self, **kwargs):
        pass

    def auth_level(self) -> Auth:
        """Authentication level to run command with"""
        return Auth.DEVICE

    def request_struct(self) -> ctypes.LittleEndianStructure:
        """RPC_CMD request structure"""
        raise NotImplementedError

    def request_json(self) -> dict[str, Any]:
        """RPC_CMD json structure (cloud)"""
        raise NotImplementedError

    def data_payload(self) -> bytes:
        """Payload to send with RPC_DATA"""
        raise NotImplementedError

    def data_payload_recv_len(self) -> int:
        """Length of payload to receive with RPC_DATA"""
        return 0xFFFFFFFF

    def data_recv_cb(self, offset: int, data: bytes) -> None:
        """Data received callback"""

    def data_progress_cb(self, offset: int) -> None:
        """Progress callback"""

    def handle_response(self, return_code: int, response: ctypes.LittleEndianStructure | None):
        """Handle RPC_RSP"""
        raise NotImplementedError
