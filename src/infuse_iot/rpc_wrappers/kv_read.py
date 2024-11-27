#!/usr/bin/env python3

import ctypes
import errno

import infuse_iot.generated.rpc_definitions as defs
from infuse_iot.commands import InfuseRpcCommand


class kv_read(InfuseRpcCommand, defs.kv_read):
    class request(ctypes.LittleEndianStructure):
        _fields_ = [
            ("num", ctypes.c_uint8),
        ]
        _pack_ = 1

    class response:
        @classmethod
        def from_buffer_copy(cls, source, offset=0):
            values = []
            while len(source) > 0:

                class kv_store_header(ctypes.LittleEndianStructure):
                    _fields_ = [
                        ("id", ctypes.c_uint16),
                        ("len", ctypes.c_int16),
                    ]
                    _pack_ = 1

                header = kv_store_header.from_buffer_copy(source)
                if header.len > 0:

                    class kv_store_value(ctypes.LittleEndianStructure):
                        _fields_ = [
                            ("id", ctypes.c_uint16),
                            ("len", ctypes.c_int16),
                            ("data", ctypes.c_ubyte * header.len),
                        ]
                        _pack_ = 1

                    struct = kv_store_value.from_buffer_copy(source)
                else:
                    struct = header
                values.append(struct)
                source = source[ctypes.sizeof(struct) :]
            return values

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--keys", "-k", required=True, type=int, nargs="+", help="Keys to read")

    def __init__(self, args):
        self.keys = args.keys

    def request_struct(self):
        keys = (ctypes.c_uint16 * len(self.keys))(*self.keys)
        return bytes(self.request(len(self.keys))) + bytes(keys)

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Invalid data buffer ({errno.errorcode[-return_code]})")
            return

        for r in response:
            if r.len > 0:
                b = bytes(r.data)

                print(f"Key: {r.id} ({r.len} bytes):")
                print(f"\tHex: {b.hex()}")
                try:
                    print(f"\tStr: {b.decode('utf-8')}")
                except UnicodeDecodeError:
                    pass
            else:
                print(f"Key: {r.id} (Failed to read '{errno.errorcode[-r.len]}')")
