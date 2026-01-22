#!/usr/bin/env python3

import base64
import binascii
import pathlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.types import (
    PrivateKeyTypes,
)

from infuse_iot.api_client import Client
from infuse_iot.api_client.api.key import get_shared_secret
from infuse_iot.api_client.models import Key
from infuse_iot.credentials import get_api_key, load_network
from infuse_iot.epacket.interface import Address as InterfaceAddress
from infuse_iot.util.crypto import hkdf_derive


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

    _network_keys: dict[int, bytes] = {}
    _derived_keys: dict[tuple[int, bytes, int], bytes] = {}

    class DeviceState:
        """Device State"""

        def __init__(
            self,
            infuse_id: int,
            network_id: int | None = None,
            device_key_id: int | None = None,
        ):
            self.infuse_id = infuse_id
            self.network_id = network_id
            self.device_key_id = device_key_id
            self.bt_addr: InterfaceAddress.BluetoothLeAddr | None = None
            self.device_public_key: bytes | None = None
            self.shared_key: bytes | None = None
            self._tx_gatt_seq = 0

        def gatt_sequence_num(self):
            """Persistent auto-incrementing sequence number for GATT"""
            self._tx_gatt_seq += 1
            return self._tx_gatt_seq

    def __init__(self, local_root: pathlib.Path | None) -> None:
        self.gateway: int | None = None
        self.devices: dict[int, DeviceDatabase.DeviceState] = {}
        self.bt_addr: dict[InterfaceAddress.BluetoothLeAddr, int] = {}
        self._local_root: PrivateKeyTypes | None = None
        if local_root:
            with local_root.open() as f:
                self._local_root = serialization.load_pem_private_key(f.read().encode("utf-8"), password=None)

    @property
    def has_local_root(self) -> bool:
        return self._local_root is not None

    def observe_device(
        self,
        infuse_id: int,
        network_id: int | None = None,
        device_key_id: int | None = None,
        bt_addr: InterfaceAddress.BluetoothLeAddr | None = None,
    ) -> None:
        """Update device state based on observed packet"""
        if self.gateway is None:
            self.gateway = infuse_id
        if infuse_id not in self.devices:
            self.devices[infuse_id] = self.DeviceState(infuse_id)
        if network_id is not None:
            self.devices[infuse_id].network_id = network_id
        if device_key_id is not None:
            if (
                self.devices[infuse_id].device_key_id is not None
                and self.devices[infuse_id].device_key_id != device_key_id
            ):
                raise DeviceKeyChangedError(f"Device key for {infuse_id:016x} has changed")
            self.devices[infuse_id].device_key_id = device_key_id
        if bt_addr is not None:
            self.bt_addr[bt_addr] = infuse_id
            self.devices[infuse_id].bt_addr = bt_addr

    def observe_security_state(
        self, infuse_id: int, cloud_pub_key: bytes, device_pub_key: bytes, network_id: int
    ) -> None:
        """Update device state based on security_state response"""
        if infuse_id not in self.devices:
            self.devices[infuse_id] = self.DeviceState(infuse_id)
        device_key_id = binascii.crc32(cloud_pub_key + device_pub_key) & 0x00FFFFFF
        self.devices[infuse_id].device_key_id = device_key_id
        self.devices[infuse_id].network_id = network_id
        self.devices[infuse_id].device_public_key = device_pub_key

        client = Client(base_url="https://api.infuse-iot.com").with_headers({"x-api-key": f"Bearer {get_api_key()}"})

        with client as client:
            body = Key(base64.b64encode(device_pub_key).decode("utf-8"))
            response = get_shared_secret.sync(client=client, body=body)
            if response is not None:
                key = base64.b64decode(response.key)
                self.devices[infuse_id].shared_key = key

    def _network_key(self, network_id: int, interface: bytes, gps_time: int) -> bytes:
        if network_id not in self._network_keys:
            try:
                info = load_network(network_id)
            except FileNotFoundError:
                raise UnknownNetworkError(network_id) from None
            self._network_keys[network_id] = info["key"]
        base = self._network_keys[network_id]
        time_idx = gps_time // (60 * 60 * 24)

        key_id = (network_id, interface, time_idx)
        if key_id not in self._derived_keys:
            self._derived_keys[key_id] = hkdf_derive(base, time_idx.to_bytes(4, "little"), interface)

        return self._derived_keys[key_id]

    def has_public_key(self, infuse_id: int) -> bool:
        """Does the database have the public key for this device?"""
        if infuse_id not in self.devices:
            return False
        return self.devices[infuse_id].device_public_key is not None

    def has_network_id(self, infuse_id: int) -> bool:
        """Does the database know the network ID for this device?"""
        if infuse_id not in self.devices:
            return False
        return self.devices[infuse_id].network_id is not None

    def infuse_id_from_bluetooth(self, bt_addr: InterfaceAddress.BluetoothLeAddr) -> int | None:
        """Get Bluetooth infuse_id associated with device"""
        return self.bt_addr.get(bt_addr, None)

    def _get_network_key(self, infuse_id: int, name: bytes, gps_time: int) -> bytes:
        if infuse_id not in self.devices:
            raise DeviceUnknownNetworkKey
        network_id = self.devices[infuse_id].network_id
        if network_id is None:
            raise DeviceUnknownNetworkKey
        return self._network_key(network_id, name, gps_time)

    def _get_device_key(self, infuse_id: int, name: bytes, gps_time: int) -> bytes:
        if infuse_id not in self.devices:
            raise DeviceUnknownDeviceKey
        d = self.devices[infuse_id]
        if d.device_key_id is None:
            raise DeviceUnknownDeviceKey
        base = self.devices[infuse_id].shared_key
        if base is None:
            raise DeviceUnknownDeviceKey
        time_idx = gps_time // (60 * 60 * 24)
        return hkdf_derive(base, time_idx.to_bytes(4, "little"), name)

    def serial_network_key(self, infuse_id: int, gps_time: int) -> bytes:
        """Network key for serial interface"""
        return self._get_network_key(infuse_id, b"serial", gps_time)

    def serial_device_key(self, infuse_id: int, gps_time: int) -> bytes:
        """Device key for serial interface"""
        return self._get_device_key(infuse_id, b"serial", gps_time)

    def bt_adv_network_key(self, infuse_id: int, gps_time: int) -> bytes:
        """Network key for Bluetooth advertising interface"""
        return self._get_network_key(infuse_id, b"bt_adv", gps_time)

    def bt_adv_device_key(self, infuse_id: int, gps_time: int) -> bytes:
        """Device key for Bluetooth advertising interface"""
        return self._get_device_key(infuse_id, b"bt_adv", gps_time)

    def bt_gatt_network_key(self, infuse_id: int, gps_time: int) -> bytes:
        """Network key for Bluetooth advertising interface"""
        return self._get_network_key(infuse_id, b"bt_gatt", gps_time)

    def bt_gatt_device_key(self, infuse_id: int, gps_time: int) -> bytes:
        """Device key for Bluetooth advertising interface"""
        return self._get_device_key(infuse_id, b"bt_gatt", gps_time)

    def udp_network_key(self, infuse_id: int, gps_time: int) -> bytes:
        """Network key for UDP interface"""
        return self._get_network_key(infuse_id, b"udp", gps_time)

    def udp_device_key(self, infuse_id: int, gps_time: int) -> bytes:
        """Device key for UDP interface"""
        return self._get_device_key(infuse_id, b"udp", gps_time)
