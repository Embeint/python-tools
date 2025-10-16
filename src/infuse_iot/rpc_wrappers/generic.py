#!/usr/bin/env python3

import ctypes

from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.util.ctypes import VLACompatLittleEndianStruct, bytes_to_uint8
from infuse_iot.zephyr.errno import errno


class generic(InfuseRpcCommand):
    NAME = "generic"
    HELP = "Generic RPC sender"
    DESCRIPTION = "Generic RPC sender"
    COMMAND_ID = -1

    class response(VLACompatLittleEndianStruct):
        _fields_ = []
        vla_field = ("val", 0 * ctypes.c_uint8)
        _pack_ = 1

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--rpc", type=int, required=True, help="RPC command ID")
        parser.add_argument("--args", type=str, default="", help="Arguments as byte string")

    def __init__(self, args):
        self.COMMAND_ID = args.rpc
        self._arg_bytes = bytes.fromhex(args.args)

    def request_struct(self):
        class request(ctypes.LittleEndianStructure):
            _fields_ = [
                ("val", len(self._arg_bytes) * ctypes.c_uint8),
            ]
            _pack_ = 1

        return request(bytes_to_uint8(self._arg_bytes))

    def handle_response(self, return_code, response):
        print(f"Return Code: {return_code} ({errno.strerror(-return_code)})")
        if len(response.val) > 0:
            print(f"   Response: {bytes(response.val).hex()}")
        else:
            print("   Response: None")
