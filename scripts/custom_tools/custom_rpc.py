#!/usr/bin/env python3

"""Provide a minimal example of an out-of-tree Infuse RPC wrapper."""

import ctypes

from infuse_iot.commands import InfuseRpcCommand


class custom_rpc(InfuseRpcCommand):
    NAME = "custom_rpc"
    HELP = "Test out-of-tree RPC wrapper"
    DESCRIPTION = "Test out-of-tree RPC wrapper"
    COMMAND_ID = 0xABCD

    class request(ctypes.LittleEndianStructure):
        _fields_ = []
        _pack_ = 1

    class response(ctypes.LittleEndianStructure):
        _fields_ = []
        _pack_ = 1

    @classmethod
    def add_parser(cls, parser):
        return

    def __init__(self, args):
        return

    def request_struct(self):
        return self.request()

    def request_json(self):
        return {}

    def handle_response(self, return_code, response):
        print(f"Custom RPC returned {return_code}")
