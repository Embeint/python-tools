#!/usr/bin/env python3

import ctypes
import enum

from typing_extensions import Self

import infuse_iot.definitions.rpc as rpc_defs
import infuse_iot.definitions.tdf as tdf_defs
from infuse_iot.epacket.common import Serializable
from infuse_iot.util.ctypes import bytes_to_uint8


class ID(enum.Enum):
    """Interface identifier"""

    SERIAL = 0
    UDP = 1
    BT_ADV = 2
    BT_PERIPHERAL = 3
    BT_CENTRAL = 4


class Address(Serializable):
    class SerialAddr(Serializable):
        def __str__(self):
            return ""

        def len(self):
            return 0

        def to_json(self) -> dict:
            return {"i": "SERIAL"}

        @classmethod
        def from_json(cls, values: dict) -> Self:
            return cls()

    class BluetoothLeAddr(Serializable):
        class CtypesFormat(ctypes.LittleEndianStructure):
            _fields_ = [
                ("type", ctypes.c_uint8),
                ("addr", 6 * ctypes.c_uint8),
            ]
            _pack_ = 1

        def __init__(self, addr_type: int, addr_val: int):
            self.addr_type = addr_type
            self.addr_val = addr_val

        def __hash__(self) -> int:
            return (self.addr_type << 48) + self.addr_val

        def __eq__(self, another) -> bool:
            return self.addr_type == another.addr_type and self.addr_val == another.addr_val

        def __str__(self) -> str:
            t = "random" if self.addr_type == 1 else "public"
            v = ":".join([f"{x:02x}" for x in self.addr_val.to_bytes(6, "big")])
            return f"{v} ({t})"

        def len(self):
            return ctypes.sizeof(self.CtypesFormat)

        def to_ctype(self) -> CtypesFormat:
            """Convert the address to the ctype format"""
            return self.CtypesFormat(self.addr_type, bytes_to_uint8(self.addr_val.to_bytes(6, "little")))

        def to_json(self) -> dict:
            return {"i": "BT", "t": self.addr_type, "v": self.addr_val}

        @classmethod
        def from_json(cls, values: dict) -> Self:
            return cls(values["t"], values["v"])

        def to_rpc_struct(self) -> rpc_defs.rpc_struct_bt_addr_le:
            """Convert the address to the common RPC address structure"""

            return rpc_defs.rpc_struct_bt_addr_le(self.addr_type, bytes_to_uint8(self.addr_val.to_bytes(6, "little")))

        @classmethod
        def from_rpc_struct(cls, struct: rpc_defs.rpc_struct_bt_addr_le):
            """Create instance from the common RPC address structure"""

            return cls(struct.type, int.from_bytes(struct.val, "little"))

        @classmethod
        def from_tdf_struct(cls, struct: tdf_defs.structs.tdf_struct_bt_addr_le):
            """Create instance from the common TDF address structure"""

            return cls(struct.type, struct.val)

    def __init__(self, val):
        self.val = val

    def __str__(self):
        return str(self.val)

    def len(self):
        return self.val.len()

    def to_json(self) -> dict:
        return self.val.to_json()

    @classmethod
    def from_json(cls, values: dict) -> Self:
        if values["i"] == "BT":
            return cls(cls.BluetoothLeAddr.from_json(values))
        elif values["i"] == "SERIAL":
            return cls(cls.SerialAddr())
        raise NotImplementedError("Unknown address type")

    @classmethod
    def from_bytes(cls, interface: ID, stream: bytes) -> Self:
        assert interface in [
            ID.BT_ADV,
            ID.BT_PERIPHERAL,
            ID.BT_CENTRAL,
        ]

        c = cls.BluetoothLeAddr.CtypesFormat.from_buffer_copy(stream)
        return cls(cls.BluetoothLeAddr(c.type, int.from_bytes(bytes(c.addr), "little")))
