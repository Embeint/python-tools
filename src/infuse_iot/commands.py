#!/usr/bin/env python3

"""Infuse-IoT SDK meta-tool command parent class"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import argparse
import ctypes

from infuse_iot.epacket.packet import Auth


class InfuseCommand:
    """Infuse-IoT SDK meta-tool command parent class"""

    NAME = "N/A"
    HELP = "N/A"
    DESCRIPTION = "N/A"

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser):
        """Add arguments for sub-command"""

    def __init__(self, args: argparse.Namespace):
        pass

    def run(self):
        """Run the subcommand"""
        raise NotImplementedError


class InfuseRpcCommand:
    RPC_DATA = False

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

    def data_payload(self) -> bytes:
        """Payload to send with RPC_DATA"""
        raise NotImplementedError

    def data_progress_cb(self, offset: int) -> None:
        """Progress callback"""

    def handle_response(self, return_code, response):
        """Handle RPC_RSP"""
        raise NotImplementedError

    class VariableSizeResponse:
        base_fields: list[tuple[str, type[ctypes._SimpleCData]]] = []
        var_name = "x"
        var_type: type[ctypes._SimpleCData] = ctypes.c_ubyte

        @classmethod
        def from_buffer_copy(cls, source, offset=0):
            class response_base(ctypes.LittleEndianStructure):
                _fields_ = cls.base_fields
                _pack_ = 1

            var_bytes = (len(source) - offset) - ctypes.sizeof(response_base)
            assert var_bytes % ctypes.sizeof(cls.var_type) == 0
            var_num = var_bytes // ctypes.sizeof(cls.var_type)

            class response(ctypes.LittleEndianStructure):
                _fields_ = [*cls.base_fields, (cls.var_name, cls.var_type * var_num)]
                _pack_ = 1

            return response.from_buffer_copy(source, offset)
