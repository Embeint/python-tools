#!/usr/bin/env python3

import ctypes
import time
import random
import enum
import base64
import typing
from typing import List

from infuse_iot.util.crypto import chachapoly_decrypt, chachapoly_encrypt
from infuse_iot.time import InfuseTime
from infuse_iot.database import DeviceDatabase


class JsonSerializer:
    """ "
    Class that can be trivially serialized to json.
    Requires that every internal field maps to an argument
    of the same name in __init__, with proper type hints.
    """

    def to_json(self):
        """Convert simple class to json"""
        out = {}
        for name, val in self.__dict__.items():
            if isinstance(val, enum.Enum):
                out[name] = val.value
            elif isinstance(val, bytes):
                out[name] = base64.b64encode(val).decode("utf-8")
            elif isinstance(val, list):
                out[name] = [x.to_json() for x in val]
            elif isinstance(val, JsonSerializer):
                out[name] = val.to_json()
            else:
                out[name] = val
        return out

    @classmethod
    def from_json(cls, json):
        """Construct simple class from json"""
        args = {}
        for name, type_hint in typing.get_type_hints(cls.__init__).items():
            if type_hint is bytes:
                val = base64.b64decode(json[name].encode("utf-8"))
            elif isinstance(json[name], list):
                val = [typing.get_args(type_hint)[0].from_json(x) for x in json[name]]
            else:
                val = type_hint(json[name])
            args[name] = val
        return cls(**args)


class ePacketHop(JsonSerializer):
    """Base ePacket hop class"""

    class interfaces(enum.Enum):
        """Interface options"""

        SERIAL = 0
        UDP = 1

    class auths(enum.Enum):
        """Authorisation options"""

        DEVICE = 0
        NETWORK = 1

    def __init__(self, address: int, interface: interfaces, auth: auths):
        self.address = address
        self.interface = interface
        self.auth = auth


class ePacketHopIn(ePacketHop):
    """Incoming ePacket hops"""

    def __init__(
        self,
        address: int,
        interface: ePacketHop.interfaces,
        auth: ePacketHop.auths,
        auth_id: int,
        gps_time: int,
        sequence: int,
        rssi: int,
    ):
        super().__init__(address, interface, auth)
        self.auth_id = auth_id
        self.sequence = sequence
        self.gps_time = gps_time
        self.rssi = rssi


class ePacketHopOut(ePacketHop):
    """Outgoing ePacket hops"""

    @classmethod
    def serial(cls, auth=ePacketHop.auths.DEVICE):
        """Local serial hop"""
        return cls(0, cls.interfaces.SERIAL, auth)


class ePacket(JsonSerializer):
    class types(enum.Enum):
        ECHO_REQ = 0
        ECHO_RSP = 1
        TDF = 2
        RPC_CMD = 3
        RPC_DATA = 4
        RPC_DATA_ACK = 5
        RPC_RSP = 6

    def __init__(self, route: List[ePacketHop], ptype: types, payload: bytes):
        self.ptype = ptype
        self.route = route
        self.payload = payload


class ePacketIn(ePacket):
    """ePacket received by a gateway"""

    @classmethod
    def from_serial(cls, database: DeviceDatabase, frame: bytes):
        header = ePacketSerialHeader.from_buffer_copy(frame)
        if header.flags & 0x8000:
            database.observe_serial(header.device_id, device_id=header.key_metadata)
            key = database.serial_device_key(header.device_id, header.gps_time)
        else:
            database.observe_serial(header.device_id, network_id=header.key_metadata)
            key = database.serial_network_key(header.device_id, header.gps_time)

        decrypted = chachapoly_decrypt(key, frame[:11], frame[11:23], frame[23:])

        return cls([header.hop_info()], cls.types(header.type), decrypted)


class ePacketOut(ePacket):
    """ePacket to be transmitted by gateway"""

    def to_serial(self, database: DeviceDatabase):
        """Encode and encrypt packet for serial transmission"""
        gps_time = InfuseTime.gps_seconds_from_unix(int(time.time()))
        route = self.route[0]

        if route.auth == ePacketHop.auths.NETWORK:
            flags = 0x0000
            key_metadata = database.devices[route.address].network_id
            key = database.serial_network_key(route.address, gps_time)
        else:
            flags = 0x8000
            key_metadata = database.devices[route.address].device_id
            key = database.serial_device_key(route.address, gps_time)

        # Create header
        header = ePacketSerialHeader(
            version=0,
            type=self.ptype.value,
            flags=flags,
            gps_time=gps_time,
            sequence=0,
            entropy=random.randint(0, 65535),
        )
        header.key_metadata = key_metadata
        header.device_id = database.gateway

        # Encrypt and return payload
        header_bytes = bytes(header)
        ciphertext = chachapoly_encrypt(
            key, header_bytes[:11], header_bytes[11:], self.payload
        )
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
        return int.from_bytes(self._key_metadata, "little")

    @key_metadata.setter
    def key_metadata(self, value):
        self._key_metadata[:] = value.to_bytes(3, "little")

    @property
    def device_id(self):
        return (self._device_id_upper << 32) | self._device_id_lower

    @device_id.setter
    def device_id(self, value):
        self._device_id_upper = value >> 32
        self._device_id_lower = value & 0xFFFFFF

    @classmethod
    def parse(cls, frame: bytes):
        """Parse serial frame into header and payload length"""
        return (
            ePacketSerialHeader.from_buffer_copy(frame),
            len(frame) - ctypes.sizeof(ePacketSerialHeader) - 16,
        )

    def hop_info(self) -> ePacketHopIn:
        auth_level = (
            ePacketHop.auths.DEVICE if self.flags & 0x8000 else ePacketHop.auths.NETWORK
        )
        return ePacketHopIn(
            self.device_id,
            ePacketHop.interfaces.SERIAL,
            auth_level,
            self.key_metadata,
            self.gps_time,
            self.sequence,
            0,
        )
