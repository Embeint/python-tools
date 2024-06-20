#!/usr/bin/env python3

import ctypes
import time
import random
import enum
import base64
import typing
from typing import List, Dict
from typing_extensions import Self

from infuse_iot.util.crypto import chachapoly_decrypt, chachapoly_encrypt
from infuse_iot.time import InfuseTime
from infuse_iot.database import DeviceDatabase


class JsonSerializer:
    """ "
    Class that can be trivially serialized to json.
    Requires that every internal field maps to an argument
    of the same name in __init__, with proper type hints.
    """

    def to_json(self) -> Dict:
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
    def from_json(cls, json) -> Self:
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
        BT_ADV = 2

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
    def serial(cls, auth=ePacketHop.auths.DEVICE) -> Self:
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
        RECEIVED_EPACKET = 7

    class BluetoothLeAddr(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_uint8),
            ("addr", 6 * ctypes.c_uint8),
        ]
        _pack_ = 1

    def __init__(self, route: List[ePacketHop], ptype: types, payload: bytes):
        self.ptype = ptype
        self.route = route
        self.payload = payload


class ePacketIn(ePacket):
    """ePacket received by a gateway"""

    class ePacketReceivedCommonHeader(ctypes.Structure):
        _fields_ = [
            ("_len_encr", ctypes.c_uint16),
            ("_rssi", ctypes.c_uint8),
            ("_if", ctypes.c_uint8),
        ]
        _pack_ = 1

        @property
        def len(self):
            return self._len_encr & 0x7FFF

        @property
        def encrypted(self):
            return (self._len_encr & 0x8000) != 0

        @property
        def interface(self):
            return ePacketHop.interfaces(self._if)

        @property
        def rssi(self):
            return 0 - self._rssi

    class ePacketReceivedDecryptedHeader(ctypes.Structure):
        _fields_ = [
            ("device_id", ctypes.c_uint64),
            ("gps_time", ctypes.c_uint32),
            ("_type", ctypes.c_uint8),
            ("flags", ctypes.c_uint16),
            ("sequence", ctypes.c_uint16),
            ("_key_id", 3 * ctypes.c_uint8),
        ]
        _pack_ = 1

        @property
        def type(self):
            return ePacket.types(self._type)

        @property
        def key_id(self):
            return int.from_bytes(self._key_id, "little")

    def __init__(self, route: List[ePacketHopIn], ptype: ePacket.types, payload: bytes):
        super().__init__(route, ptype, payload)

    @classmethod
    def from_serial(cls, database: DeviceDatabase, frame: bytes) -> List[Self]:
        header = ePacketSerialHeader.from_buffer_copy(frame)
        if header.flags & 0x8000:
            database.observe_serial(header.device_id, device_id=header.key_metadata)
            try:
                key = database.serial_device_key(header.device_id, header.gps_time)
            except Exception as exc:
                raise KeyError(f"No device key for {header.device_id:016x}") from exc
        else:
            database.observe_serial(header.device_id, network_id=header.key_metadata)
            key = database.serial_network_key(header.device_id, header.gps_time)

        decrypted = chachapoly_decrypt(key, frame[:11], frame[11:23], frame[23:])

        if header.type == cls.types.RECEIVED_EPACKET.value:
            contained = []
            while len(decrypted) > 0:
                h = cls.ePacketReceivedCommonHeader.from_buffer_copy(decrypted)
                t = decrypted[: h.len]
                decrypted = decrypted[h.len :]

                # Only Bluetooth advertising supported for now
                if h.interface != ePacketHopIn.interfaces.BT_ADV:
                    raise NotImplementedError

                # Decrypting payloads not currently supported
                if h.encrypted:
                    raise NotImplementedError

                t = t[ctypes.sizeof(h) :]
                addr = cls.BluetoothLeAddr.from_buffer_copy(t)
                t = t[ctypes.sizeof(addr) :]
                dh = cls.ePacketReceivedDecryptedHeader.from_buffer_copy(t)
                auth = (
                    ePacketHop.auths.DEVICE
                    if dh.flags & 0x8000
                    else ePacketHop.auths.NETWORK
                )
                t = t[ctypes.sizeof(dh) :]

                bt_hop = ePacketHopIn(
                    dh.device_id,
                    h.interface,
                    auth,
                    dh.key_id,
                    dh.gps_time,
                    dh.sequence,
                    h.rssi,
                )
                p = cls([bt_hop, header.hop_info()], dh.type, t)
                contained.append(p)
            return contained
        else:
            return [cls([header.hop_info()], cls.types(header.type), decrypted)]


class ePacketOut(ePacket):
    """ePacket to be transmitted by gateway"""

    def to_serial(self, database: DeviceDatabase) -> bytes:
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
        self._device_id_lower = value & 0xFFFFFFFF

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
