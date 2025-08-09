#!/usr/bin/env python3

import ctypes
import sys
from http import HTTPStatus
from json import loads

import infuse_iot.definitions.rpc as defs
from infuse_iot.api_client import Client
from infuse_iot.api_client.api.coap import get_coap_file_stats
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.credentials import get_api_key
from infuse_iot.definitions.rpc import rpc_enum_file_action
from infuse_iot.util.ctypes import UINT32_MAX
from infuse_iot.zephyr.errno import errno


def coap_server_file_stats(server: str, resource: str) -> tuple[int, int]:
    if server == coap_download.INFUSE_COAP_SERVER_ADDR:
        # Validate file prefix
        if not resource.startswith("file/"):
            sys.exit("Infuse-IoT COAP files start with 'file/'")
        api_filename = resource.removeprefix("file/")
        # Get COAP file information
        client = Client(base_url="https://api.infuse-iot.com").with_headers({"x-api-key": f"Bearer {get_api_key()}"})
        with client as client:
            response = get_coap_file_stats.sync_detailed(client=client, filename=api_filename)
            decoded = loads(response.content.decode("utf-8"))
            if response.status_code != HTTPStatus.OK:
                sys.exit(f"<{response.status_code}>: {decoded['message']}")
            return (decoded["len"], decoded["crc"])
    else:
        # Unknown, let the COAP download automatically determine
        # This does mean that duplicate file are not detected
        print("Custom COAP server, duplicate file detection disabled")
        return (UINT32_MAX, UINT32_MAX)


class coap_download(InfuseRpcCommand, defs.coap_download):
    INFUSE_COAP_SERVER_ADDR = "coap.dev.infuse-iot.com"
    INFUSE_COAP_SERVER_PORT = 5684

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--server",
            type=str,
            default=cls.INFUSE_COAP_SERVER_ADDR,
            help="COAP server name",
        )
        parser.add_argument(
            "--port",
            type=int,
            default=cls.INFUSE_COAP_SERVER_PORT,
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
        group.add_argument(
            "--for-copy",
            dest="action",
            action="store_const",
            const=rpc_enum_file_action.FILE_FOR_COPY,
            help="File to copy to other device",
        )

    def __init__(self, args):
        self.server = args.server.encode("utf-8")
        self.port = args.port
        self.resource = args.resource.encode("utf-8")
        self.action = args.action
        self.file_len, self.file_crc = coap_server_file_stats(args.server, args.resource)

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

        return request(
            self.server,
            self.port,
            2000,
            self.action,
            self.file_len,
            self.file_crc,
            self.resource,
        )

    def request_json(self):
        return {
            "server_address": self.server.decode("utf-8"),
            "server_port": str(self.port),
            "block_timeout_ms": "2000",
            "action": self.action.name,
            "resource_len": str(self.file_len),
            "resource_crc": str(self.file_crc),
            "resource": self.resource.decode("utf-8"),
        }

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to download file ({errno.strerror(-return_code)})")
            return
        else:
            print("File downloaded")
            print(f"\tLength: {response.resource_len}")
            print(f"\t   CRC: 0x{response.resource_crc:08x}")
