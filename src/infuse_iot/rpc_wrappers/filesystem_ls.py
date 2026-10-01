#!/usr/bin/env python3

import tabulate

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand


class filesystem_ls(InfuseRpcCommand, defs.filesystem_ls):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--folder",
            type=str.upper,
            choices=[folder.name for folder in defs.rpc_enum_filesystem_folder],
            required=True,
            help="Folder to query",
        )
        parser.add_argument(
            "--skip", type=int, choices=range(256), metavar="N", default=0, help="Skip first N files (0-255)"
        )

    def __init__(self, args):
        self._folder = defs.rpc_enum_filesystem_folder[args.folder]
        self._skip = args.skip

    def request_struct(self):
        return self.request(folder=self._folder, skip=self._skip)

    def request_json(self):
        return {"folder": self._folder.name, "skip": str(self._skip)}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to list filesystem files ({self.return_code_str(return_code)})")
            return

        self.handle_json_response(
            {
                "total_files": response.total_files,
                "contained_files": response.contained_files,
                "files": [
                    {
                        "name": file.name,
                        "size": file.size,
                        "metadata": {
                            "timestamp": file.metadata.timestamp,
                            "identifier": file.metadata.identifier,
                            "crc": file.metadata.crc,
                        },
                    }
                    for file in response.files
                ],
            }
        )

    @classmethod
    def handle_json_response(cls, response: dict) -> None:
        table = []
        for file in response["files"]:
            metadata = file["metadata"]
            table.append(
                [
                    f"{int(file['name']):08x}",
                    int(file["size"]),
                    int(metadata["timestamp"]),
                    f"{int(metadata['identifier']):08x}",
                    f"{int(metadata['crc']):08x}",
                ]
            )

        print(f"Files returned: {response['contained_files']} / {response['total_files']}")
        headers = ["Name", "Size (bytes)", "Timestamp", "Identifier", "CRC"]
        print(tabulate.tabulate(table, headers=headers, disable_numparse=True))
