#!/usr/bin/env python3

import base64
import ctypes
import random

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.epacket.packet import Auth
from infuse_iot.util.argparse import ValidFile
from infuse_iot.util.ctypes import bytes_to_uint8
from infuse_iot.zephyr.errno import errno


class challenge_response_header(ctypes.LittleEndianStructure):
    _fields_ = [
        ("cloud_public_key", 32 * ctypes.c_uint8),
        ("device_public_key", 32 * ctypes.c_uint8),
        ("network_id", ctypes.c_uint32),
        ("challenge_response_type", ctypes.c_uint8),
    ]
    _pack_ = 1


class challenge_response_basic_encr(ctypes.LittleEndianStructure):
    _fields_ = [
        ("nonce", 12 * ctypes.c_uint8),
        ("challenge", 16 * ctypes.c_uint8),
        ("identity", 16 * ctypes.c_uint8),
        ("device_id", ctypes.c_uint64),
        ("tag", 16 * ctypes.c_uint8),
    ]
    _pack_ = 1


class challenge_response_basic(ctypes.LittleEndianStructure):
    _fields_ = [
        ("challenge", 16 * ctypes.c_uint8),
        ("identity", 16 * ctypes.c_uint8),
        ("device_id", ctypes.c_uint64),
    ]
    _pack_ = 1


class security_state(InfuseRpcCommand, defs.security_state):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--pem", type=ValidFile, help="Cloud .pem file for identity validation")
        parser.add_argument("--base64", action="store_true", help="Print results as base64")

    def __init__(self, args):
        self.challenge = random.randbytes(16)
        self.pem = args.pem
        self.base64 = args.base64

    def auth_level(self):
        return Auth.NETWORK

    def request_struct(self):
        return self.request(bytes_to_uint8(self.challenge))

    def _decrypt_response(self, response):
        rsp = response.response

        rb = bytes(response.response)
        with self.pem.open("r") as f:
            cloud_private_key = serialization.load_pem_private_key(f.read().encode("utf-8"), password=None)
            assert isinstance(cloud_private_key, x25519.X25519PrivateKey)
        device_public_key = x25519.X25519PublicKey.from_public_bytes(bytes(response.device_public_key))
        shared_secret = cloud_private_key.exchange(device_public_key)
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=0x1234.to_bytes(4, "little"),
            info=b"sign",
        )
        sign_key = hkdf.derive(shared_secret)

        cipher = ChaCha20Poly1305(sign_key)
        plaintext = cipher.decrypt(bytes(rsp.nonce), rb[12:], bytes(response.header))
        return challenge_response_basic.from_buffer_copy(plaintext)

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query current time ({errno.strerror(-return_code)})")
            return

        def print_bytes(ctypes_array) -> str:
            b = bytes(ctypes_array)
            if self.base64:
                return base64.b64encode(b).decode("utf-8")
            return b.hex()

        print("Challenge:")
        print(f"\t  Challenge Bytes: {print_bytes(self.challenge)}")

        # Decrypt identity information
        print("Security State:")
        print(f"\tDevice Public Key: {print_bytes(response.device_public_key)}")
        print(f"\t Cloud Public Key: {print_bytes(response.cloud_public_key)}")
        print(f"\t          Network: 0x{response.network_id:06x}")
        if self.pem is None:
            print("\t         Identity: Cannot validate")
            print(f"\t             Type: {response.challenge_response_type}")
            print(f"\t              Raw: {print_bytes(response.challenge_response)}")
        else:
            challenge_rsp = self._decrypt_response(response)

            valid_response = bytes(challenge_rsp.challenge) == self.challenge

            print(f"\t         Response: {'Valid' if valid_response else 'Invalid'}")
            print(f"\t        Device ID: {challenge_rsp.device_id:016x}")
            print(f"\t  Identity Secret: {print_bytes(challenge_rsp.identity)}")
