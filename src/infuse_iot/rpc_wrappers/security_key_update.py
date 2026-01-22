#!/usr/bin/env python3

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.epacket.packet import Auth
from infuse_iot.util.argparse import ValidFile
from infuse_iot.util.ctypes import bytes_to_uint8
from infuse_iot.zephyr.errno import errno


class security_key_update(InfuseRpcCommand, defs.security_key_update):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--network-auth", action="store_true", help="Use network auth instead of device")
        parser.add_argument("--delete", action="store_true", help="Delete instead of writing key")
        parser.add_argument("--delay", type=int, default=2, help="Reboot delay (seconds)")
        key_group = parser.add_mutually_exclusive_group(required=True)
        key_group.add_argument("--secondary-root", type=ValidFile)

    def __init__(self, args):
        self._auth = Auth.NETWORK if args.network_auth else Auth.DEVICE
        self._key_action = defs.rpc_enum_key_action.KEY_DELETE if args.delete else defs.rpc_enum_key_action.KEY_WRITE
        self._delay = args.delay
        if args.secondary_root:
            self._key_id = defs.rpc_enum_key_id.SECONDARY_REMOTE_PUBLIC_KEY
            self._global_key_id = 0
            with args.secondary_root.open("r") as f:
                private_key = serialization.load_pem_private_key(f.read().encode("utf-8"), password=None)
                assert isinstance(private_key, x25519.X25519PrivateKey)
                public_key = private_key.public_key()
                self._key_bytes = public_key.public_bytes_raw()
        else:
            raise NotImplementedError("Unimplemented key type")

    def auth_level(self):
        return self._auth

    def request_struct(self):
        return self.request(
            self._key_id,
            self._key_action,
            self._global_key_id,
            bytes_to_uint8(self._key_bytes),
            self._delay,
        )

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to update key ({errno.strerror(-return_code)}, {-return_code})")
            return
        print(f"Updated key {self._key_id.name} on device")
