#!/usr/bin/env python3

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno


class security_public_keys(InfuseRpcCommand, defs.security_public_keys):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--skip", type=int, default=0, help="Skip first N keys")

    def __init__(self, args):
        self._skip = args.skip

    def request_struct(self):
        return self.request(
            self._skip,
        )

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to update key ({errno.strerror(-return_code)}, {-return_code})")
            return

        for key in response.public_keys:
            key_id = defs.rpc_enum_key_id(key.id)
            key_str = bytes(key.key).hex()
            print(f"{key_id.name:>30}: {key_str}")
