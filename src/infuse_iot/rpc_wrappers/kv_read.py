#!/usr/bin/env python3

import ctypes
from typing import Any

from tabulate import tabulate

import infuse_iot.definitions.kv as kv
import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno


class kv_read(InfuseRpcCommand, defs.kv_read):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--keys", "-k", required=True, type=int, nargs="+", help="Keys to read")

    def __init__(self, args):
        self.keys = args.keys

    def request_struct(self):
        keys = (ctypes.c_uint16 * len(self.keys))(*self.keys)
        return bytes(self.request(len(self.keys))) + bytes(keys)

    def request_json(self):
        return {"num": str(len(self.keys)), "keys": [str(k) for k in self.keys]}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Invalid data buffer ({errno.strerror(-return_code)})")
            return

        for r in response.values:
            if r.len > 0:
                b = bytes(r.data)
                try:
                    kv_type = kv.slots.ID_MAPPING[r.id]
                except KeyError:
                    print(f"Key: {r.id} ({r.len} bytes):")
                    print(f"\tHex: {b.hex()}")
                    continue
                kv_val = kv_type.vla_from_buffer_copy(b)

                print(f"Key: {kv_type.NAME} ({r.len} bytes):")
                print(f"\tHex: {b.hex()}")

                fields = []
                for field_name, field_val in kv_val.iter_fields():
                    fmt_val: Any
                    if isinstance(field_val, ctypes.Array):
                        if field_val._type_ == ctypes.c_char:
                            fmt_val = bytes(field_val).decode("utf-8")
                        elif field_val._type_ == ctypes.c_ubyte:
                            fmt_val = bytes(field_val).hex()
                        else:
                            fmt_val = list(field_val)
                    else:
                        fmt_val = field_val
                    fields.append((field_name, fmt_val))
                print(tabulate(fields))
            else:
                print(f"Key: {r.id} (Failed to read '{errno.strerror(-r.len)}')")
