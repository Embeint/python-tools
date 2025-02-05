#!/usr/bin/env python3

import ctypes
import os

import infuse_iot.generated.rpc_definitions as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.util.argparse import BtLeAddress
from infuse_iot.util.ctypes import VLACompatLittleEndianStruct, bytes_to_uint8
from infuse_iot.zephyr.errno import errno


class kv_bt_peer(InfuseRpcCommand, defs.kv_write):
    HELP = "Configure the peer Bluetooth address"
    DESCRIPTION = "Configure the peer Bluetooth address"

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
        addr_group = parser.add_mutually_exclusive_group(required=True)
        addr_group.add_argument("--public", type=BtLeAddress, help="Public Bluetooth address")
        addr_group.add_argument("--random", type=BtLeAddress, help="Random Bluetooth address")
        addr_group.add_argument("--delete", action="store_true", help="Delete peer device")

    def __init__(self, args):
        if args.public:
            addr = bytes(BtLeAddress.to_ctype(defs.rpc_enum_bt_le_addr_type.PUBLIC, args.public))
        elif args.random:
            addr = bytes(BtLeAddress.to_ctype(defs.rpc_enum_bt_le_addr_type.RANDOM, args.random))
        elif args.delete:
            addr = b""
        else:
            raise NotImplementedError
        self.addr = addr

    def request_struct(self):
        addr_struct = self.kv_store_value_factory(50, self.addr)
        request_bytes = bytes(addr_struct)
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

        print_status("Peer address", response.rc[0])
