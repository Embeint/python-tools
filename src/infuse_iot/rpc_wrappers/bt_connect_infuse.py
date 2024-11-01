#!/usr/bin/env python3

import ctypes

from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.generated.rpc_definitions import (
    rpc_struct_bt_addr_le,
    rpc_enum_bt_le_addr_type,
    rpc_enum_infuse_bt_characteristic,
)
from infuse_iot.util.argparse import BtLeAddress
from infuse_iot.util.ctypes import bytes_to_uint8


class bt_connect_infuse(InfuseRpcCommand):
    HELP = "Connect to an Infuse-IoT Bluetooth device"
    DESCRIPTION = "Connect to an Infuse-IoT Bluetooth device"
    COMMAND_ID = 50

    class request(ctypes.LittleEndianStructure):
        _fields_ = [
            ("peer", rpc_struct_bt_addr_le),
            ("conn_timeout_ms", ctypes.c_uint16),
            ("subscribe", ctypes.c_uint8),
            ("inactivity_timeout_ms", ctypes.c_uint16),
        ]
        _pack_ = 1

    class response(ctypes.LittleEndianStructure):
        _fields_ = [
            ("cloud_public_key", 32 * ctypes.c_uint8),
            ("device_public_key", 32 * ctypes.c_uint8),
            ("network_id", ctypes.c_uint32),
        ]
        _pack_ = 1

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--timeout", type=int, default=5000, help="Connection timeout (ms)"
        )
        parser.add_argument(
            "--inactivity", type=int, default=0, help="Data inactivity timeout (ms)"
        )
        parser.add_argument(
            "--data", action="store_true", help="Subscribe to data characteristic"
        )
        addr_group = parser.add_mutually_exclusive_group(required=True)
        addr_group.add_argument(
            "--public", type=BtLeAddress, help="Public Bluetooth address"
        )
        addr_group.add_argument(
            "--random", type=BtLeAddress, help="Random Bluetooth address"
        )

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

        # Requested characteristic subscriptions
        sub = rpc_enum_infuse_bt_characteristic.COMMAND
        if self.args.data:
            sub |= rpc_enum_infuse_bt_characteristic.DATA

        return self.request(
            peer,
            self.args.timeout,
            sub,
            self.args.inactivity,
        )

    def handle_response(self, return_code, response):
        if return_code < 0:
            print(f"Failed to connect ({return_code})")
            return

        if return_code == 1:
            print("Already connected")
        else:
            print("Connected")
        print(f"\tDevice Public Key: {bytes(response.device_public_key).hex()}")
        print(f"\t Cloud Public Key: {bytes(response.cloud_public_key).hex()}")
        print(f"\t          Network: 0x{response.network_id:06x}")
