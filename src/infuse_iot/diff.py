#!/usr/bin/env python3

import argparse
import enum
import ctypes
import binascii

from collections import defaultdict, OrderedDict
from typing import List, Dict, Tuple

from functools import cmp_to_key


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
    WRITE_CACHED = 8 << 4
    ADDR_SHIFT_S8 = 9 << 4
    ADDR_SHIFT_S16 = 10 << 4
    ADDR_SET_U32 = 11 << 4
    PATCH = 12 << 4
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
        write_cache: List[bytes],
    ):
        """Reconstruct class from bytes"""
        opcode = OpCode.from_byte(b[offset])
        if (
            opcode == OpCode.COPY_LEN_U4
            or opcode == OpCode.COPY_LEN_U12
            or opcode == OpCode.COPY_LEN_U20
            or opcode == OpCode.COPY_LEN_U32
        ):
            return CopyInstr.from_bytes(b, offset, original_offset, write_cache)
        if (
            opcode == OpCode.WRITE_LEN_U4
            or opcode == OpCode.WRITE_LEN_U12
            or opcode == OpCode.WRITE_LEN_U20
            or opcode == OpCode.WRITE_LEN_U32
        ):
            return WriteInstr.from_bytes(b, offset, original_offset, write_cache)
        if opcode == OpCode.WRITE_CACHED:
            return WriteCachedInstr.from_bytes(b, offset, original_offset, write_cache)
        if (
            opcode == OpCode.ADDR_SHIFT_S8
            or opcode == OpCode.ADDR_SHIFT_S16
            or opcode == OpCode.ADDR_SET_U32
        ):
            return SetAddrInstr.from_bytes(b, offset, original_offset, write_cache)
        if opcode == OpCode.PATCH:
            return PatchInstr.from_bytes(b, offset, original_offset, write_cache)

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

    def __init__(self, old_addr, new_addr):
        self.old = old_addr
        self.new = new_addr
        self.shift = self.new - self.old

    def ctypes_class(self):
        if -128 <= self.shift <= 127:
            return self.ShiftAddrS8
        elif -32768 <= self.shift <= 32767:
            return self.ShiftAddrS16
        else:
            return self.SetAddrU32

    @classmethod
    def from_bytes(
        cls, b: bytes, offset: int, original_offset: int, _write_cache: List[bytes]
    ):
        opcode = b[offset]
        if opcode == OpCode.ADDR_SHIFT_S8:
            s = cls.ShiftAddrS8.from_buffer_copy(b, offset)
            c = cls(original_offset, original_offset + s.val)
        elif opcode == OpCode.ADDR_SHIFT_S16:
            s = cls.ShiftAddrS16.from_buffer_copy(b, offset)
            c = cls(original_offset, original_offset + s.val)
        elif opcode == OpCode.ADDR_SET_U32:
            s = cls.SetAddrU32.from_buffer_copy(b, offset)
            c = cls(original_offset, s.val)
        else:
            raise RuntimeError
        return c, ctypes.sizeof(s), c.new

    def __bytes__(self):
        if -128 <= self.shift <= 127:
            instr_cls = self.ShiftAddrS8
            val = self.shift
        elif -32768 <= self.shift <= 32767:
            instr_cls = self.ShiftAddrS16
            val = self.shift
        else:
            instr_cls = self.SetAddrU32
            val = self.new

        return bytes(instr_cls(instr_cls.op.value, val))

    def __str__(self):
        if -32768 <= self.shift <= 32767:
            return (
                f" ADDR: shifting {self.shift} (from {self.old:08x} to {self.new:08x})"
            )
        else:
            return f" ADDR: now {self.new:08x} (shift of {self.new - self.old})"


class CopyInstr(Instr):
    class CopyU4(ctypes.LittleEndianStructure):
        op = OpCode.COPY_LEN_U4
        _fields_ = [
            ("opcode", ctypes.c_uint8),
        ]
        _pack_ = 1

        @property
        def length(self):
            return OpCode.data(self.opcode)

    class CopyU12(ctypes.LittleEndianStructure):
        op = OpCode.COPY_LEN_U12
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("_length", ctypes.c_uint8),
        ]
        _pack_ = 1

        @property
        def length(self):
            return (OpCode.data(self.opcode) << 8) | self._length

    class CopyU20(ctypes.LittleEndianStructure):
        op = OpCode.COPY_LEN_U20
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("_length", ctypes.c_uint16),
        ]
        _pack_ = 1

        @property
        def length(self):
            return (OpCode.data(self.opcode) << 16) | self._length

    class CopyU32(ctypes.LittleEndianStructure):
        op = OpCode.COPY_LEN_U32
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("length", ctypes.c_uint32),
        ]
        _pack_ = 1

    def __init__(self, length: int, original_offset: int = -1):
        assert length != 0
        self.length = length
        # Used in construction to simplify optimisations
        self.original_offset = original_offset

    def ctypes_class(self):
        if self.length < 16:
            return self.CopyU4
        elif self.length < 4096:
            return self.CopyU12
        elif self.length < 1048576:
            return self.CopyU20
        else:
            return self.CopyU32

    @classmethod
    def from_bytes(
        cls, b: bytes, offset: int, original_offset: int, _write_cache: List[bytes]
    ):
        opcode = OpCode.from_byte(b[offset])
        if opcode == OpCode.COPY_LEN_U4:
            s = cls.CopyU4.from_buffer_copy(b, offset)
        elif opcode == OpCode.COPY_LEN_U12:
            s = cls.CopyU12.from_buffer_copy(b, offset)
        elif opcode == OpCode.COPY_LEN_U20:
            s = cls.CopyU20.from_buffer_copy(b, offset)
        elif opcode == OpCode.COPY_LEN_U32:
            s = cls.CopyU32.from_buffer_copy(b, offset)
        else:
            raise RuntimeError

        return cls(s.length), ctypes.sizeof(s), original_offset + s.length

    def __bytes__(self):
        instr = self.ctypes_class()
        if self.length < 16:
            return bytes(instr(instr.op.value | self.length))
        elif self.length < 4096:
            top = self.length >> 8
            bottom = self.length & 0xFF
            return bytes(instr(instr.op.value | top, bottom))
        elif self.length < 1048576:
            top = self.length >> 16
            bottom = self.length & 0xFFFF
            return bytes(instr(instr.op.value | top, bottom))
        else:
            return bytes(instr(instr.op.value, self.length))

    def __str__(self):
        return f" COPY: {self.length:6d} bytes"


class WriteInstr(Instr):
    class WriteU4(ctypes.LittleEndianStructure):
        op = OpCode.WRITE_LEN_U4
        length = 1
        _fields_ = [
            ("opcode", ctypes.c_uint8),
        ]
        _pack_ = 1

        @property
        def length(self):
            return OpCode.data(self.opcode)

    class WriteU12(ctypes.LittleEndianStructure):
        op = OpCode.WRITE_LEN_U12
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("_length", ctypes.c_uint8),
        ]
        _pack_ = 1

        @property
        def length(self):
            return (OpCode.data(self.opcode) << 8) | self._length

    class WriteU20(ctypes.LittleEndianStructure):
        op = OpCode.WRITE_LEN_U20
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("_length", ctypes.c_uint16),
        ]
        _pack_ = 1

        @property
        def length(self):
            return (OpCode.data(self.opcode) << 16) | self._length

    class WriteU32(ctypes.LittleEndianStructure):
        op = OpCode.WRITE_LEN_U32
        _fields_ = [
            ("opcode", ctypes.c_uint8),
            ("length", ctypes.c_uint32),
        ]
        _pack_ = 1

    def __init__(self, data):
        assert len(data) != 0
        self.data = data

    def ctypes_class(self):
        if len(self.data) < 16:
            return self.WriteU4
        elif len(self.data) < 4096:
            return self.WriteU12
        elif len(self.data) < 1048576:
            return self.WriteU20
        else:
            return self.WriteU32

    @classmethod
    def from_bytes(
        cls, b: bytes, offset: int, original_offset: int, _write_cache: List[bytes]
    ):
        opcode = OpCode.from_byte(b[offset])
        if opcode == OpCode.WRITE_LEN_U4:
            s = cls.WriteU4.from_buffer_copy(b, offset)
        elif opcode == OpCode.WRITE_LEN_U12:
            s = cls.WriteU12.from_buffer_copy(b, offset)
        elif opcode == OpCode.WRITE_LEN_U20:
            s = cls.WriteU20.from_buffer_copy(b, offset)
        elif opcode == OpCode.WRITE_LEN_U32:
            s = cls.WriteU32.from_buffer_copy(b, offset)
        else:
            raise RuntimeError
        hdr_len = ctypes.sizeof(s)

        return (
            cls(b[offset + hdr_len : offset + hdr_len + s.length]),
            hdr_len + s.length,
            original_offset + s.length,
        )

    def __bytes__(self):
        instr = self.ctypes_class()
        if len(self.data) < 16:
            return bytes(instr(instr.op.value | len(self.data))) + self.data
        elif len(self.data) < 4096:
            top = len(self.data) >> 8
            bottom = len(self.data) & 0xFF
            return bytes(instr(instr.op.value | top, bottom)) + self.data
        elif len(self.data) < 1048576:
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


class WriteCachedInstr(Instr):
    class WriteCached(ctypes.LittleEndianStructure):
        op = OpCode.WRITE_CACHED
        _fields_ = [
            ("opcode", ctypes.c_uint8),
        ]
        _pack_ = 1

    def __init__(self, idx, write_len):
        self.idx = idx
        self.write_len = write_len

    def ctypes_class(self):
        return self.WriteCached

    @classmethod
    def from_bytes(
        cls, b: bytes, offset: int, original_offset: int, write_cache: List[bytes]
    ):
        """Reconstruct class from bytes"""
        instr = cls.WriteCached.from_buffer_copy(b, offset)
        idx = OpCode.data(instr.opcode)
        write_len = len(write_cache[idx])
        return (
            cls(idx, write_len),
            ctypes.sizeof(instr),
            original_offset + write_len,
        )

    def __bytes__(self):
        instr = self.ctypes_class()
        op = instr.op.value | self.idx
        return bytes(instr(op))

    def __str__(self):
        return f"WRITE: Cache index {self.idx} ({self.write_len} bytes)"

    def __len__(self):
        return ctypes.sizeof(self.ctypes_class())


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
    def from_bytes(
        cls, b: bytes, offset: int, original_offset: int, _write_cache: List[bytes]
    ):
        assert b[offset] == OpCode.PATCH
        operations = []
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
            operations.append(
                WriteInstr(b[offset + length : offset + length + write_len])
            )
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


class diff:
    class PatchHeader(ctypes.LittleEndianStructure):
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
            ("original_file", ArrayValidation),
            ("constructed_file", ArrayValidation),
            ("patch_file", ArrayValidation),
            ("write_cache", 128 * ctypes.c_uint8),
            ("header_crc", ctypes.c_uint32),
        ]
        _pack_ = 1

    @classmethod
    def _naive_diff(cls, old: bytes, new: bytes, hash_len: int = 8):
        """Construct basic runs Merge runs of COPY and WRITE into PATCH"""
        instr = []
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
                    instr.append(
                        WriteInstr(new[write_start : write_start + write_pending])
                    )
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
                        and new[new_offset + this_match]
                        == old[orig_offset + this_match]
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
    def _common_writes(cls, instructions: List[Instr]) -> OrderedDict:
        common = OrderedDict()

        write_chunks = defaultdict(int)
        for instr in instructions:
            if isinstance(instr, WriteInstr):
                if len(instr.data) < 8:
                    continue
                write_chunks[instr.data] += 1

        for val, cnt in write_chunks.items():
            if cnt > 2:
                common[val] = (cnt - 1) * len(val)

        by_savings = sorted(common.items(), key=lambda x: x[1], reverse=True)
        allocated = 0

        # This allocation scheme is not necessarily the most efficient.
        # A 100 byte chunk that saves 1000 bytes would be chosen over
        # two 50 byte chunks that save 800 bytes each
        cached = []
        for write_bytes, _ in by_savings:
            if len(cached) > 16:
                break
            if (1 + len(write_bytes) + allocated) > cls.PatchHeader.cache_size:
                continue
            cached.append(write_bytes)
            allocated += 1 + len(write_bytes)

        # Replace the writes that are of common values
        out_instr = []
        for instr in instructions:
            if isinstance(instr, WriteInstr):
                if instr.data in cached:
                    out_instr.append(
                        WriteCachedInstr(cached.index(instr.data), len(instr.data))
                    )
                else:
                    out_instr.append(instr)
            else:
                out_instr.append(instr)

        return cached, out_instr

    @classmethod
    def _cleanup_jumps(cls, old: bytes, instructions: List[Instr]) -> List[Instr]:
        """Find locations that jumped backwards just to jump forward to original location"""

        merged: List[Instr] = []
        while len(instructions) > 0:
            instr = instructions.pop(0)
            replaced = False

            if isinstance(instr, SetAddrInstr):
                copy = instructions[0]
                assert isinstance(copy, CopyInstr)

                if len(instructions) >= 2 and isinstance(instructions[1], SetAddrInstr):
                    # ADDR, COPY, ADRR
                    if instr.shift == -instructions[1].shift:
                        # Replace with a write instead
                        merged.append(
                            WriteInstr(old[instr.new : instr.new + copy.length])
                        )
                        replaced = True
                        instructions.pop(0)
                        instructions.pop(0)
                elif (
                    len(instructions) >= 3
                    and isinstance(instructions[1], WriteInstr)
                    and isinstance(instructions[2], SetAddrInstr)
                ):
                    # ADDR, COPY, WRITE, ADRR
                    if instr.shift == -instructions[2].shift:
                        write = instructions[1]
                        # Replace with a merged write instead
                        merged.append(
                            WriteInstr(
                                old[instr.new : instr.new + copy.length] + write.data
                            )
                        )
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
    def _merge_operations(cls, instructions: List[Instr]) -> List[Instr]:
        """Merge runs of COPY and WRITE into PATCH"""
        merged: List[Instr] = []
        to_merge = []

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
            pended = False

            if isinstance(instr, CopyInstr):
                if instr.length < 128:
                    to_merge.append(instr)
                    pended = True
            elif isinstance(instr, WriteInstr):
                if len(to_merge) > 0 and len(instr.data) < 256:
                    to_merge.append(instr)
                    pended = True
            if not pended:
                finalise()
                merged.append(instr)

        if len(to_merge) > 0:
            finalise()
        return merged

    @classmethod
    def _merge_crack(cls, old: bytes, instructions: List[Instr]) -> List[Instr]:
        """Crack a WRITE operation in a PATCH into a [WRITE,COPY,WRITE] if COPY is at least 2 bytes"""

        for instr in instructions:
            if not isinstance(instr, PatchInstr):
                continue

            old_offset = 0
            updated_ops = []
            while len(instr.operations) > 0:
                if len(instr.operations) == 1:
                    updated_ops.append(instr.operations.pop())
                    continue

                copy_op = instr.operations.pop(0)
                write_op = instr.operations.pop(0)
                assert isinstance(copy_op, CopyInstr)
                assert isinstance(write_op, WriteInstr)
                assert copy_op.original_offset != -1

                old_offset = copy_op.original_offset + copy_op.length
                updated_ops.append(copy_op)

                if len(write_op.data) < 4:
                    # Too small to crack
                    updated_ops.append(write_op)
                    continue

                split = [0]
                for idx, b in enumerate(write_op.data):
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
                assert sum(split) == len(write_op.data)

                if len(split) % 2 == 0:
                    # Ended on a copy
                    copy_len = split.pop()
                    if len(instr.operations) > 0:
                        # Push the match into the next instruction if possible
                        assert isinstance(instr.operations[0], CopyInstr)
                        instr.operations[0].length += copy_len
                        instr.operations[0].original_offset -= copy_len
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
                        updated_ops.append(
                            WriteInstr(write_op.data[offset : offset + write_len])
                        )
                        offset += write_len
                        updated_ops.append(CopyInstr(copy_len, old_offset + offset))
                        offset += copy_len

                # Append the final WRITE
                write_len = split.pop()
                updated_ops.append(
                    WriteInstr(write_op.data[offset : offset + write_len])
                )

            # Update the PATCH operations
            instr.operations = updated_ops

        return instructions

    @classmethod
    def _gen_patch_instr(cls, bin_orig: bytes, bin_new: bytes) -> List[Instr]:
        best_patch = None
        best_write_cache = None
        best_patch_len = 2**32

        # Find best diff across range
        for i in range(4, 8):
            instr = cls._naive_diff(bin_orig, bin_new, i)
            instr = cls._cleanup_jumps(bin_orig, instr)
            write_cache, instr = cls._common_writes(instr)
            instr = cls._merge_operations(instr)
            instr = cls._merge_crack(bin_orig, instr)
            patch_len = sum([len(i) for i in instr])

            if patch_len < best_patch_len:
                best_patch = instr
                best_write_cache = write_cache
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

        return metadata, best_write_cache, best_patch

    @classmethod
    def _gen_patch_header(
        cls, patch_metadata: Dict, write_cache: List[bytes], patch_data: bytes
    ):
        cache_bin = b""
        for entry in write_cache:
            cache_bin += len(entry).to_bytes(1, "little") + entry
        cache_bin += (cls.PatchHeader.cache_size - len(cache_bin)) * b"\x00"
        assert len(cache_bin) == cls.PatchHeader.cache_size
        c = (ctypes.c_uint8 * cls.PatchHeader.cache_size).from_buffer_copy(cache_bin)

        hdr = cls.PatchHeader(
            cls.PatchHeader.magic_value,
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
            c,
            0,
        )
        hdr_no_crc = bytes(hdr)
        hdr.header_crc = binascii.crc32(hdr_no_crc[: -ctypes.sizeof(ctypes.c_uint32)])
        return bytes(hdr)

    @classmethod
    def _gen_patch_data(cls, instructions: List[Instr]):
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

        header_crc = binascii.crc32(
            patch_binary[: ctypes.sizeof(hdr) - ctypes.sizeof(ctypes.c_uint32)]
        )
        if header_crc != hdr.header_crc:
            raise ValidationError("Patch header validation failed")
        if len(data) != hdr.patch_file.length:
            raise ValidationError(
                f"Patch data length does not match header information ({len(data)} != {hdr.patch_file.length})"
            )
        if binascii.crc32(data) != hdr.patch_file.crc:
            raise ValidationError(
                f"Patch data CRC does not match patch information ({binascii.crc32(data):08x} != {hdr.patch_file.crc:08x})"
            )

        cache = []
        cache_bin = bytes(hdr.write_cache)
        while len(cache_bin) and cache_bin[0] != 0:
            l = cache_bin[0]
            cache.append(cache_bin[1 : 1 + l])
            cache_bin = cache_bin[1 + l :]

        instructions = []
        patch_offset = 0
        original_offset = 0
        while patch_offset < len(data):
            instr, length, original_offset = Instr.from_bytes(
                data, patch_offset, original_offset, cache
            )
            patch_offset += length
            instructions.append(instr)

        return metadata, cache, instructions

    @classmethod
    def generate(
        cls,
        bin_original: bytes,
        bin_new: bytes,
        verbose: bool,
    ) -> bytes:
        meta, cache, instructions = diff._gen_patch_instr(bin_original, bin_new)
        patch_data = diff._gen_patch_data(instructions)
        patch_header = diff._gen_patch_header(meta, cache, patch_data)
        bin_patch = patch_header + patch_data
        ratio = 100 * len(bin_patch) / meta["new"]["len"]

        print(f"Original File: {meta['original']['len']:6d} bytes")
        print(f"     New File: {meta['new']['len']:6d} bytes")
        print(
            f"   Patch File: {len(bin_patch):6d} bytes ({ratio:.2f}%) ({len(instructions):5d} instructions)"
        )

        if verbose:
            class_count = defaultdict(int)
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
    def patch(
        cls,
        bin_original: bytes,
        bin_patch: bytes,
    ) -> bytes:
        meta, cache, instructions = diff._patch_load(bin_patch)
        patched = b""
        orig_offset = 0

        if len(bin_original) != meta["original"]["len"]:
            raise ValidationError(
                f"Original file length does not match patch information ({len(bin_original)} != {meta['original']['len']})"
            )
        if binascii.crc32(bin_original) != meta["original"]["crc"]:
            raise ValidationError(
                f"Original file CRC does not match patch information ({binascii.crc32(bin_original):08x} != {meta['original']['crc']:08x})"
            )

        for instr in instructions:
            if isinstance(instr, CopyInstr):
                patched += bin_original[orig_offset : orig_offset + instr.length]
                orig_offset += instr.length
            elif isinstance(instr, WriteInstr):
                patched += instr.data
                orig_offset += len(instr.data)
            elif isinstance(instr, WriteCachedInstr):
                patched += cache[instr.idx]
                orig_offset += len(cache[instr.idx])
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
        if len(patched) != meta["new"]["len"]:
            raise ValidationError(
                f"Original file length does not match patch information ({len(patched)} != {meta['new']['len']})"
            )
        if binascii.crc32(patched) != meta["new"]["crc"]:
            raise ValidationError(
                f"Original file CRC does not match patch information ({binascii.crc32(patched):08x} != {meta['new']['crc']:08x})"
            )

        return patched

    @classmethod
    def dump(
        cls,
        bin_patch: bytes,
    ):
        meta, cache, instructions = diff._patch_load(bin_patch)
        total_write_bytes = 0

        print(f"Original File: {meta['original']['len']:6d} bytes")
        print(f"     New File: {meta['new']['len']:6d} bytes")
        print(
            f"   Patch File: {meta['patch']['len']:6d} bytes ({len(instructions):5d} instructions)"
        )
        print("")
        print("Write Cache:")
        for idx, entry in enumerate(cache):
            total_write_bytes += len(entry)
            print(f"\t{idx:2d}: {entry.hex()}")

        class_count = defaultdict(int)
        for instr in instructions:
            class_count[instr.ctypes_class().op] += 1
            if isinstance(instr, WriteInstr):
                total_write_bytes += len(instr.data)
            elif isinstance(instr, PatchInstr):
                for op in instr.operations:
                    if isinstance(op, WriteInstr):
                        total_write_bytes += len(op.data)

        print("")
        print("Patch Data Split")
        print(
            f"\tWRITE data: {total_write_bytes} bytes ({100*total_write_bytes/len(bin_patch):.2f}%)"
        )

        print("")
        print("Instruction Count:")
        for cls, count in sorted(class_count.items()):
            print(f"{cls.name:>16s}: {count}")

        print("")
        print("Instruction List:")
        for instr in instructions:
            print(instr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose command output"
    )
    subparser = parser.add_subparsers(dest="command", title="Commands", required=True)

    # Generate patch file
    generate_args = subparser.add_parser("generate", help="Generate a patch file")
    generate_args.add_argument("original", help="Original file to use as base image")
    generate_args.add_argument(
        "new", help="New file that will be the result of applying the patch"
    )
    generate_args.add_argument("patch", help="Output patch file name")

    # Apply patch file
    patch_args = subparser.add_parser("patch", help="Apply a patch file")
    patch_args.add_argument("original", help="Original file to use as base image")
    patch_args.add_argument("patch", help="Patch file to apply")
    patch_args.add_argument("output", help="File to write output to")

    # Dump patch instructions
    dump_args = subparser.add_parser(
        "dump", help="Dump patch file instructions to terminal"
    )
    dump_args.add_argument("patch", help="Patch file to dump")

    # Parse args
    args = parser.parse_args()

    # Run requested command
    if args.command == "generate":
        with open(args.original, "rb") as f_orig:
            with open(args.new, "rb") as f_new:
                patch = diff.generate(
                    f_orig.read(-1),
                    f_new.read(-1),
                    args.verbose,
                )
        with open(args.patch, "wb") as f_output:
            f_output.write(patch)
    elif args.command == "patch":
        with open(args.original, "rb") as f_orig:
            with open(args.patch, "rb") as f_patch:
                output = diff.patch(f_orig.read(-1), f_patch.read(-1))
        with open(args.output, "wb") as f_output:
            f_output.write(output)
    elif args.command == "dump":
        with open(args.patch, "rb") as f_patch:
            diff.dump(f_patch.read(-1))
