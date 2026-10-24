#!/usr/bin/env python3

"""Patch file instructions"""

import ctypes
import enum

from typing_extensions import Self


class OpCode(enum.IntEnum):
    """Patch file operation code"""

    COPY_LEN_U4 = 0 << 4
    COPY_LEN_U12 = 1 << 4
    COPY_LEN_U20 = 2 << 4
    COPY_LEN_U32 = 3 << 4
    WRITE_LEN_U4 = 4 << 4
    WRITE_LEN_U12 = 5 << 4
    WRITE_LEN_U20 = 6 << 4
    WRITE_LEN_U32 = 7 << 4
    ADDR_SHIFT_S8 = 8 << 4
    ADDR_SHIFT_S16 = 9 << 4
    ADDR_SET_U32 = 10 << 4
    PATCH = 11 << 4
    OPCODE_MASK = 0xF0
    DATA_MASK = 0x0F

    @classmethod
    def from_byte(cls, byte: int):
        return cls(byte & cls.OPCODE_MASK)

    @classmethod
    def data(cls, byte: int):
        return byte & cls.DATA_MASK


class Instr:
    """Parent instruction class"""

    def ctypes_class(self):
        """Instruction ctypes class"""
        raise NotImplementedError

    def __bytes__(self) -> bytes:
        raise NotImplementedError

    def __len__(self):
        return ctypes.sizeof(self.ctypes_class())

    @classmethod
    def from_bytes(
        cls,
        b: bytes,
        offset: int,
        original_offset: int,
    ):
        """Reconstruct class from bytes"""
        opcode = OpCode.from_byte(b[offset])
        if (
            opcode == OpCode.COPY_LEN_U4
            or opcode == OpCode.COPY_LEN_U12
            or opcode == OpCode.COPY_LEN_U20
            or opcode == OpCode.COPY_LEN_U32
        ):
            return CopyInstr.from_bytes(b, offset, original_offset)
        if (
            opcode == OpCode.WRITE_LEN_U4
            or opcode == OpCode.WRITE_LEN_U12
            or opcode == OpCode.WRITE_LEN_U20
            or opcode == OpCode.WRITE_LEN_U32
        ):
            return WriteInstr.from_bytes(b, offset, original_offset)
        if opcode == OpCode.ADDR_SHIFT_S8 or opcode == OpCode.ADDR_SHIFT_S16 or opcode == OpCode.ADDR_SET_U32:
            return SetAddrInstr.from_bytes(b, offset, original_offset)
        if opcode == OpCode.PATCH:
            return PatchInstr.from_bytes(b, offset, original_offset)

        raise NotImplementedError


class SetAddrInstr(Instr):
    class ShiftAddrS8(ctypes.LittleEndianStructure):
        op = OpCode.ADDR_SHIFT_S8
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("val", ctypes.c_int8),
        ]
        _pack_ = 1
        _layout_ = "ms"

    class ShiftAddrS16(ctypes.LittleEndianStructure):
        op = OpCode.ADDR_SHIFT_S16
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("val", ctypes.c_int16),
        ]
        _pack_ = 1
        _layout_ = "ms"

    class SetAddrU32(ctypes.LittleEndianStructure):
        op = OpCode.ADDR_SET_U32
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("val", ctypes.c_uint32),
        ]
        _pack_ = 1
        _layout_ = "ms"

    def __init__(self, old_addr, new_addr, cls_override=None):
        self.old = old_addr
        self.new = new_addr
        self.shift = self.new - self.old
        self._cls_override = cls_override

    def ctypes_class(self):
        if self._cls_override is not None:
            return self._cls_override

        if -128 <= self.shift <= 127:
            return self.ShiftAddrS8
        elif -32768 <= self.shift <= 32767:
            return self.ShiftAddrS16
        else:
            return self.SetAddrU32

    @classmethod
    def from_bytes(cls, b: bytes, offset: int, original_offset: int) -> tuple[Self, int, int]:
        opcode = b[offset]
        if opcode == OpCode.ADDR_SHIFT_S8:
            s8 = cls.ShiftAddrS8.from_buffer_copy(b, offset)
            c = cls(original_offset, original_offset + s8.val)
            struct_len = ctypes.sizeof(s8)
        elif opcode == OpCode.ADDR_SHIFT_S16:
            s16 = cls.ShiftAddrS16.from_buffer_copy(b, offset)
            c = cls(original_offset, original_offset + s16.val)
            struct_len = ctypes.sizeof(s16)
        elif opcode == OpCode.ADDR_SET_U32:
            s32 = cls.SetAddrU32.from_buffer_copy(b, offset)
            c = cls(original_offset, s32.val)
            struct_len = ctypes.sizeof(s32)
        else:
            raise RuntimeError
        return c, struct_len, c.new

    def __bytes__(self):
        instr = self.ctypes_class()
        if instr == self.ShiftAddrS8 or instr == self.ShiftAddrS16:
            val = self.shift
        else:
            val = self.new

        return bytes(instr(instr.op.value, val))

    def __str__(self):
        if -32768 <= self.shift <= 32767:
            return f" ADDR: shifting {self.shift} (from {self.old:08x} to {self.new:08x})"
        else:
            return f" ADDR: now {self.new:08x} (shift of {self.new - self.old})"


class CopyInstr(Instr):
    class CopyGeneric(ctypes.LittleEndianStructure):
        pass

    class CopyU4(CopyGeneric):
        op = OpCode.COPY_LEN_U4
        _fields_ = [
            ("opcode", ctypes.c_uint8),
        ]
        _pack_ = 1
        _layout_ = "ms"

        @property
        def length(self):
            return OpCode.data(self.opcode)

    class CopyU12(CopyGeneric):
        op = OpCode.COPY_LEN_U12
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("_length", ctypes.c_uint8),
        ]
        _pack_ = 1
        _layout_ = "ms"

        @property
        def length(self):
            return (OpCode.data(self.opcode) << 8) | self._length

    class CopyU20(CopyGeneric):
        op = OpCode.COPY_LEN_U20
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("_length", ctypes.c_uint16),
        ]
        _pack_ = 1
        _layout_ = "ms"

        @property
        def length(self):
            return (OpCode.data(self.opcode) << 16) | self._length

    class CopyU32(CopyGeneric):
        op = OpCode.COPY_LEN_U32
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("length", ctypes.c_uint32),
        ]
        _pack_ = 1
        _layout_ = "ms"

    def __init__(self, length: int, original_offset: int = -1, cls_override=None):
        assert length != 0
        self.length = length
        # Used in construction to simplify optimisations
        self.original_offset = original_offset
        self._cls_override = cls_override

    def ctypes_class(self):
        if self._cls_override is not None:
            return self._cls_override
        if self.length < 16:
            return self.CopyU4
        elif self.length < 4096:
            return self.CopyU12
        elif self.length < 1048576:
            return self.CopyU20
        else:
            return self.CopyU32

    @classmethod
    def _from_opcode(cls, op: OpCode) -> type[CopyGeneric]:
        if op == OpCode.COPY_LEN_U4:
            return cls.CopyU4
        elif op == OpCode.COPY_LEN_U12:
            return cls.CopyU12
        elif op == OpCode.COPY_LEN_U20:
            return cls.CopyU20
        elif op == OpCode.COPY_LEN_U32:
            return cls.CopyU32
        else:
            raise RuntimeError

    @classmethod
    def from_bytes(cls, b: bytes, offset: int, original_offset: int) -> tuple[Self, int, int]:
        opcode = OpCode.from_byte(b[offset])
        op_class = cls._from_opcode(opcode)
        s = op_class.from_buffer_copy(b, offset)
        return cls(s.length), ctypes.sizeof(s), original_offset + s.length

    def __bytes__(self):
        instr = self.ctypes_class()
        if instr == self.CopyU4:
            return bytes(instr(instr.op.value | self.length))
        elif instr == self.CopyU12:
            top = self.length >> 8
            bottom = self.length & 0xFF
            return bytes(instr(instr.op.value | top, bottom))
        elif instr == self.CopyU20:
            top = self.length >> 16
            bottom = self.length & 0xFFFF
            return bytes(instr(instr.op.value | top, bottom))
        else:
            return bytes(instr(instr.op.value, self.length))

    def __str__(self):
        return f" COPY: {self.length:6d} bytes"


class WriteInstr(Instr):
    class WriteGeneric(ctypes.LittleEndianStructure):
        pass

    class WriteU4(WriteGeneric):
        op = OpCode.WRITE_LEN_U4
        _fields_ = [
            ("opcode", ctypes.c_uint8),
        ]
        _pack_ = 1
        _layout_ = "ms"

        @property
        def length(self):
            return OpCode.data(self.opcode)

    class WriteU12(WriteGeneric):
        op = OpCode.WRITE_LEN_U12
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("_length", ctypes.c_uint8),
        ]
        _pack_ = 1
        _layout_ = "ms"

        @property
        def length(self):
            return (OpCode.data(self.opcode) << 8) | self._length

    class WriteU20(WriteGeneric):
        op = OpCode.WRITE_LEN_U20
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("_length", ctypes.c_uint16),
        ]
        _pack_ = 1
        _layout_ = "ms"

        @property
        def length(self):
            return (OpCode.data(self.opcode) << 16) | self._length

    class WriteU32(WriteGeneric):
        op = OpCode.WRITE_LEN_U32
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("length", ctypes.c_uint32),
        ]
        _pack_ = 1
        _layout_ = "ms"

    def __init__(self, data, cls_override=None):
        assert len(data) != 0
        self.data = data
        self._cls_override = cls_override

    def ctypes_class(self):
        if self._cls_override is not None:
            return self._cls_override
        if len(self.data) < 16:
            return self.WriteU4
        elif len(self.data) < 4096:
            return self.WriteU12
        elif len(self.data) < 1048576:
            return self.WriteU20
        else:
            return self.WriteU32

    @classmethod
    def _from_opcode(cls, op: OpCode) -> type[WriteGeneric]:
        if op == OpCode.WRITE_LEN_U4:
            return cls.WriteU4
        elif op == OpCode.WRITE_LEN_U12:
            return cls.WriteU12
        elif op == OpCode.WRITE_LEN_U20:
            return cls.WriteU20
        elif op == OpCode.WRITE_LEN_U32:
            return cls.WriteU32
        else:
            raise RuntimeError

    @classmethod
    def from_bytes(cls, b: bytes, offset: int, original_offset: int) -> tuple[Self, int, int]:
        opcode = OpCode.from_byte(b[offset])
        op_class = cls._from_opcode(opcode)
        s = op_class.from_buffer_copy(b, offset)
        hdr_len = ctypes.sizeof(s)

        return (
            cls(b[offset + hdr_len : offset + hdr_len + s.length]),
            hdr_len + s.length,
            original_offset + s.length,
        )

    def __bytes__(self):
        instr = self.ctypes_class()
        if instr == self.WriteU4:
            return bytes(instr(instr.op.value | len(self.data))) + self.data
        elif instr == self.WriteU12:
            top = len(self.data) >> 8
            bottom = len(self.data) & 0xFF
            return bytes(instr(instr.op.value | top, bottom)) + self.data
        elif instr == self.WriteU20:
            top = len(self.data) >> 16
            bottom = len(self.data) & 0xFFFF
            return bytes(instr(instr.op.value | top, bottom)) + self.data
        else:
            return bytes(instr(instr.op.value, len(self.data))) + self.data

    def __str__(self):
        if len(self.data) < 64:
            return f"WRITE: {len(self.data):6d} bytes ({self.data.hex()})"
        else:
            return f"WRITE: {len(self.data):6d} bytes ({self.data[:64].hex()}...)"

    def __len__(self):
        return ctypes.sizeof(self.ctypes_class()) + len(self.data)


class PatchInstr(Instr):
    class PatchData(ctypes.LittleEndianStructure):
        op = OpCode.PATCH
        _fields_ = [("opcode", ctypes.c_uint8)]
        _pack_ = 1
        _layout_ = "ms"

    def __init__(self, operations):
        self.operations = operations

    def ctypes_class(self):
        return self.PatchData

    @classmethod
    def from_bytes(cls, b: bytes, offset: int, original_offset: int):
        assert b[offset] == OpCode.PATCH
        operations: list[Instr] = []
        length = 1

        while True:
            copy_len = b[offset + length]
            length += 1
            if copy_len == 0:
                break
            assert copy_len != 0
            actual_copy_len = copy_len & 0x7F
            original_offset += actual_copy_len
            operations.append(CopyInstr(int(actual_copy_len)))

            if copy_len & 0x80:
                write_len = 1
            else:
                write_len = b[offset + length]
                length += 1
            if write_len == 0:
                break
            assert write_len != 0
            original_offset += write_len
            operations.append(WriteInstr(b[offset + length : offset + length + write_len]))
            length += write_len

        return cls(operations), length, original_offset

    def __bytes__(self):
        x = OpCode.PATCH.value.to_bytes(1, "little")
        op_iterator = (o for o in self.operations)

        while True:
            copy_op = next(op_iterator, None)
            write_op = next(op_iterator, None)

            if copy_op is None:
                break
            assert isinstance(copy_op, CopyInstr)
            assert copy_op.length < 128
            assert copy_op.length != 0

            if write_op is not None and len(write_op.data) == 1:
                val = 0x80 | copy_op.length
            else:
                val = copy_op.length
            x += val.to_bytes(1, "little")

            if write_op is None:
                break
            assert isinstance(write_op, WriteInstr)
            assert len(write_op.data) < 256
            assert len(write_op.data) != 0
            if len(write_op.data) > 1:
                x += len(write_op.data).to_bytes(1, "little")
            x += write_op.data
        x += b"\x00"
        return x

    def __str__(self):
        return "PATCH:\n" + "\n".join([f"\t{str(o)}" for o in self.operations])

    def __len__(self):
        length = 2
        for op in self.operations:
            if isinstance(op, CopyInstr):
                length += 1
            elif isinstance(op, WriteInstr):
                if len(op.data) > 1:
                    length += 1
                length += len(op.data)
        return length
