#!/usr/bin/env python3

import ctypes
import time
import random
import enum

from infuse_iot.crypto import hkdf_derive, chachapoly_decrypt, chachapoly_encrypt
from infuse_iot.time import InfuseTime

class data_types(enum.IntEnum):
    ECHO_REQ = 0
    ECHO_RSP = 1
    TDF = 2
    RPC_CMD = 3
    RPC_DATA = 4
    RPC_DATA_ACK = 5
    RPC_RSP = 6

class KeyDeriver:
    _network_keys = {
        0x123456: b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f"
    }
    _network_rotation_freq = {
        0: 60,
        1: 60*60,
        2: 24*60*60,
        3: 7*24*60*60,
    }
    _device_keys = {
        1234: b"\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f",
        1235: b"\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x20",
    }

    def __init__(self):
        self._cache = {}

    def derive(self, ids):
        if ids in self._cache:
            return self._cache[ids]

        if ids[2] & 0x8000:
            # Device Encryption
            base = self._device_keys[ids[1]]
            salt = ids[3]
        else:
            # Network Encryption
            base = self._network_keys[ids[3]]
            freq_idx = (ids[2] & 0x7000) >> 12
            salt = ids[4] // self._network_rotation_freq[freq_idx]

        derived = hkdf_derive(base, salt.to_bytes(4, 'little'), ids[0])
        self._cache[ids] = derived
        return derived

class ePacketDecoder:
    def __init__(self):
        self._key_deriver = KeyDeriver()
        self._seq = 0

    def decode_serial(self, serial_frame: bytes) -> dict:
        header = ePacketSerialHeader.from_buffer_copy(serial_frame)
        derived_key = self._key_deriver.derive(header.key_identifiers())
        decrypted = chachapoly_decrypt(derived_key, serial_frame[:11], serial_frame[11:23], serial_frame[23:])

        packet = {
            "device": header.device_id,
            "pkt_type": data_types(header.type),
            "unix_time": InfuseTime.unix_time_from_gps_seconds(header.gps_time),
            "sequence": header.sequence,
            "raw": decrypted.hex(),
        }
        return packet

    def encode_serial(self, packet: dict) -> bytes:
        # Create header
        gps_time = InfuseTime.gps_seconds_from_unix(int(time.time()))
        header = ePacketSerialHeader(
            version = 0,
            type = packet['pkt_type'],
            flags = 0x8000,
            gps_time = gps_time,
            sequence = self._seq,
            entropy = random.randint(0, 65535)
        )
        header.key_metadata = 1
        header.device_id = packet['device']
        self._seq += 1

        # Encrypt and return payload
        header_bytes = bytes(header)
        derived_key = self._key_deriver.derive(header.key_identifiers())
        ciphertext = chachapoly_encrypt(derived_key, header_bytes[:11], header_bytes[11:], bytes.fromhex(packet['raw']))
        return header_bytes + ciphertext

class ePacketSerialHeader(ctypes.Structure):
    """Serial packet header"""
    _fields_ = [
        ("version", ctypes.c_uint8),
        ("type", ctypes.c_uint8),
        ("flags", ctypes.c_uint16),
        ("_key_metadata", ctypes.c_uint8 * 3),
        ("_device_id_upper", ctypes.c_uint32),
        ("_device_id_lower", ctypes.c_uint32),
        ("gps_time", ctypes.c_uint32),
        ("sequence", ctypes.c_uint16),
        ("entropy", ctypes.c_uint16),
    ]
    _pack_ = 1

    @property
    def key_metadata(self):
        return int.from_bytes(self._key_metadata, 'little')

    @key_metadata.setter
    def key_metadata(self, value):
        self._key_metadata[:] = value.to_bytes(3, 'little')

    @property
    def device_id(self):
        return (self._device_id_upper << 32) | self._device_id_lower

    @device_id.setter
    def device_id(self, value):
        self._device_id_upper = (value >> 32)
        self._device_id_lower = (value & 0xFFFFFF)

    @classmethod
    def parse(cls, frame: bytes):
        """Parse serial frame into header and payload length"""
        return ePacketSerialHeader.from_buffer_copy(frame), len(frame) - ctypes.sizeof(ePacketSerialHeader) - 16

    def key_identifiers(self):
        return (b"serial", self.device_id, self.flags, self.key_metadata, self.gps_time)
