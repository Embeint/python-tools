#!/usr/bin/env python3

import argparse

import infuse_iot.definitions.rpc as defs
from infuse_iot.rpc_wrappers.file_write_basic import FileWriteTransfer
from infuse_iot.rpc_wrappers.filesystem_rm import _file_name
from infuse_iot.util.argparse import ValidFile


class filesystem_write(FileWriteTransfer, defs.file_write):
    NAME = "filesystem_write"
    HELP = "Write a file to the device filesystem"
    DESCRIPTION = HELP

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--file", "-f", type=ValidFile, required=True, help="Local file to upload")
        parser.add_argument(
            "--folder",
            type=str.upper,
            choices=[folder.name for folder in defs.rpc_enum_filesystem_folder],
            required=True,
            help="Destination folder",
        )
        parser.add_argument(
            "--filename",
            type=_file_name,
            required=True,
            help="Destination file name in hexadecimal (optional 0x prefix)",
        )
        parser.add_argument(
            "--identifier", type=_file_name, default=0, help="Metadata identifier in hexadecimal (default 0)"
        )

    def __init__(self, args):
        self._folder = defs.rpc_enum_filesystem_folder[args.folder]
        self._filename = args.filename
        self._identifier = args.identifier
        super().__init__(argparse.Namespace(file=args.file, action=defs.rpc_enum_file_action.WRITE_LITTLEFS))

    def request_struct(self):
        return self.request(
            action=self.action,
            folder=self._folder,
            filename=self._filename,
            identifier=self._identifier,
            file_crc=self._expected_crc,
        )

    def request_json(self):
        return {
            "action": self.action.name,
            "folder": self._folder.name,
            "filename": str(self._filename),
            "identifier": str(self._identifier),
            "file_crc": str(self._expected_crc),
        }
