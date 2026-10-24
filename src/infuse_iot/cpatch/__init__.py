#!/usr/bin/env python3

import binascii
import ctypes
import enum
import logging
from collections import defaultdict

from infuse_iot.cpatch import encoder_greedy
from infuse_iot.cpatch.instructions import (
    CopyInstr,
    Instr,
    OpCode,
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

    def encode(self, bin_original: bytes, bin_new: bytes) -> list[Instr]:
        return encoder_greedy.encode(bin_original, bin_new)


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
        encoder: Encoder = Encoder.GREEDY,
    ) -> bytes:
        meta = cls._gen_metadata(bin_original, bin_new)
        instructions = encoder.encode(bin_original, bin_new)
        patch_data = cls._gen_patch_data(instructions)
        patch_header = cls._gen_patch_header(meta, patch_data)
        bin_patch = patch_header + patch_data
        ratio = 100 * len(bin_patch) / meta["new"]["len"]

        logger.info(f"Original File: {meta['original']['len']:6d} bytes")
        logger.info(f"     New File: {meta['new']['len']:6d} bytes")
        logger.info(f"   Patch File: {len(bin_patch):6d} bytes ({ratio:.2f}%) ({len(instructions):5d} instructions)")

        if verbose:
            class_count: dict[OpCode, int] = defaultdict(int)
            for instr in instructions:
                class_count[instr.ctypes_class().op] += 1

            logger.info("")
            logger.info("Instructions:")
            for instr_cls, instr_count in sorted(class_count.items()):
                logger.info(f"{instr_cls.name:>16s}: {instr_count}")

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

        meta = cls._gen_metadata(bin_original, bin_original)
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
