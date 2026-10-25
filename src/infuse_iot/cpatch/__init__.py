#!/usr/bin/env python3

import binascii
import ctypes
import enum
import logging
from collections import defaultdict
from typing import Any

from infuse_iot.cpatch import (
    encoder_greedy,
    encoder_shortest_path,
    encoder_shortest_path_delta,
    encoder_stream_thumb2,
    stream,
)
from infuse_iot.cpatch.instructions import (
    CopyInstr,
    DeltaHistory,
    Instr,
    OpCode,
    PatchDeltaInstr,
    PatchInstr,
    SetAddrInstr,
    WriteInstr,
)

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Generic patch validation exception"""


class Encoder(enum.Enum):
    """Algorithm used to generate the patch instructions"""

    # Greedy longest match with cleanup passes
    GREEDY = "greedy"
    # Minimum encoded size over candidate matching runs
    SHORTEST_PATH = "shortest-path"
    # As SHORTEST_PATH, additionally using PATCH_DELTA (requires patch format version 2)
    SHORTEST_PATH_DELTA = "shortest-path-delta"
    # Element stream with relocation of Thumb-2 branches and pointers (requires patch format version 3)
    STREAM_THUMB2 = "stream-thumb2"

    @property
    def version(self) -> tuple[int, int]:
        """Patch (major, minor) version, identifying the encoder that generated the patch"""
        if self == Encoder.STREAM_THUMB2:
            return (cpatch.PatchHeader.VERSION_MAJOR_STREAM_THUMB2, 0)
        if self == Encoder.SHORTEST_PATH_DELTA:
            # Existing appliers reject the newer major version before applying any instructions
            return (cpatch.PatchHeader.VERSION_MAJOR_DELTA, 0)
        if self == Encoder.SHORTEST_PATH:
            return (cpatch.PatchHeader.VERSION_MAJOR, 1)
        return (cpatch.PatchHeader.VERSION_MAJOR, cpatch.PatchHeader.VERSION_MINOR)

    def encode(self, bin_original: bytes, bin_new: bytes) -> list[Instr]:
        assert self != Encoder.STREAM_THUMB2, "Element streams are not instructions, use `encoder_stream_thumb2.encode`"
        if self == Encoder.GREEDY:
            return encoder_greedy.encode(bin_original, bin_new)
        if self == Encoder.SHORTEST_PATH_DELTA:
            return encoder_shortest_path_delta.encode(bin_original, bin_new)
        return encoder_shortest_path.encode(bin_original, bin_new)


class cpatch:
    class PatchHeader(ctypes.LittleEndianStructure):
        VERSION_MAJOR = 1
        VERSION_MINOR = 0
        # Patches containing PATCH_DELTA instructions
        VERSION_MAJOR_DELTA = 2
        # Patches containing an element stream for Thumb-2 images, with a relocation preamble
        VERSION_MAJOR_STREAM_THUMB2 = 3

        class ArrayValidation(ctypes.LittleEndianStructure):
            _fields_ = [
                ("length", ctypes.c_uint32),
                ("crc", ctypes.c_uint32),
            ]
            _pack_ = 1
            _layout_ = "ms"

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
        _layout_ = "ms"

    @classmethod
    def _gen_metadata(cls, bin_orig: bytes, bin_new: bytes) -> dict:
        return {
            "original": {
                "len": len(bin_orig),
                "crc": binascii.crc32(bin_orig),
            },
            "new": {
                "len": len(bin_new),
                "crc": binascii.crc32(bin_new),
            },
        }

    @classmethod
    def _gen_patch_header(
        cls,
        patch_metadata: dict,
        patch_data: bytes,
        version: tuple[int, int] = (PatchHeader.VERSION_MAJOR, PatchHeader.VERSION_MINOR),
    ):
        hdr = cls.PatchHeader(
            cls.PatchHeader.magic_value,
            version[0],
            version[1],
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
    def _patch_load(cls, patch_binary: bytes) -> tuple[dict[str, Any], list[Any]]:
        """Validate a patch, returning its metadata and instructions (elements for version 3)"""
        hdr = cls.PatchHeader.from_buffer_copy(patch_binary)
        data = patch_binary[ctypes.sizeof(cls.PatchHeader) :]

        metadata: dict[str, Any] = {
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
        if hdr.version_major not in (
            cls.PatchHeader.VERSION_MAJOR,
            cls.PatchHeader.VERSION_MAJOR_DELTA,
            cls.PatchHeader.VERSION_MAJOR_STREAM_THUMB2,
        ):
            raise ValidationError(f"Unsupported patch version ({hdr.version_major})")
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

        metadata["version"] = (hdr.version_major, hdr.version_minor)
        if hdr.version_major == cls.PatchHeader.VERSION_MAJOR_STREAM_THUMB2:
            # Version 3 patch data is a relocation preamble and an element stream
            try:
                preamble, elements = stream.decode(data)
            except stream.ValidationError as e:
                raise ValidationError(str(e)) from e
            metadata["preamble"] = preamble
            return metadata, elements

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
        encoder: Encoder = Encoder.SHORTEST_PATH,
    ) -> bytes:
        meta = cls._gen_metadata(bin_original, bin_new)
        counts: dict[str, int]
        instructions: list[Instr] | list[stream.Element]
        if encoder == Encoder.STREAM_THUMB2:
            preamble, elements = encoder_stream_thumb2.encode(bin_original, bin_new)
            patch_data = stream.encode(preamble, elements)
            counts = dict(stream.op_counts(elements))
            instructions = elements
        else:
            instructions = encoder.encode(bin_original, bin_new)
            patch_data = cls._gen_patch_data(instructions)
            class_count: dict[OpCode, int] = defaultdict(int)
            for instr in instructions:
                class_count[instr.ctypes_class().op] += 1
            counts = {op.name: count for op, count in sorted(class_count.items())}
        patch_header = cls._gen_patch_header(meta, patch_data, encoder.version)
        bin_patch = patch_header + patch_data
        ratio = 100 * len(bin_patch) / meta["new"]["len"]

        logger.info(f"Original File: {meta['original']['len']:6d} bytes")
        logger.info(f"     New File: {meta['new']['len']:6d} bytes")
        logger.info(f"   Patch File: {len(bin_patch):6d} bytes ({ratio:.2f}%) ({len(instructions):5d} instructions)")

        if verbose:
            logger.info("")
            logger.info("Instructions:")
            for name, instr_count in counts.items():
                logger.info(f"{name:>16s}: {instr_count}")

        # Validate that file can be reconstructed
        patched = cls.patch(bin_original, bin_patch)
        assert bin_new == patched

        # Return complete file
        return bin_patch

    @classmethod
    def _validation_delta(cls, bin_original: bytes, offset: int) -> list[Instr]:
        """Instructions that run every PATCH_DELTA element type, reconstructing `bin_original[offset:]`"""

        def val16(o: int) -> int:
            return bin_original[o] | bin_original[o + 1] << 8

        instructions: list[Instr] = []
        history = DeltaHistory()

        # Every COPY length encoding on the current offset, where the required delta is 0
        elements = [(0, PatchDeltaInstr.EXPLICIT, 0)]
        history.use(None, 0)
        for copy_len in [*range(1, 15), 15, 100, PatchDeltaInstr.MAX_COPY]:
            elements.append((copy_len, 0, 0))
            history.use(0, 0)
        elements.append((5, PatchDeltaInstr.NONE, 0))
        elements.append((PatchDeltaInstr.MAX_COPY, PatchDeltaInstr.NONE, 0))
        instructions.append(PatchDeltaInstr(elements))
        out = offset + sum(c + (2 if a != PatchDeltaInstr.NONE else 0) for c, a, _ in elements)
        old = out

        # Additions of non-zero deltas read from a different offset in the original, such that
        # the output still matches the original.
        positions: dict[int, list[int]] = defaultdict(list)
        for o in range(len(bin_original) - 1):
            positions[val16(o)].append(o)

        def addition(x: int, y: int, index: int, delta: int) -> None:
            """Output the original at `x` by adding a delta to the original at `y`"""
            nonlocal out, old
            if x > out:
                if old != out:
                    instructions.append(SetAddrInstr(old, out))
                instructions.append(CopyInstr(x - out))
                old = x
            if old != y:
                instructions.append(SetAddrInstr(old, y))
            instructions.append(PatchDeltaInstr([(0, index, delta)]))
            history.use(None if index == PatchDeltaInstr.EXPLICIT else index, delta)
            out, old = x + 2, y + 2

        def history_addition(accept) -> None:
            for x in range(out, len(bin_original) - 1):
                for index, delta in enumerate(history.deltas):
                    for y in positions.get((val16(x) - delta) & 0xFFFF, []):
                        if accept(index, delta, y):
                            addition(x, y, index, 0)
                            return
            raise ValueError("Input file does not contain the values required for PATCH_DELTA validation")

        # Each history index, and at least one addition carrying out of the low byte
        for target in range(DeltaHistory.SIZE - 1, 0, -1):
            history_addition(lambda index, delta, y, target=target: index == target and delta != 0)
        history_addition(lambda index, delta, y: (val16(y) & 0xFF) + (delta & 0xFF) > 0xFF)

        # An explicit delta that is not in the history
        for x in range(out, len(bin_original) - 2):
            delta = (val16(x) - val16(x + 1)) & 0xFFFF
            if history.find(delta) is None:
                addition(x, x + 1, PatchDeltaInstr.EXPLICIT, delta)
                break
        else:
            raise ValueError("Input file does not contain the values required for PATCH_DELTA validation")

        # Remainder of the file
        if old != out:
            instructions.append(SetAddrInstr(old, out))
        if out < len(bin_original):
            instructions.append(CopyInstr(len(bin_original) - out))
        return instructions

    @classmethod
    def validation(
        cls,
        bin_original: bytes,
        invalid_length: bool,
        invalid_crc: bool,
        delta: bool = False,
        stream_thumb2: bool = False,
    ) -> bytes:
        assert len(bin_original) > 1024
        assert not (delta and stream_thumb2)

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
        if stream_thumb2:
            # Element streams require version 3 appliers, and replace all instructions
            preamble, elements = stream.validation(bin_original)
            patch_data = stream.encode(preamble, elements)
            version = (cls.PatchHeader.VERSION_MAJOR_STREAM_THUMB2, 0)
        elif delta:
            # PATCH_DELTA instructions require version 2 appliers
            instructions += cls._validation_delta(bin_original, 544)
            patch_data = cls._gen_patch_data(instructions)
            version = (cls.PatchHeader.VERSION_MAJOR_DELTA, 0)
        else:
            instructions.append(CopyInstr(len(bin_original) - 544))
            patch_data = cls._gen_patch_data(instructions)
            version = (cls.PatchHeader.VERSION_MAJOR, cls.PatchHeader.VERSION_MINOR)

        meta = cls._gen_metadata(bin_original, bin_original)
        if invalid_length:
            meta["new"]["len"] -= 1
        if invalid_crc:
            meta["new"]["crc"] -= 1

        patch_header = cls._gen_patch_header(meta, patch_data, version)
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
        history = DeltaHistory()

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

        if meta["version"][0] == cls.PatchHeader.VERSION_MAJOR_STREAM_THUMB2:
            try:
                patched = stream.apply(bin_original, meta["preamble"], instructions)
            except stream.ValidationError as e:
                raise ValidationError(str(e)) from e
            instructions = []

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
            elif isinstance(instr, PatchDeltaInstr):
                for copy_len, addition, delta in instr.elements:
                    patched += bin_original[orig_offset : orig_offset + copy_len]
                    orig_offset += copy_len
                    if addition == PatchDeltaInstr.NONE:
                        continue
                    index = None if addition == PatchDeltaInstr.EXPLICIT else addition
                    delta = history.use(index, delta)
                    val = int.from_bytes(bin_original[orig_offset : orig_offset + 2], "little")
                    patched += ((val + delta) & 0xFFFF).to_bytes(2, "little")
                    orig_offset += 2
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
    def _dump_stream(cls, bin_patch: bytes, meta: dict, elements: list[stream.Element]):
        preamble: stream.Preamble = meta["preamble"]
        total_write_bytes = sum(
            len(e.op.data) for e in elements if isinstance(e.op, (stream.Literal, stream.LiteralShift))
        )
        print(f"Original File: {meta['original']['len']:6d} bytes")
        print(f"     New File: {meta['new']['len']:6d} bytes")
        print(f"   Patch File: {len(bin_patch)} bytes ({len(elements):5d} elements)")
        print(f"   Relocation: flags {preamble.flags:02x}, base {preamble.base:08x}")
        print(f"Relocation Map: {len(preamble.map)} entries")
        for start, shift in preamble.map:
            print(f"\t{start:08x}: {shift:+d}")
        for region in preamble.regions:
            print(f"Pointer Region: {region.base:08x}-{region.base + region.length:08x}, {len(region.map)} entries")
            for start, shift in region.map:
                print(f"\t{start:08x}: {shift:+d}")

        print("")
        print("Total WRITE data:")
        print(f"\t{total_write_bytes} bytes ({100 * total_write_bytes / len(bin_patch):.2f}%)")

        print("")
        print("Operation Count:")
        for name, count in stream.op_counts(elements):
            print(f"{name:>16s}: {count}")

        print("")
        print("Element List:")
        for element in elements:
            print(element)

    @classmethod
    def dump(
        cls,
        bin_patch: bytes,
    ):
        meta, instructions = cls._patch_load(bin_patch)
        if meta["version"][0] == cls.PatchHeader.VERSION_MAJOR_STREAM_THUMB2:
            cls._dump_stream(bin_patch, meta, instructions)
            return
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
