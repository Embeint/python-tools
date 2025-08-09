#!/usr/bin/env python3


import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.definitions.rpc import (
    rpc_enum_bt_le_addr_type,
    rpc_struct_bt_addr_le,
)
from infuse_iot.util.argparse import BtLeAddress
from infuse_iot.util.ctypes import bytes_to_uint8
from infuse_iot.zephyr.errno import errno


class bt_disconnect(InfuseRpcCommand, defs.bt_disconnect):
    @classmethod
    def add_parser(cls, parser):
        addr_group = parser.add_mutually_exclusive_group(required=True)
        addr_group.add_argument("--public", type=BtLeAddress, help="Public Bluetooth address")
        addr_group.add_argument("--random", type=BtLeAddress, help="Random Bluetooth address")

    def __init__(self, args):
        self.args = args

    def request_struct(self):
        if self.args.public:
            peer = rpc_struct_bt_addr_le(
                rpc_enum_bt_le_addr_type.PUBLIC,
                bytes_to_uint8(self.args.public.to_bytes(6, "little")),
            )
        else:
            peer = rpc_struct_bt_addr_le(
                rpc_enum_bt_le_addr_type.RANDOM,
                bytes_to_uint8(self.args.random.to_bytes(6, "little")),
            )

        return self.request(
            peer,
        )

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to disconnect ({errno.strerror(-return_code)})")
            return
        else:
            print("Disconnected")
