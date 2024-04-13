#!/usr/bin/env python3

import ctypes
import random

from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from infuse_iot.argparse import ValidFile
from infuse_iot.commands import InfuseRpcCommand

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

class security_state(InfuseRpcCommand):
    HELP = 'Get the current device security state'
    DESCRIPTION = 'Get the current device security state'
    COMMAND_ID = 30000

    class request(ctypes.LittleEndianStructure):
        _fields_ = [
            ("challenge", 16 * ctypes.c_char),
        ]
        _pack_ = 1

    class response(ctypes.LittleEndianStructure):
        _fields_ = [
            ("header", challenge_response_header),
            ("response", challenge_response_basic_encr),
        ]
        _pack_ = 1

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument('--pem', type=ValidFile, help='Cloud .pem file for identity validation')

    def __init__(self, args):
        self.challenge = random.randbytes(16)
        self.pem = args.pem

    def request_struct(self):
        return self.request(self.challenge)

    def _decrypt_response(self, response):
        hdr = response.header
        rsp = response.response

        rb = bytes(response.response)
        with self.pem.open('r') as f:
            cloud_private_key = serialization.load_pem_private_key(f.read().encode('utf-8'), password=None)
        device_public_key = x25519.X25519PublicKey.from_public_bytes(bytes(hdr.device_public_key))
        shared_secret = cloud_private_key.exchange(device_public_key)
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=0x1234.to_bytes(4, 'little'),
            info=b"sign",
        )
        sign_key = hkdf.derive(shared_secret)

        cipher = ChaCha20Poly1305(sign_key)
        plaintext = cipher.decrypt(bytes(rsp.nonce), rb[12:], bytes(response.header))
        return challenge_response_basic.from_buffer_copy(plaintext)

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query current time ({return_code})")
            return

        # Decrypt identity information
        hdr = response.header

        print("Security State:")
        print(f"\tDevice Public Key: {bytes(hdr.device_public_key).hex()}")
        print(f"\t Cloud Public Key: {bytes(hdr.cloud_public_key).hex()}")
        print(f"\t          Network: 0x{hdr.network_id:06x}")
        if self.pem is None:
            print(f"\t         Identity: Cannot validate")
        else:
            challenge_rsp = self._decrypt_response(response)

            valid_response = bytes(challenge_rsp.challenge) == self.challenge

            print(f"\t         Response: {'Valid' if valid_response else 'Invalid'}")
            print(f"\t        Device ID: {challenge_rsp.device_id:016x}")
            print(f"\t  Identity Secret: {bytes(challenge_rsp.identity).hex()}")
