#!/usr/bin/env python3


import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.definitions.rpc import (
    rpc_enum_bt_le_addr_type,
    rpc_enum_infuse_bt_characteristic,
    rpc_struct_bt_addr_le,
)
from infuse_iot.util.argparse import BtLeAddress
from infuse_iot.util.ctypes import bytes_to_uint8
from infuse_iot.zephyr.errno import errno
from infuse_iot.zephyr.hci import error


class bt_connect_infuse(InfuseRpcCommand, defs.bt_connect_infuse):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--timeout", type=int, default=5000, help="Connection timeout (ms)")
        parser.add_argument("--inactivity", type=int, default=0, help="Data inactivity timeout (ms)")
        parser.add_argument("--data", action="store_true", help="Subscribe to data characteristic")
        parser.add_argument(
            "--logging",
            action="store_true",
            help="Subscribe to serial logging characteristic",
        )
        addr_group = parser.add_mutually_exclusive_group(required=True)
        addr_group.add_argument("--public", type=BtLeAddress, help="Public Bluetooth address")
        addr_group.add_argument("--random", type=BtLeAddress, help="Random Bluetooth address")

    def __init__(self, args):
        self.args = args

    def request_struct(self) -> defs.bt_connect_infuse.request:
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

        # Requested characteristic subscriptions
        sub: int = rpc_enum_infuse_bt_characteristic.COMMAND
        if self.args.data:
            sub |= rpc_enum_infuse_bt_characteristic.DATA
        if self.args.logging:
            sub |= rpc_enum_infuse_bt_characteristic.LOGGING

        return self.request(
            peer,
            self.args.timeout,
            sub,
            self.args.inactivity,
        )

    def handle_response(self, return_code, response):
        if return_code < 0:
            print(f"Failed to connect ({errno.strerror(-return_code)})")
            return
        elif return_code > 0:
            print(f"Failed to connect ({error.strerror(return_code)})")

        print("Connected")
        print(f"\tDevice Public Key: {bytes(response.device_public_key).hex()}")
        print(f"\t Cloud Public Key: {bytes(response.cloud_public_key).hex()}")
        print(f"\t          Network: 0x{response.network_id:06x}")
