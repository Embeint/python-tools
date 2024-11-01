#!/usr/bin/env python3

import ctypes

from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.generated.rpc_definitions import rpc_enum_file_action


class coap_download(InfuseRpcCommand):
    HELP = "Download a file from a COAP server (Infuse-IoT DTLS protected)"
    DESCRIPTION = "Download a file from a COAP server (Infuse-IoT DTLS protected)"
    COMMAND_ID = 30

    class response(ctypes.LittleEndianStructure):
        _fields_ = [
            ("resource_len", ctypes.c_uint32),
            ("resource_crc", ctypes.c_uint32),
        ]
        _pack_ = 1

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--server",
            type=str,
            default="coap.dev.infuse-iot.com",
            help="COAP server name",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=5684,
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
            "--nrf91-modem",
            dest="action",
            action="store_const",
            const=rpc_enum_file_action.NRF91_MODEM_DIFF,
            help="nRF91 LTE modem diff upgrade",
        )

    def __init__(self, args):
        self.server = args.server.encode("utf-8")
        self.port = args.port
        self.resource = args.resource.encode("utf-8")
        self.action = args.action

    def request_struct(self):

        class request(ctypes.LittleEndianStructure):
            _fields_ = [
                ("server_address", 48 * ctypes.c_char),
                ("server_port", ctypes.c_uint16),
                ("block_timeout_ms", ctypes.c_uint16),
                ("action", ctypes.c_uint8),
                ("resource_len", ctypes.c_uint32),
                ("resource_crc", ctypes.c_uint32),
                ("resource", (len(self.resource) + 1) * ctypes.c_char),
            ]
            _pack_ = 1

        UINT32_MAX = 2**32 - 1

        return request(
            self.server,
            self.port,
            2000,
            self.action,
            UINT32_MAX,
            UINT32_MAX,
            self.resource,
        )

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to download file ({return_code})")
            return
        else:
            print("File downloaded")
            print(f"\tLength: {response.resource_len}")
            print(f"\t   CRC: 0x{response.resource_crc:08x}")
