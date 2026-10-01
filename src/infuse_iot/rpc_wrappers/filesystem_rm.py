#!/usr/bin/env python3

import argparse

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand


def _file_name(value: str) -> int:
    try:
        name = int(value, 16)
    except ValueError:
        raise argparse.ArgumentTypeError("File name must be a hexadecimal uint32") from None
    if not 0 <= name <= 0xFFFFFFFF:
        raise argparse.ArgumentTypeError("File name must be a hexadecimal uint32")
    return name


class filesystem_rm(InfuseRpcCommand, defs.filesystem_rm):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--folder",
            type=str.upper,
            choices=[folder.name for folder in defs.rpc_enum_filesystem_folder],
            required=True,
            help="Folder containing the file",
        )
        parser.add_argument(
            "--file",
            type=_file_name,
            required=True,
            help="Hexadecimal file name from filesystem_ls (optional 0x prefix)",
        )

    def __init__(self, args):
        self._folder = defs.rpc_enum_filesystem_folder[args.folder]
        self._file = args.file

    def request_struct(self):
        return self.request(folder=self._folder, file=self._file)

    def request_json(self):
        return {"folder": self._folder.name, "file": str(self._file)}

    def handle_response(self, return_code, _response):
        if return_code != 0:
            print(f"Failed to delete filesystem file ({self.return_code_str(return_code)})")
            return

        print(f"Deleted {self._folder.name}/{self._file:08x}")
