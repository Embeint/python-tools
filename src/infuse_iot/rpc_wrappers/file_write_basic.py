#!/usr/bin/env python3

import binascii

from rich.progress import (
    DownloadColumn,
    Progress,
    TransferSpeedColumn,
)

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import Auth, InfuseRpcCommand
from infuse_iot.definitions.rpc import rpc_enum_file_action
from infuse_iot.zephyr.errno import errno


class file_write_basic(InfuseRpcCommand, defs.file_write_basic):
    RPC_DATA_SEND = True

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--file",
            "-f",
            type=str,
            required=True,
            help="File to write",
        )
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--discard",
            dest="action",
            action="store_const",
            const=rpc_enum_file_action.DISCARD,
            help="Discard data without action",
        )
        group.add_argument(
            "--dfu",
            dest="action",
            action="store_const",
            const=rpc_enum_file_action.APP_IMG,
            help="Write complete image file and perform DFU",
        )
        group.add_argument(
            "--cpatch",
            dest="action",
            action="store_const",
            const=rpc_enum_file_action.APP_CPATCH,
            help="Write diff image file and perform DFU",
        )
        group.add_argument(
            "--bt-ctlr-dfu",
            dest="action",
            action="store_const",
            const=rpc_enum_file_action.BT_CTLR_IMG,
            help="Write Bluetooth controller image file and perform DFU",
        )
        group.add_argument(
            "--bt-ctlr-cpatch",
            dest="action",
            action="store_const",
            const=rpc_enum_file_action.BT_CTLR_CPATCH,
            help="Write Bluetooth controller diff file and perform DFU",
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
        self.file = args.file
        self.action = args.action
        self.progress = Progress(
            *Progress.get_default_columns(),
            DownloadColumn(),
            TransferSpeedColumn(),
        )
        self.task = None

        with open(self.file, "rb") as f:
            self.payload = f.read()

    def auth_level(self):
        return Auth.NETWORK

    def request_struct(self):
        return self.request(self.action, binascii.crc32(self.payload))

    def data_payload(self):
        print("Preparing for file upload...")
        return self.payload

    def data_progress_cb(self, offset):
        if self.task is None:
            self.progress.start()
            self.task = self.progress.add_task("Writing...", total=len(self.payload))
        self.progress.update(self.task, completed=offset)

    def handle_response(self, return_code, response):
        self.progress.stop()

        if return_code != 0:
            print(f"Failed to write file ({errno.strerror(-return_code)})")
            return
        print("File written")
        print(f"\tLength: {response.recv_len}")
        print(f"\t   CRC: 0x{response.recv_crc:08x}")
