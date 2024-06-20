#!/usr/bin/env python3

import binascii
import base64
import urllib.parse
from typing import Dict

import requests
from requests.auth import HTTPBasicAuth

from infuse_iot.util.crypto import hkdf_derive


class DeviceDatabase:
    """Database of current device state"""

    _network_keys = {
        0x00: b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f",
    }

    class DeviceState:
        """Device State"""

        def __init__(self, address, network_id=None, device_id=None):
            self.address = address
            self.network_id = network_id
            self.device_id = device_id
            self.public_key = None
            self.shared_key = None

    def __init__(self):
        self.gateway = None
        self.devices: Dict[int, DeviceDatabase.DeviceState] = {}

    def observe_serial(
        self, address: int, network_id: int | None = None, device_id: int | None = None
    ):
        """Update device state based on observed packet"""
        if self.gateway is None:
            self.gateway = address
        if address not in self.devices:
            self.devices[address] = self.DeviceState(address)
        if network_id is not None:
            self.devices[address].network_id = network_id
        if device_id is not None:
            if (
                self.devices[address].device_id is not None
                and self.devices[address].device_id != device_id
            ):
                raise KeyError(f"Device key for {address:016x} has changed")
            self.devices[address].device_id = device_id

    def observe_security_state(
        self, address: int, cloud_key: bytes, device_key: bytes, network_id: int
    ):
        """Update device state based on security_state response"""
        if address not in self.devices:
            self.devices[address] = self.DeviceState(address)
        device_id = binascii.crc32(cloud_key + device_key) & 0x00FFFFFF
        self.devices[address].device_id = device_id
        self.devices[address].network_id = network_id
        self.devices[address].public_key = device_key

        # Query cloud for shared key
        key_enc = base64.b64encode(device_key).decode("utf-8")
        url = f"http://api.dev.infuse-iot.com/key/sharedSecret?publicKey={urllib.parse.quote_plus(key_enc)}"
        resp = requests.get(
            url,
            auth=HTTPBasicAuth("admin", "eBrtfxwUpgVv"),
            timeout=2.0,
        )
        # Decode and save shared key response
        self.devices[address].shared_key = base64.b64decode(
            resp.json()["key"].encode("utf-8")
        )

    def _serial_key(self, base, time_idx):
        return hkdf_derive(base, time_idx.to_bytes(4, "little"), b"serial")

    def has_public_key(self, address: int):
        """Does the database have the public key for this device?"""
        if address not in self.devices:
            return False
        return self.devices[address].public_key is not None

    def serial_network_key(self, address: int, gps_time: int):
        """Network key for serial interface"""
        if address not in self.devices:
            raise KeyError
        base = self._network_keys[self.devices[address].network_id]
        time_idx = gps_time // (60 * 60 * 24)

        return self._serial_key(base, time_idx)

    def serial_device_key(self, address: int, gps_time: int):
        """Device key for serial interface"""
        if address not in self.devices:
            raise KeyError
        d = self.devices[address]
        if d.device_id is None:
            raise KeyError
        base = self.devices[address].shared_key
        time_idx = gps_time // (60 * 60 * 24)

        return self._serial_key(base, time_idx)
