#!/usr/bin/env python3

import ctypes
import os

import infuse_iot.generated.rpc_definitions as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.util.ctypes import VLACompatLittleEndianStruct, bytes_to_uint8


class kv_write(InfuseRpcCommand, defs.kv_write):
    HELP = "Write an arbitrary kv value"
    DESCRIPTION = "Write an arbitrary kv value"

    class request(ctypes.LittleEndianStructure):
        _fields_ = [
            ("num", ctypes.c_uint8),
        ]
        _pack_ = 1

    class response(VLACompatLittleEndianStruct):
        vla_field = ("rc", 0 * ctypes.c_int16)

    @staticmethod
    def kv_store_value_factory(id, value_bytes):
        class kv_store_value(ctypes.LittleEndianStructure):
            _fields_ = [
                ("id", ctypes.c_uint16),
                ("len", ctypes.c_uint16),
                ("data", ctypes.c_ubyte * len(value_bytes)),
            ]
            _pack_ = 1

        return kv_store_value(id, len(value_bytes), bytes_to_uint8(value_bytes))

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--key", type=int, required=True, help="KV key ID")
        parser.add_argument("--value", type=str, required=True, help="KV value as hex string")

    def __init__(self, args):
        self.key = args.key
        self.value = bytes.fromhex(args.value)

    def request_struct(self):
        kv_struct = self.kv_store_value_factory(self.key, self.value)
        request_bytes = bytes(kv_struct)
        return bytes(self.request(1)) + request_bytes

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Invalid data buffer ({os.strerror(-return_code)})")
            return

        def print_status(name, rc):
            if rc < 0:
                print(f"{name} failed to write ({os.strerror(-rc)})")
            elif rc == 0:
                print(f"{name} already matched")
            else:
                print(f"{name} updated")

        print_status(f"{self.key} value", response.rc[0])
