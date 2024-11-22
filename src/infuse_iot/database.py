#!/usr/bin/env python3

import binascii
import base64
from typing import Dict

from infuse_iot.api_client import Client
from infuse_iot.api_client.api.default import get_shared_secret
from infuse_iot.api_client.models import Key
from infuse_iot.util.crypto import hkdf_derive
from infuse_iot.credentials import get_api_key, load_network


class NoKeyError(KeyError):
    """Generic key not found error"""


class UnknownNetworkError(NoKeyError):
    """Requested network is not known"""


class DeviceUnknownDeviceKey(NoKeyError):
    """Device key is not known for requested device"""


class DeviceUnknownNetworkKey(NoKeyError):
    """Network key is not known for requested device"""


class DeviceKeyChangedError(KeyError):
    """Device key for the requested device has changed"""


class DeviceDatabase:
    """Database of current device state"""

    _network_keys = {
        0x000000: b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10\x11\x12\x13\x14\x15\x16\x17\x18\x19\x1a\x1b\x1c\x1d\x1e\x1f",
    }
    _derived_keys = {}

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

    def observe_device(
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
                raise DeviceKeyChangedError(
                    f"Device key for {address:016x} has changed"
                )
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

        client = Client(base_url="https://api.dev.infuse-iot.com").with_headers(
            {"x-api-key": f"Bearer {get_api_key()}"}
        )

        with client as client:
            body = Key(base64.b64encode(device_key).decode("utf-8"))
            response = get_shared_secret.sync(client=client, body=body)
            key = base64.b64decode(response.key)
            self.devices[address].shared_key = key

    def _network_key(self, network_id: int, interface: str, gps_time: int):
        if network_id not in self._network_keys:
            try:
                info = load_network(network_id)
            except FileNotFoundError:
                raise UnknownNetworkError
            self._network_keys[network_id] = info["key"]
        base = self._network_keys[network_id]
        time_idx = gps_time // (60 * 60 * 24)

        key_id = (network_id, interface, time_idx)
        if key_id not in self._derived_keys:
            self._derived_keys[key_id] = hkdf_derive(
                base, time_idx.to_bytes(4, "little"), interface
            )

        return self._derived_keys[key_id]

    def _serial_key(self, base, time_idx):
        return hkdf_derive(base, time_idx.to_bytes(4, "little"), b"serial")

    def _bt_adv_key(self, base, time_idx):
        return hkdf_derive(base, time_idx.to_bytes(4, "little"), b"bt_adv")

    def _bt_gatt_key(self, base, time_idx):
        return hkdf_derive(base, time_idx.to_bytes(4, "little"), b"bt_gatt")

    def has_public_key(self, address: int):
        """Does the database have the public key for this device?"""
        if address not in self.devices:
            return False
        return self.devices[address].public_key is not None

    def has_network_id(self, address: int):
        """Does the database know the network ID for this device?"""
        if address not in self.devices:
            return False
        return self.devices[address].network_id is not None

    def serial_network_key(self, address: int, gps_time: int):
        """Network key for serial interface"""
        if address not in self.devices:
            raise DeviceUnknownNetworkKey
        network_id = self.devices[address].network_id

        return self._network_key(network_id, b"serial", gps_time)

    def serial_device_key(self, address: int, gps_time: int):
        """Device key for serial interface"""
        if address not in self.devices:
            raise DeviceUnknownDeviceKey
        d = self.devices[address]
        if d.device_id is None:
            raise DeviceUnknownDeviceKey
        base = self.devices[address].shared_key
        if base is None:
            raise DeviceUnknownDeviceKey
        time_idx = gps_time // (60 * 60 * 24)

        return self._serial_key(base, time_idx)

    def bt_adv_network_key(self, address: int, gps_time: int):
        """Network key for Bluetooth advertising interface"""
        if address not in self.devices:
            raise DeviceUnknownNetworkKey
        network_id = self.devices[address].network_id

        return self._network_key(network_id, b"bt_adv", gps_time)

    def bt_adv_device_key(self, address: int, gps_time: int):
        """Device key for Bluetooth advertising interface"""
        if address not in self.devices:
            raise DeviceUnknownDeviceKey
        d = self.devices[address]
        if d.device_id is None:
            raise DeviceUnknownDeviceKey
        base = self.devices[address].shared_key
        if base is None:
            raise DeviceUnknownDeviceKey
        time_idx = gps_time // (60 * 60 * 24)

        return self._bt_adv_key(base, time_idx)

    def bt_gatt_network_key(self, address: int, gps_time: int):
        """Network key for Bluetooth advertising interface"""
        if address not in self.devices:
            raise DeviceUnknownNetworkKey
        network_id = self.devices[address].network_id

        return self._network_key(network_id, b"bt_gatt", gps_time)

    def bt_gatt_device_key(self, address: int, gps_time: int):
        """Device key for Bluetooth advertising interface"""
        if address not in self.devices:
            raise DeviceUnknownDeviceKey
        d = self.devices[address]
        if d.device_id is None:
            raise DeviceUnknownDeviceKey
        base = self.devices[address].shared_key
        if base is None:
            raise DeviceUnknownDeviceKey
        time_idx = gps_time // (60 * 60 * 24)

        return self._bt_gatt_key(base, time_idx)
