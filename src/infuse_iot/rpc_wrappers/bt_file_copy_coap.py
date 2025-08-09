#!/usr/bin/env python3

import ctypes

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.definitions.rpc import rpc_enum_bt_le_addr_type, rpc_enum_file_action, rpc_struct_bt_addr_le
from infuse_iot.rpc_wrappers.coap_download import coap_download, coap_server_file_stats
from infuse_iot.util.argparse import BtLeAddress
from infuse_iot.util.ctypes import bytes_to_uint8
from infuse_iot.zephyr.errno import errno


class bt_file_copy_coap(InfuseRpcCommand, defs.bt_file_copy_coap):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--server",
            type=str,
            default=coap_download.INFUSE_COAP_SERVER_ADDR,
            help="COAP server name",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=coap_download.INFUSE_COAP_SERVER_PORT,
            help="COAP server port",
        )
        parser.add_argument(
            "--resource",
            "-r",
            type=str,
            required=True,
            help="Resource path",
        )
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--discard",
            dest="action",
            action="store_const",
            const=rpc_enum_file_action.DISCARD,
            help="Download file and discard without action",
        )
        group.add_argument(
            "--dfu",
            dest="action",
            action="store_const",
            const=rpc_enum_file_action.APP_IMG,
            help="Download complete image file and perform DFU",
        )
        group.add_argument(
            "--cpatch",
            dest="action",
            action="store_const",
            const=rpc_enum_file_action.APP_CPATCH,
            help="Download CPatch binary diff and perform DFU",
        )
        group.add_argument(
            "--nrf91-modem",
            dest="action",
            action="store_const",
            const=rpc_enum_file_action.NRF91_MODEM_DIFF,
            help="nRF91 LTE modem diff upgrade",
        )
        addr_group = parser.add_mutually_exclusive_group(required=True)
        addr_group.add_argument("--public", type=BtLeAddress, help="Public Bluetooth address")
        addr_group.add_argument("--random", type=BtLeAddress, help="Random Bluetooth address")
        parser.add_argument("--conn-timeout", type=int, default=5000, help="Connection timeout (ms)")
        parser.add_argument("--bt-pipelining", type=int, default=4, help="Bluetooth data pipelining")

    def __init__(self, args):
        self.server = args.server.encode("utf-8")
        self.port = args.port
        self.resource = args.resource.encode("utf-8")
        self.action = args.action
        self.conn_timeout = args.conn_timeout
        self.pipelining = args.bt_pipelining
        if args.public:
            self.peer = rpc_struct_bt_addr_le(
                rpc_enum_bt_le_addr_type.PUBLIC,
                bytes_to_uint8(args.public.to_bytes(6, "little")),
            )
        else:
            self.peer = rpc_struct_bt_addr_le(
                rpc_enum_bt_le_addr_type.RANDOM,
                bytes_to_uint8(args.random.to_bytes(6, "little")),
            )
        self.file_len, self.file_crc = coap_server_file_stats(args.server, args.resource)

    def request_struct(self):
        class request(ctypes.LittleEndianStructure):
            _fields_ = [
                *self.request._fields_,
                ("resource", (len(self.resource) + 1) * ctypes.c_char),
            ]
            _pack_ = 1

        return request(
            self.peer,
            self.conn_timeout,
            self.action,
            0,
            1,
            self.pipelining,
            self.server,
            self.port,
            2000,
            self.file_len,
            self.file_crc,
            self.resource,
        )

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to download file ({errno.strerror(-return_code)})")
            return
        else:
            print("File downloaded and copied")
            print(f"\tLength: {response.resource_len}")
            print(f"\t   CRC: 0x{response.resource_crc:08x}")
