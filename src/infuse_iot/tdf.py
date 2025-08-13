#!/usr/bin/env python3

import copy
import ctypes
import enum
import time
from collections.abc import Generator

from infuse_iot.definitions import tdf as tdf_defs
from infuse_iot.generated import tdf_base
from infuse_iot.time import InfuseTime


def unknown_tdf_factory(tdf_id: int, tdf_len: int) -> type[tdf_base.TdfReadingBase]:
    class UnknownTDF(tdf_base.TdfReadingBase):
        NAME = str(tdf_id)
        ID = tdf_id
        _fields_ = [
            ("data", tdf_len * ctypes.c_uint8),
        ]
        _pack_ = 1
        _postfix_ = {"data": ""}
        _display_fmt_ = {"data": "{}"}

    return UnknownTDF


class TDF:
    class flags(enum.IntEnum):
        TIMESTAMP_NONE = 0x0000
        TIMESTAMP_ABSOLUTE = 0x4000
        TIMESTAMP_RELATIVE = 0x8000
        TIMESTAMP_EXTENDED_RELATIVE = 0xC000
        TIMESTAMP_MASK = 0xC000
        TIME_ARRAY = 0x1000
        DIFF_ARRAY = 0x2000
        IDX_ARRAY = 0x3000
        ARRAY_MASK = 0x3000
        ID_MASK = 0x0FFF

    class DiffType(enum.IntEnum):
        DIFF_16_8 = 1
        DIFF_32_8 = 2
        DIFF_32_16 = 3

    class CoreHeader(ctypes.LittleEndianStructure):
        _fields_ = [
            ("id_flags", ctypes.c_uint16),
            ("len", ctypes.c_uint8),
        ]
        _pack_ = 1

    class ArrayHeader(ctypes.LittleEndianStructure):
        _fields_ = [
            ("num", ctypes.c_uint8),
            ("period", ctypes.c_uint16),
        ]
        _pack_ = 1

    class AbsoluteTime(ctypes.LittleEndianStructure):
        _fields_ = [
            ("seconds", ctypes.c_uint32),
            ("subseconds", ctypes.c_uint16),
        ]
        _pack_ = 1

    class RelativeTime(ctypes.LittleEndianStructure):
        _fields_ = [
            ("offset", ctypes.c_uint16),
        ]
        _pack_ = 1

    class ExtendedRelativeTime(ctypes.LittleEndianStructure):
        _fields_ = [
            ("_offset", ctypes.c_uint8 * 3),
        ]
        _pack_ = 1

        @property
        def offset(self):
            return int.from_bytes(self._offset, byteorder="little", signed=True)

    class Reading:
        def __init__(
            self,
            tdf_id: int,
            reading_time: None | float,
            period: None | float,
            base_idx: None | int,
            data: list[tdf_base.TdfReadingBase],
        ):
            self.id = tdf_id
            self.time = reading_time
            self.period = period
            self.base_idx = base_idx
            self.data = data

    def __init__(self):
        pass

    @staticmethod
    def _buffer_pull(buffer: bytes, ctype: type[ctypes.LittleEndianStructure]):
        v = ctype.from_buffer_copy(buffer)
        b = buffer[ctypes.sizeof(ctype) :]
        return v, b

    @classmethod
    def _diff_expand(cls, buffer: bytes, tdf_len: int, diff_type: DiffType, diff_num: int) -> tuple[int, bytes]:
        t_in: type[ctypes._SimpleCData]
        t_diff: type[ctypes._SimpleCData]
        if diff_type == cls.DiffType.DIFF_16_8:
            t_in = ctypes.c_uint16
            t_diff = ctypes.c_int8
        elif diff_type == cls.DiffType.DIFF_32_8:
            t_in = ctypes.c_uint32
            t_diff = ctypes.c_int8
        elif diff_type == cls.DiffType.DIFF_32_16:
            t_in = ctypes.c_uint32
            t_diff = ctypes.c_int16
        else:
            raise RuntimeError(f"Unknown diff type {diff_type}")
        num_fields = tdf_len // ctypes.sizeof(t_in)

        class _tdf(ctypes.LittleEndianStructure):
            _fields_ = [("data", num_fields * t_in)]
            _pack_ = 1

        class _diff(ctypes.LittleEndianStructure):
            _fields_ = [("data", num_fields * t_diff)]
            _pack_ = 1

        class _complete(ctypes.LittleEndianStructure):
            _fields_ = [("base", _tdf), ("diffs", diff_num * _diff)]
            _pack_ = 1

        raw = _complete.from_buffer_copy(buffer)
        out: list[ctypes.LittleEndianStructure] = [_tdf.from_buffer_copy(buffer)]
        for idx in range(diff_num):
            next = copy.copy(out[-1])
            for f in range(num_fields):
                next.data[f] += raw.diffs[idx].data[f]
            out.append(next)

        expanded = b"".join([bytes(b) for b in out])
        return ctypes.sizeof(raw), expanded

    def decode(self, buffer: bytes, no_defs: bool = False) -> Generator[Reading, None, None]:
        buffer_time = None

        while len(buffer) > 3:
            header, buffer = self._buffer_pull(buffer, self.CoreHeader)
            time_flags = header.id_flags & self.flags.TIMESTAMP_MASK

            if header.id_flags in [0x0000, 0xFFFF]:
                break

            tdf_id = header.id_flags & 0x0FFF
            if no_defs:
                id_type = unknown_tdf_factory(tdf_id, header.len)
            else:
                try:
                    id_type = tdf_defs.id_type_mapping[tdf_id]
                except KeyError:
                    id_type = unknown_tdf_factory(tdf_id, header.len)

            if time_flags == self.flags.TIMESTAMP_NONE:
                reading_time = None
            elif time_flags == self.flags.TIMESTAMP_ABSOLUTE:
                t, buffer = self._buffer_pull(buffer, self.AbsoluteTime)
                buffer_time = t.seconds * 65536 + t.subseconds
                reading_time = InfuseTime.unix_time_from_epoch(buffer_time)
            elif time_flags == self.flags.TIMESTAMP_RELATIVE:
                t, buffer = self._buffer_pull(buffer, self.RelativeTime)
                buffer_time += t.offset
                reading_time = InfuseTime.unix_time_from_epoch(buffer_time)
            elif time_flags == self.flags.TIMESTAMP_EXTENDED_RELATIVE:
                t, buffer = self._buffer_pull(buffer, self.ExtendedRelativeTime)
                buffer_time += t.offset
                reading_time = InfuseTime.unix_time_from_epoch(buffer_time)
            else:
                raise RuntimeError("Unreachable time option")

            array_header = None
            base_idx = None
            array_type = header.id_flags & self.flags.ARRAY_MASK
            if array_type == self.flags.DIFF_ARRAY:
                array_header, buffer = self._buffer_pull(buffer, self.ArrayHeader)
                diff_type = array_header.num >> 6
                diff_num = array_header.num & 0x3F

                total_len, expanded = self._diff_expand(buffer, header.len, self.DiffType(diff_type), diff_num)
                buffer = buffer[total_len:]
                if buffer_time is None:
                    t_now = int(time.time() * 65536)
                    reading_time = InfuseTime.unix_time_from_epoch(t_now)
                else:
                    reading_time = InfuseTime.unix_time_from_epoch(buffer_time)
                data = [
                    id_type.from_buffer_consume(expanded[x : x + header.len]) for x in range(0, total_len, header.len)
                ]
            elif array_type == self.flags.TIME_ARRAY:
                array_header, buffer = self._buffer_pull(buffer, self.ArrayHeader)
                total_len = array_header.num * header.len
                total_data = buffer[:total_len]
                buffer = buffer[total_len:]

                if buffer_time is None:
                    t_now = int(time.time() * 65536)
                    reading_time = InfuseTime.unix_time_from_epoch(t_now)
                else:
                    reading_time = InfuseTime.unix_time_from_epoch(buffer_time)
                data = [
                    id_type.from_buffer_consume(total_data[x : x + header.len]) for x in range(0, total_len, header.len)
                ]
            elif array_type == self.flags.IDX_ARRAY:
                array_header, buffer = self._buffer_pull(buffer, self.ArrayHeader)
                total_len = array_header.num * header.len
                total_data = buffer[:total_len]
                buffer = buffer[total_len:]

                if time_flags != self.flags.TIMESTAMP_NONE:
                    assert buffer_time is not None
                    reading_time = InfuseTime.unix_time_from_epoch(buffer_time)
                base_idx = array_header.period
                data = [
                    id_type.from_buffer_consume(total_data[x : x + header.len]) for x in range(0, total_len, header.len)
                ]
            else:
                data_bytes = buffer[: header.len]
                buffer = buffer[header.len :]

                data = [id_type.from_buffer_consume(data_bytes)]

            period = None
            if array_header is not None and base_idx is None:
                period = array_header.period / 65536

            yield self.Reading(tdf_id, reading_time, period, base_idx, data)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        sys.exit("Expected `python -m infuse_iot.tdf /path/to/tdf.bin`")

    decoder = TDF()

    with open(sys.argv[1], "rb") as f:
        tdf_binary_blob = f.read(-1)

        # Check data is in the form we expect (single block, 2 byte prefix)
        if tdf_binary_blob[1] != 0x02:
            sys.exit("Expected second byte to be 0x02 (INFUSE_TDF)")

        try:
            for tdf in decoder.decode(tdf_binary_blob[2:]):
                print(f"TDF {tdf.id} @ t={tdf.time}: {tdf.data}")
        except Exception:
            pass
