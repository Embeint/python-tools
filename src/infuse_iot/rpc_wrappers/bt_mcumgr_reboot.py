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
from infuse_iot.zephyr.hci import error


class bt_mcumgr_reboot(InfuseRpcCommand, defs.bt_mcumgr_reboot):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--timeout", type=int, default=5000, help="Connection timeout (ms)")
        addr_group = parser.add_mutually_exclusive_group(required=True)
        addr_group.add_argument("--public", type=BtLeAddress, help="Public Bluetooth address")
        addr_group.add_argument("--random", type=BtLeAddress, help="Random Bluetooth address")

    def __init__(self, args):
        self.args = args

    def request_struct(self) -> defs.bt_mcumgr_reboot.request:
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
            self.args.timeout,
        )

    def handle_response(self, return_code, response):
        if return_code < 0:
            print(f"Failed to reboot ({errno.strerror(-return_code)})")
            return
        elif return_code > 0:
            print(f"Failed to reboot ({error.strerror(return_code)})")

        print("Reboot request sent")
