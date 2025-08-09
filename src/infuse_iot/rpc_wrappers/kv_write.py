#!/usr/bin/env python3

import ctypes
import os
import sys

import infuse_iot.definitions.kv as kv_defs
import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.util.ctypes import VLACompatLittleEndianStruct, bytes_to_uint8
from infuse_iot.zephyr.errno import errno


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
        parser.add_argument("--key", "-k", type=int, required=True, help="KV key ID")
        v_parser = parser.add_mutually_exclusive_group(required=True)
        v_parser.add_argument("--value", "-v", type=str, help="KV value as hex string")
        v_parser.add_argument("--string", "-s", type=str, help="KV string")

    def __init__(self, args):
        self.key = args.key
        if args.value is not None:
            self.value = bytes.fromhex(args.value)
        elif args.string is not None:
            if self.key not in kv_defs.slots.ID_MAPPING:
                sys.exit(f"Key ID {self.key} not known, cannot validate")
            kv_type = kv_defs.slots.ID_MAPPING[self.key]
            # Validate key type is a string
            if (
                len(kv_type._fields_) != 0
                or not hasattr(kv_type, "vla_field")
                or not isinstance(kv_type.vla_field, tuple)
                or kv_type.vla_field[1] != kv_defs.structs.kv_string
            ):
                sys.exit(f"Key ID {self.key} is not a string value")

            str_val = args.string.encode("utf-8") + b"\x00"
            self.value = len(str_val).to_bytes(1, "little") + str_val
        else:
            raise NotImplementedError("Unimplmented value parsing")

    def request_struct(self):
        kv_struct = self.kv_store_value_factory(self.key, self.value)
        request_bytes = bytes(kv_struct)
        return bytes(self.request(1)) + request_bytes

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Invalid data buffer ({errno.strerror(-return_code)})")
            return

        def print_status(name, rc):
            if rc < 0:
                print(f"{name} failed to write ({os.strerror(-rc)})")
            elif rc == 0:
                print(f"{name} already matched")
            else:
                print(f"{name} updated")

        print_status(f"{self.key} value", response.rc[0])
