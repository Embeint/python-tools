#!/usr/bin/env python3

"""Infuse-IoT SDK meta-tool command parent class"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import argparse
import ctypes

from infuse_iot.epacket import ePacketHop


class InfuseCommand:
    """Infuse-IoT SDK meta-tool command parent class"""

    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser):
        """Add arguments for sub-command"""

    def __init__(self, **kwargs):
        pass

    def run(self):
        """Run the subcommand"""
        raise NotImplementedError


class InfuseRpcCommand:
    @classmethod
    def add_parser(cls, parser: argparse.ArgumentParser):
        raise NotImplementedError

    def __init__(self, **kwargs):
        pass

    def auth_level(self):
        """Authentication level to run command with"""
        return ePacketHop.auths.DEVICE

    def request_struct(self):
        raise NotImplementedError

    def handle_response(self, return_code, response):
        raise NotImplementedError

    class VariableSizeResponse:
        base_fields = []
        var_name = "x"
        var_type = ctypes.c_ubyte

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
