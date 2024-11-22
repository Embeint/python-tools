#!/usr/bin/env python3

import ctypes
import enum
import base64
import time
import random

from typing import List, Dict, Tuple
from typing_extensions import Self

from infuse_iot.common import InfuseType
from infuse_iot.epacket.common import Serializable
from infuse_iot.epacket.interface import ID as Interface
from infuse_iot.epacket.interface import Address
from infuse_iot.util.crypto import chachapoly_decrypt, chachapoly_encrypt
from infuse_iot.database import DeviceDatabase, NoKeyError
from infuse_iot.time import InfuseTime


class Auth(enum.Enum):
    """Authorisation options"""

    DEVICE = 0
    NETWORK = 1


class Flags(enum.IntEnum):
    ENCR_DEVICE = 0x8000
    ENCR_NETWORK = 0x0000


class InterfaceAddress(Serializable):
    class SerialAddr(Serializable):
        def __str__(self):
            return ""

        def len(self):
            return 0

        def to_json(self) -> Dict:
            return {"i": "SERIAL"}

        @classmethod
        def from_json(cls, values: Dict) -> Self:
            return cls()

    class BluetoothLeAddr(Serializable):
        class CtypesFormat(ctypes.Structure):
            _fields_ = [
                ("type", ctypes.c_uint8),
                ("addr", 6 * ctypes.c_uint8),
            ]
            _pack_ = 1

        def __init__(self, addr_type, addr_val):
            self.addr_type = addr_type
            self.addr_val = addr_val

        def __str__(self):
            t = "random" if self.addr_type == 1 else "public"
            v = ":".join([f"{x:02x}" for x in self.addr_val.to_bytes(6, "big")])
            return f"{v} ({t})"

        def len(self):
            return ctypes.sizeof(self.CtypesFormat)

        def to_json(self) -> Dict:
            return {"i": "BT", "t": self.addr_type, "v": self.addr_val}

        @classmethod
        def from_json(cls, values: Dict) -> Self:
            return cls(values["t"], values["v"])

    def __init__(self, val):
        self.val = val

    def __str__(self):
        return str(self.val)

    def len(self):
        return self.val.len()

    def to_json(self) -> Dict:
        return self.val.to_json()

    @classmethod
    def from_json(cls, values: Dict) -> Self:
        if values["i"] == "BT":
            return cls(cls.BluetoothLeAddr.from_json(values))
        elif values["i"] == "SERIAL":
            return cls(cls.SerialAddr())
        raise NotImplementedError("Unknown address type")

    @classmethod
    def from_bytes(cls, interface: Interface, stream: bytes) -> Self:
        assert interface in [
            Interface.BT_ADV,
            Interface.BT_PERIPHERAL,
            Interface.BT_CENTRAL,
        ]

        c = cls.BluetoothLeAddr.CtypesFormat.from_buffer_copy(stream)
        return cls.BluetoothLeAddr(c.type, int.from_bytes(bytes(c.addr), "little"))


class HopOutput(Serializable):
    def __init__(self, infuse_id: int, interface: Interface, auth: Auth):
        self.infuse_id = infuse_id
        self.interface = interface
        self.auth = auth

    def to_json(self) -> Dict:
        return {
            "id": self.infuse_id,
            "interface": self.interface.value,
            "auth": self.auth.value,
        }

    @classmethod
    def from_json(cls, values: Dict) -> Self:
        return cls(
            infuse_id=values["id"],
            interface=Interface(values["interface"]),
            auth=Auth(values["auth"]),
        )

    @classmethod
    def serial(cls, auth=Auth.DEVICE) -> Self:
        """Local serial hop"""
        return cls(0, Interface.SERIAL, auth)


class HopReceived(Serializable):
    def __init__(
        self,
        infuse_id: int,
        interface: Interface,
        interface_address: InterfaceAddress,
        auth: Auth,
        key_identifier: int,
        gps_time: int,
        sequence: int,
        rssi: int,
    ):
        self.infuse_id = infuse_id
        self.interface = interface
        self.interface_address = interface_address
        self.auth = auth
        self.key_identifier = key_identifier
        self.gps_time = gps_time
        self.sequence = sequence
        self.rssi = rssi

    def to_json(self) -> Dict:
        return {
            "id": self.infuse_id,
            "interface": self.interface.value,
            "interface_addr": self.interface_address.to_json(),
            "auth": self.auth.value,
            "key_id": self.key_identifier,
            "time": self.gps_time,
            "seq": self.sequence,
            "rssi": self.rssi,
        }

    @classmethod
    def from_json(cls, values: Dict) -> Self:
        interface = Interface(values["interface"])
        return cls(
            infuse_id=values["id"],
            interface=interface,
            interface_address=InterfaceAddress.from_json(values["interface_addr"]),
            auth=Auth(values["auth"]),
            key_identifier=values["key_id"],
            gps_time=values["time"],
            sequence=values["seq"],
            rssi=values["rssi"],
        )


class PacketReceived(Serializable):
    """ePacket received by a gateway"""

    def __init__(self, route: List[HopReceived], ptype: InfuseType, payload: bytes):
        # [Original Transmission, hop, hop, serial]
        self.route = route
        self.ptype = ptype
        self.payload = payload

    def to_json(self) -> Dict:
        """Convert class to json dictionary"""
        return {
            "route": [x.to_json() for x in self.route],
            "type": self.ptype.value,
            "payload": base64.b64encode(self.payload).decode("utf-8"),
        }

    @classmethod
    def from_json(cls, values: Dict) -> Self:
        """Reconstruct class from json dictionary"""
        return cls(
            route=[HopReceived.from_json(x) for x in values["route"]],
            ptype=InfuseType(values["type"]),
            payload=base64.b64decode(values["payload"].encode("utf-8")),
        )

    @classmethod
    def from_serial(cls, database: DeviceDatabase, serial_frame: bytes) -> List[Self]:
        header, decrypted = CtypeSerialFrame.decrypt(database, serial_frame)

        # Packet from local gateway
        if header.type != InfuseType.RECEIVED_EPACKET:
            return [cls([header.hop_received()], header.type, decrypted)]

        # Extract packets contained in payload
        packets = []
        buffer = bytearray(decrypted)
        while len(buffer) > 0:
            common_header = CtypePacketReceived.CommonHeader.from_buffer_copy(buffer)
            packet_bytes = buffer[: common_header.len]
            del buffer[: common_header.len]
            del packet_bytes[: ctypes.sizeof(common_header)]

            # Only Bluetooth advertising supported for now
            decode_mapping = {
                Interface.BT_ADV: CtypeBtAdvFrame,
                Interface.BT_PERIPHERAL: CtypeBtGattFrame,
                Interface.BT_CENTRAL: CtypeBtGattFrame,
            }
            if common_header.interface not in decode_mapping:
                raise NotImplementedError
            frame_type = decode_mapping[common_header.interface]

            # Extract interface address (Only Bluetooth supported)
            addr = InterfaceAddress.from_bytes(common_header.interface, packet_bytes)
            del packet_bytes[: addr.len()]

            # Decrypting packet
            if common_header.encrypted:
                try:
                    f_header, f_decrypted = frame_type.decrypt(database, packet_bytes)
                except NoKeyError:
                    continue

                bt_hop = HopReceived(
                    f_header.device_id,
                    common_header.interface,
                    addr,
                    (
                        Auth.DEVICE
                        if f_header.flags & Flags.ENCR_DEVICE
                        else Auth.NETWORK
                    ),
                    f_header.key_metadata,
                    f_header.gps_time,
                    f_header.sequence,
                    common_header.rssi,
                )
                packet = cls(
                    [bt_hop, header.hop_received()],
                    f_header.type,
                    bytes(f_decrypted),
                )
            else:
                # Extract payload metadata
                decr_header = CtypePacketReceived.DecryptedHeader.from_buffer_copy(
                    packet_bytes
                )
                del packet_bytes[: ctypes.sizeof(decr_header)]

                bt_hop = HopReceived(
                    decr_header.device_id,
                    common_header.interface,
                    addr,
                    (
                        Auth.DEVICE
                        if decr_header.flags & Flags.ENCR_DEVICE
                        else Auth.NETWORK
                    ),
                    decr_header.key_id,
                    decr_header.gps_time,
                    decr_header.sequence,
                    common_header.rssi,
                )
                packet = cls(
                    [bt_hop, header.hop_received()],
                    decr_header.type,
                    bytes(packet_bytes),
                )
            packets.append(packet)

        return packets


class PacketOutput(Serializable):
    """ePacket to be transmitted by gateway"""

    def __init__(self, route: List[HopOutput], ptype: InfuseType, payload: bytes):
        # [Serial, hop, hop, final_hop]
        self.route = route
        self.ptype = ptype
        self.payload = payload

    def to_serial(self, database: DeviceDatabase) -> bytes:
        """Encode and encrypt packet for serial transmission"""
        gps_time = InfuseTime.gps_seconds_from_unix(int(time.time()))
        # Multi hop not currently supported
        assert len(self.route) == 1
        route = self.route[0]

        if route.auth == Auth.NETWORK:
            flags = Flags.ENCR_NETWORK
            key_metadata = database.devices[route.infuse_id].network_id
            key = database.serial_network_key(route.infuse_id, gps_time)
        else:
            flags = Flags.ENCR_DEVICE
            key_metadata = database.devices[route.infuse_id].device_id
            key = database.serial_device_key(route.infuse_id, gps_time)

        # Create header
        header = CtypeSerialFrame(
            version=0,
            _type=self.ptype.value,
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

    def to_json(self) -> Dict:
        return {
            "route": [x.to_json() for x in self.route],
            "type": self.ptype.value,
            "payload": base64.b64encode(self.payload).decode("utf-8"),
        }

    @classmethod
    def from_json(cls, values: Dict) -> Self:
        return cls(
            route=[HopOutput.from_json(x) for x in values["route"]],
            ptype=InfuseType(values["type"]),
            payload=base64.b64decode(values["payload"].encode("utf-8")),
        )


class CtypeV0VersionedFrame(ctypes.LittleEndianStructure):
    _fields_ = [
        ("version", ctypes.c_uint8),
        ("_type", ctypes.c_uint8),
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
    def type(self) -> InfuseType:
        return InfuseType(self._type)

    @property
    def key_metadata(self) -> int:
        return int.from_bytes(self._key_metadata, "little")

    @key_metadata.setter
    def key_metadata(self, value):
        self._key_metadata[:] = value.to_bytes(3, "little")

    @property
    def device_id(self) -> int:
        return (self._device_id_upper << 32) | self._device_id_lower

    @device_id.setter
    def device_id(self, value):
        self._device_id_upper = value >> 32
        self._device_id_lower = value & 0xFFFFFFFF

    @classmethod
    def parse(cls, frame: bytes) -> Tuple[Self, int]:
        """Parse serial frame into header and payload length"""
        return (
            CtypeV0VersionedFrame.from_buffer_copy(frame),
            len(frame) - ctypes.sizeof(CtypeV0VersionedFrame) - 16,
        )


class CtypeSerialFrame(CtypeV0VersionedFrame):
    """Serial packet header"""

    def hop_received(self) -> HopReceived:
        auth = Auth.DEVICE if self.flags & Flags.ENCR_DEVICE else Auth.NETWORK
        return HopReceived(
            self.device_id,
            Interface.SERIAL,
            InterfaceAddress(InterfaceAddress.SerialAddr()),
            auth,
            self.key_metadata,
            self.gps_time,
            self.sequence,
            0,
        )

    @classmethod
    def decrypt(cls, database: DeviceDatabase, frame: bytes):
        header = cls.from_buffer_copy(frame)
        if header.flags & Flags.ENCR_DEVICE:
            database.observe_device(header.device_id, device_id=header.key_metadata)
            key = database.serial_device_key(header.device_id, header.gps_time)
        else:
            database.observe_device(header.device_id, network_id=header.key_metadata)
            key = database.serial_network_key(header.device_id, header.gps_time)

        decrypted = chachapoly_decrypt(key, frame[:11], frame[11:23], frame[23:])
        return header, decrypted


class CtypeBtAdvFrame(CtypeV0VersionedFrame):
    """Bluetooth Advertising packet header"""

    @classmethod
    def decrypt(cls, database: DeviceDatabase, frame: bytes):
        header = cls.from_buffer_copy(frame)
        if header.flags & Flags.ENCR_DEVICE:
            raise NotImplementedError
        else:
            database.observe_device(header.device_id, network_id=header.key_metadata)
            key = database.bt_adv_network_key(header.device_id, header.gps_time)

        decrypted = chachapoly_decrypt(key, frame[:11], frame[11:23], frame[23:])
        return header, decrypted


class CtypeBtGattFrame(CtypeV0VersionedFrame):
    """Bluetooth GATT packet header"""

    @classmethod
    def decrypt(cls, database: DeviceDatabase, frame: bytes):
        header = cls.from_buffer_copy(frame)
        if header.flags & Flags.ENCR_DEVICE:
            print(hex(header.device_id))
            database.observe_device(header.device_id, device_id=header.key_metadata)
            key = database.bt_gatt_device_key(header.device_id, header.gps_time)
        else:
            database.observe_device(header.device_id, network_id=header.key_metadata)
            key = database.bt_gatt_network_key(header.device_id, header.gps_time)

        decrypted = chachapoly_decrypt(key, frame[:11], frame[11:23], frame[23:])
        return header, decrypted


class CtypePacketReceived:
    class CommonHeader(ctypes.Structure):
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
            return Interface(self._if)

        @property
        def rssi(self):
            return 0 - self._rssi

    class DecryptedHeader(ctypes.Structure):
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
            return InfuseType(self._type)

        @property
        def key_id(self):
            return int.from_bytes(self._key_id, "little")
