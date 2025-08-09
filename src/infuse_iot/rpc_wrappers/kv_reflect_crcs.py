#!/usr/bin/env python3

import ctypes

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.util.ctypes import VLACompatLittleEndianStruct
from infuse_iot.zephyr.errno import errno


class kv_reflect_crcs(InfuseRpcCommand, defs.kv_reflect_crcs):
    HELP = "Read KV store reflection crc values"
    DESCRIPTION = "Read KV store reflection crc values"

    class response(VLACompatLittleEndianStruct):
        _fields_ = [
            ("num", ctypes.c_uint16),
            ("remaining", ctypes.c_uint16),
        ]
        vla_field = ("crcs", 0 * defs.rpc_struct_kv_store_crc)
        _pack_ = 1

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--offset", type=int, default=0, help="Offset to start CRC read at")

    def __init__(self, args):
        self.offset = args.offset

    def request_struct(self):
        return self.request(self.offset)

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Invalid query ({errno.strerror(-return_code)})")
            return

        print(f"Slot CRCs ({response.remaining} remaining):")
        for slot in response.crcs:
            print(f"\t{slot.id:5d}: 0x{slot.crc:08x}")
