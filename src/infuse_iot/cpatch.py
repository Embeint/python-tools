#!/usr/bin/env python3

import argparse
import binascii
import ctypes
import enum
from collections import defaultdict

from typing_extensions import Self


class ValidationError(Exception):
    """Generic patch validation exception"""


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

    class ShiftAddrS16(ctypes.LittleEndianStructure):
        op = OpCode.ADDR_SHIFT_S16
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("val", ctypes.c_int16),
        ]
        _pack_ = 1

    class SetAddrU32(ctypes.LittleEndianStructure):
        op = OpCode.ADDR_SET_U32
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("val", ctypes.c_uint32),
        ]
        _pack_ = 1

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


class cpatch:
    class PatchHeader(ctypes.LittleEndianStructure):
        VERSION_MAJOR = 1
        VERSION_MINOR = 0

        class ArrayValidation(ctypes.LittleEndianStructure):
            _fields_ = [
                ("length", ctypes.c_uint32),
                ("crc", ctypes.c_uint32),
            ]
            _pack_ = 1

        magic_value = 0xBA854092
        cache_size = 128
        _fields_ = [
            ("magic", ctypes.c_uint32),
            ("version_major", ctypes.c_uint8),
            ("version_minor", ctypes.c_uint8),
            ("original_file", ArrayValidation),
            ("constructed_file", ArrayValidation),
            ("patch_file", ArrayValidation),
            ("header_crc", ctypes.c_uint32),
        ]
        _pack_ = 1

    @classmethod
    def _naive_diff(cls, old: bytes, new: bytes, hash_len: int = 8):
        """Construct basic runs of WRITE, COPY, and SET_ADDR instructions"""
        instr: list[Instr] = []
        old_offset = 0
        new_offset = 0
        write_start = 0
        write_pending = 0

        # Pre-hash original image
        pre_hash = {}
        prev_val = None
        for offset in range(len(old) - hash_len):
            val = old[offset : offset + hash_len]
            if val == prev_val:
                continue
            if val not in pre_hash:
                pre_hash[val] = [offset]
            else:
                pre_hash[val].append(offset)
            prev_val = val

        # Loop until entire image is reconstructed
        while new_offset < len(new):
            val = new[new_offset : new_offset + hash_len]

            # If word exists in original image
            if val in pre_hash:
                if write_pending:
                    instr.append(WriteInstr(new[write_start : write_start + write_pending]))
                    write_pending = 0

                old_match = -100

                # Check to see if we have a match at current pointer
                if old_offset in pre_hash[val]:
                    old_match = 0
                    while (
                        (new_offset + old_match) < len(new)
                        and (old_offset + old_match) < len(old)
                        and new[new_offset + old_match] == old[old_offset + old_match]
                    ):
                        old_match += 1

                max_match = old_match
                max_offset = old_offset

                # For each location in original image
                for orig_offset in pre_hash[val]:
                    this_match = 0
                    while (
                        (new_offset + this_match) < len(new)
                        and (orig_offset + this_match) < len(old)
                        and new[new_offset + this_match] == old[orig_offset + this_match]
                    ):
                        this_match += 1

                    if this_match > max_match and this_match > (old_match + 8):
                        max_match = this_match
                        max_offset = orig_offset

                if max_offset != old_offset:
                    # Update memory address
                    instr.append(SetAddrInstr(old_offset, max_offset))

                instr.append(CopyInstr(max_match, max_offset))
                new_offset += max_match
                old_offset = max_offset + max_match
            else:
                if write_pending == 0:
                    write_start = new_offset
                write_pending += 1
                new_offset += 1
                old_offset += 1

        if write_pending:
            instr.append(WriteInstr(new[write_start : write_start + write_pending]))
            write_pending = 0

        return instr

    @classmethod
    def _cleanup_jumps(cls, old: bytes, instructions: list[Instr]) -> list[Instr]:
        """Find locations that jumped backwards just to jump forward to original location"""

        merged: list[Instr] = []
        while len(instructions) > 0:
            instr = instructions.pop(0)
            replaced = False

            if isinstance(instr, SetAddrInstr):
                copy = instructions[0]
                assert isinstance(copy, CopyInstr)

                if len(instructions) >= 2 and isinstance(instructions[1], SetAddrInstr):
                    # ADDR, COPY, ADRR
                    if instr.shift == -instructions[1].shift:
                        print(copy.length)
                        # Replace with a write instead
                        merged.append(WriteInstr(old[instr.new : instr.new + copy.length]))
                        replaced = True
                        instructions.pop(0)
                        instructions.pop(0)
                elif (
                    len(instructions) >= 3
                    and isinstance(instructions[1], WriteInstr)
                    and isinstance(instructions[2], SetAddrInstr)
                    # ADDR, COPY, WRITE, ADRR
                    and instr.shift == -instructions[2].shift
                ):
                    write = instructions[1]
                    # Replace with a merged write instead
                    merged.append(WriteInstr(old[instr.new : instr.new + copy.length] + write.data))
                    replaced = True
                    instructions.pop(0)
                    instructions.pop(0)
                    instructions.pop(0)

            if not replaced:
                merged.append(instr)

        # We may have sequential WRITE commands due to the merging, do a pass
        cleaned = [merged[0]]
        for instr in merged[1:]:
            if isinstance(instr, WriteInstr) and isinstance(cleaned[-1], WriteInstr):
                cleaned[-1].data += instr.data
            else:
                cleaned.append(instr)
        return cleaned

    @classmethod
    def _merge_operations(cls, instructions: list[Instr]) -> list[Instr]:
        """Merge runs of COPY and WRITE into PATCH"""
        merged: list[Instr] = []
        to_merge: list[Instr] = []

        def finalise():
            nonlocal merged
            nonlocal to_merge
            if len(to_merge) == 0:
                return
            elif len(to_merge) == 1:
                merged.append(to_merge[0])
            else:
                merged.append(PatchInstr(to_merge))
            to_merge = []

        for instr in instructions:
            if (isinstance(instr, CopyInstr) and instr.length < 128) or (
                isinstance(instr, WriteInstr) and len(to_merge) > 0 and len(instr.data) < 256
            ):
                to_merge.append(instr)
            else:
                finalise()
                merged.append(instr)

        if len(to_merge) > 0:
            finalise()
        return merged

    @classmethod
    def _write_crack(cls, old: bytes, instructions: list[Instr]) -> list[Instr]:
        """Crack a WRITE operation into a [WRITE,COPY,WRITE] if COPY is at least 2 bytes"""

        cracked: list[Instr] = []
        old_offset = 0

        while len(instructions):
            instr = instructions.pop(0)

            if isinstance(instr, CopyInstr):
                old_offset = instr.original_offset + instr.length
                cracked.append(instr)
                continue
            elif isinstance(instr, SetAddrInstr):
                old_offset = instr.new
                cracked.append(instr)
                continue
            assert isinstance(instr, WriteInstr)

            split = [0]
            for idx, b in enumerate(instr.data):
                if old_offset + idx >= len(old):
                    # Add remainder of write to last split
                    split[-1] += len(instr.data) - idx
                    break
                if old[old_offset + idx] != b:
                    if len(split) % 2:
                        # Already on a WRITE
                        split[-1] += 1
                    else:
                        # On a COPY, swap to a WRITE
                        split.append(1)
                    continue

                if len(split) % 2:
                    # On a WRITE, switch to a COPY
                    split.append(1)
                else:
                    # Already on a COPY
                    split[-1] += 1

            # Total data count should remain the same
            assert sum(split) == len(instr.data)

            if len(split) % 2 == 0:
                # Ended on a copy
                copy_len = split.pop()
                if len(instructions) > 0 and isinstance(instructions[0], CopyInstr):
                    # Push the match into the next instruction if possible
                    instructions[0].length += copy_len
                    instructions[0].original_offset -= copy_len
                else:
                    # Merge the copy back into the previous write
                    split[-1] += copy_len

            # Should now have N*[WRITE, COPY] + [WRITE]
            assert len(split) % 2 == 1

            # Construct the [WRITE, COPY] pairs
            offset = 0
            while len(split) > 1:
                write_len = split.pop(0)
                copy_len = split.pop(0)

                # If the copy was only 1 byte, roll it back
                if copy_len == 1:
                    split[0] += write_len + copy_len
                else:
                    cracked.append(WriteInstr(instr.data[offset : offset + write_len]))
                    offset += write_len
                    cracked.append(CopyInstr(copy_len, old_offset + offset))
                    offset += copy_len

            # Append the final WRITE
            write_len = split.pop()
            cracked.append(WriteInstr(instr.data[offset : offset + write_len]))

        return cracked

    @classmethod
    def _gen_patch_instr(cls, bin_orig: bytes, bin_new: bytes) -> tuple[dict, list[Instr]]:
        best_patch = []
        best_patch_len = 2**32

        # Find best diff across range
        for i in range(4, 8):
            instr = cls._naive_diff(bin_orig, bin_new, i)
            instr = cls._cleanup_jumps(bin_orig, instr)
            instr = cls._write_crack(bin_orig, instr)
            instr = cls._merge_operations(instr)
            patch_len = sum([len(i) for i in instr])

            if patch_len < best_patch_len:
                best_patch = instr
                best_patch_len = patch_len

        metadata = {
            "original": {
                "len": len(bin_orig),
                "crc": binascii.crc32(bin_orig),
            },
            "new": {
                "len": len(bin_new),
                "crc": binascii.crc32(bin_new),
            },
        }

        return metadata, best_patch

    @classmethod
    def _gen_patch_header(cls, patch_metadata: dict, patch_data: bytes):
        hdr = cls.PatchHeader(
            cls.PatchHeader.magic_value,
            cls.PatchHeader.VERSION_MAJOR,
            cls.PatchHeader.VERSION_MINOR,
            cls.PatchHeader.ArrayValidation(
                patch_metadata["original"]["len"],
                patch_metadata["original"]["crc"],
            ),
            cls.PatchHeader.ArrayValidation(
                patch_metadata["new"]["len"],
                patch_metadata["new"]["crc"],
            ),
            cls.PatchHeader.ArrayValidation(
                len(patch_data),
                binascii.crc32(patch_data),
            ),
            0,
        )
        hdr_no_crc = bytes(hdr)
        hdr.header_crc = binascii.crc32(hdr_no_crc[: -ctypes.sizeof(ctypes.c_uint32)])
        return bytes(hdr)

    @classmethod
    def _gen_patch_data(cls, instructions: list[Instr]):
        output_bytes = b""
        for instr in instructions:
            output_bytes += bytes(instr)
        return output_bytes

    @classmethod
    def _patch_load(cls, patch_binary: bytes):
        hdr = cls.PatchHeader.from_buffer_copy(patch_binary)
        data = patch_binary[ctypes.sizeof(cls.PatchHeader) :]

        metadata = {
            "original": {
                "len": hdr.original_file.length,
                "crc": hdr.original_file.crc,
            },
            "new": {
                "len": hdr.constructed_file.length,
                "crc": hdr.constructed_file.crc,
            },
            "patch": {
                "len": hdr.patch_file.length,
                "crc": hdr.patch_file.crc,
            },
        }

        header_crc = binascii.crc32(patch_binary[: ctypes.sizeof(hdr) - ctypes.sizeof(ctypes.c_uint32)])
        if header_crc != hdr.header_crc:
            raise ValidationError("Patch header validation failed")
        if len(data) != hdr.patch_file.length:
            raise ValidationError(
                f"Patch data length does not match header information ({len(data)} != {hdr.patch_file.length})"
            )
        crc_patch = binascii.crc32(data)
        crc_expected = hdr.patch_file.crc
        if crc_patch != hdr.patch_file.crc:
            raise ValidationError(
                f"Patch data CRC does not match patch information ({crc_patch:08x} != {crc_expected:08x})"
            )

        instructions = []
        patch_offset = 0
        original_offset = 0
        while patch_offset < len(data):
            instr, length, original_offset = Instr.from_bytes(data, patch_offset, original_offset)
            patch_offset += length
            instructions.append(instr)

        return metadata, instructions

    @classmethod
    def generate(
        cls,
        bin_original: bytes,
        bin_new: bytes,
        verbose: bool,
    ) -> bytes:
        meta, instructions = cls._gen_patch_instr(bin_original, bin_new)
        patch_data = cls._gen_patch_data(instructions)
        patch_header = cls._gen_patch_header(meta, patch_data)
        bin_patch = patch_header + patch_data
        ratio = 100 * len(bin_patch) / meta["new"]["len"]

        print(f"Original File: {meta['original']['len']:6d} bytes")
        print(f"     New File: {meta['new']['len']:6d} bytes")
        print(f"   Patch File: {len(bin_patch):6d} bytes ({ratio:.2f}%) ({len(instructions):5d} instructions)")

        if verbose:
            class_count: dict[OpCode, int] = defaultdict(int)
            for instr in instructions:
                class_count[instr.ctypes_class().op] += 1

            print("")
            print("Instructions:")
            for instr_cls, instr_count in sorted(class_count.items()):
                print(f"{instr_cls.name:>16s}: {instr_count}")

        # Validate that file can be reconstructed
        patched = cls.patch(bin_original, bin_patch)
        assert bin_new == patched

        # Return complete file
        return bin_patch

    @classmethod
    def validation(cls, bin_original: bytes, invalid_length: bool, invalid_crc: bool) -> bytes:
        assert len(bin_original) > 1024

        # Manually construct an instruction set that runs all instructions
        instructions: list[Instr] = []
        instructions.append(WriteInstr(bin_original[:8], cls_override=WriteInstr.WriteU4))
        instructions.append(WriteInstr(bin_original[8:16], cls_override=WriteInstr.WriteU12))
        instructions.append(SetAddrInstr(16, 8, cls_override=SetAddrInstr.ShiftAddrS8))
        instructions.append(WriteInstr(bin_original[16:128], cls_override=WriteInstr.WriteU20))
        instructions.append(SetAddrInstr(120, 200, cls_override=SetAddrInstr.ShiftAddrS16))
        instructions.append(WriteInstr(bin_original[128:256], cls_override=WriteInstr.WriteU32))
        instructions.append(SetAddrInstr(328, 256, cls_override=SetAddrInstr.SetAddrU32))
        instructions.append(CopyInstr(8, cls_override=CopyInstr.CopyU4))
        instructions.append(CopyInstr(8, cls_override=CopyInstr.CopyU12))
        instructions.append(CopyInstr(128 - 16, cls_override=CopyInstr.CopyU20))
        instructions.append(CopyInstr(128, cls_override=CopyInstr.CopyU32))
        instructions.append(
            PatchInstr(
                [
                    CopyInstr(15),
                    WriteInstr(bin_original[512 + 15 : 512 + 16]),
                    CopyInstr(14),
                    WriteInstr(bin_original[512 + 30 : 512 + 32]),
                ]
            )
        )
        instructions.append(CopyInstr(len(bin_original) - 544))

        meta, _ = cls._gen_patch_instr(bin_original, bin_original)
        if invalid_length:
            meta["new"]["len"] -= 1
        if invalid_crc:
            meta["new"]["crc"] -= 1

        patch_data = cls._gen_patch_data(instructions)
        patch_header = cls._gen_patch_header(meta, patch_data)
        bin_patch = patch_header + patch_data

        # Validate that file can be reconstructed
        if not invalid_length and not invalid_crc:
            patched = cls.patch(bin_original, bin_patch)
            assert bin_original == patched

        return bin_patch

    @classmethod
    def patch(
        cls,
        bin_original: bytes,
        bin_patch: bytes,
    ) -> bytes:
        meta, instructions = cls._patch_load(bin_patch)
        patched = b""
        orig_offset = 0

        len_orig = len(bin_original)
        len_expected = meta["original"]["len"]
        if len_orig != len_expected:
            raise ValidationError(
                f"Original file length does not match patch information ({len_orig} != {len_expected})"
            )
        crc_orig = binascii.crc32(bin_original)
        crc_expected = meta["original"]["crc"]
        if crc_orig != crc_expected:
            raise ValidationError(
                f"Original file CRC does not match patch information ({crc_orig:08x} != {crc_expected:08x})"
            )

        for instr in instructions:
            if isinstance(instr, CopyInstr):
                patched += bin_original[orig_offset : orig_offset + instr.length]
                orig_offset += instr.length
            elif isinstance(instr, WriteInstr):
                patched += instr.data
                orig_offset += len(instr.data)
            elif isinstance(instr, SetAddrInstr):
                orig_offset = instr.new
            elif isinstance(instr, PatchInstr):
                for op in instr.operations:
                    if isinstance(op, CopyInstr):
                        patched += bin_original[orig_offset : orig_offset + op.length]
                        orig_offset += op.length
                    elif isinstance(op, WriteInstr):
                        patched += op.data
                        orig_offset += len(op.data)
                    else:
                        assert 0
            else:
                assert 0

        # Validate generated file matches what was expected
        len_patched = len(patched)
        len_expected = meta["new"]["len"]
        if len_patched != len_expected:
            raise ValidationError(
                f"Original file length does not match patch information ({len_patched} != {len_expected})"
            )
        crc_patched = binascii.crc32(patched)
        crc_expected = meta["new"]["crc"]
        if crc_patched != crc_expected:
            raise ValidationError(
                f"Original file CRC does not match patch information ({crc_patched:08x} != {crc_expected:08x})"
            )

        return patched

    @classmethod
    def dump(
        cls,
        bin_patch: bytes,
    ):
        meta, instructions = cls._patch_load(bin_patch)
        total_write_bytes = 0

        print(f"Original File: {meta['original']['len']:6d} bytes")
        print(f"     New File: {meta['new']['len']:6d} bytes")
        print(f"   Patch File: {len(bin_patch)} bytes ({len(instructions):5d} instructions)")

        class_count: dict[OpCode, int] = defaultdict(int)
        for instr in instructions:
            class_count[instr.ctypes_class().op] += 1
            if isinstance(instr, WriteInstr):
                total_write_bytes += len(instr.data)
            elif isinstance(instr, PatchInstr):
                for op in instr.operations:
                    if isinstance(op, WriteInstr):
                        total_write_bytes += len(op.data)

        print("")
        print("Total WRITE data:")
        print(f"\t{total_write_bytes} bytes ({100 * total_write_bytes / len(bin_patch):.2f}%)")

        print("")
        print("Instruction Count:")
        for op_cls, count in sorted(class_count.items()):
            print(f"{op_cls.name:>16s}: {count}")

        print("")
        print("Instruction List:")
        for instr in instructions:
            print(instr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose command output")
    subparser = parser.add_subparsers(dest="command", title="Commands", required=True)

    # Generate patch file
    generate_args = subparser.add_parser("generate", help="Generate a patch file")
    generate_args.add_argument("original", help="Original file to use as base image")
    generate_args.add_argument("new", help="New file that will be the result of applying the patch")
    generate_args.add_argument("patch", help="Output patch file name")

    # Generate validation patch file
    validation_args = subparser.add_parser("validation", help="Generate a patch file for validating appliers")
    validation_args.add_argument("--invalid-length", action="store_true", help="Incorrect output file length")
    validation_args.add_argument("--invalid-crc", action="store_true", help="Incorrect output file CRC")
    validation_args.add_argument("input_file", help="File to use as base image and desired output")
    validation_args.add_argument("patch", help="Output patch file name")

    # Apply patch file
    patch_args = subparser.add_parser("patch", help="Apply a patch file")
    patch_args.add_argument("original", help="Original file to use as base image")
    patch_args.add_argument("patch", help="Patch file to apply")
    patch_args.add_argument("output", help="File to write output to")

    # Dump patch instructions
    dump_args = subparser.add_parser("dump", help="Dump patch file instructions to terminal")
    dump_args.add_argument("patch", help="Patch file to dump")

    # Parse args
    args = parser.parse_args()

    # Run requested command
    if args.command == "generate":
        with open(args.original, "rb") as f_orig, open(args.new, "rb") as f_new:
            patch = cpatch.generate(
                f_orig.read(-1),
                f_new.read(-1),
                args.verbose,
            )
        with open(args.patch, "wb") as f_output:
            f_output.write(patch)
    elif args.command == "validation":
        with open(args.input_file, "rb") as f_input:
            patch = cpatch.validation(f_input.read(-1), args.invalid_length, args.invalid_crc)
        with open(args.patch, "wb") as f_output:
            f_output.write(patch)
    elif args.command == "patch":
        with open(args.original, "rb") as f_orig, open(args.patch, "rb") as f_patch:
            output = cpatch.patch(f_orig.read(-1), f_patch.read(-1))
        with open(args.output, "wb") as f_output:
            f_output.write(output)
    elif args.command == "dump":
        with open(args.patch, "rb") as f_patch:
            cpatch.dump(f_patch.read(-1))
