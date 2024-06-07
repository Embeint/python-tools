#!/usr/bin/env python3

import ctypes
import enum

from infuse_iot.time import InfuseTime
from infuse_iot.generated import tdf_definitions


class TDF:
    class flags(enum.IntEnum):
        TIMESTAMP_NONE = 0x0000
        TIMESTAMP_ABSOLUTE = 0x4000
        TIMESTAMP_RELATIVE = 0x8000
        TIMESTAMP_EXTENDED_RELATIVE = 0xC000
        TIMESTAMP_MASK = 0xC000
        TIME_ARRAY = 0x1000
        ID_MASK = 0x0FFF

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

    def __init__(self):
        pass

    @staticmethod
    def _buffer_pull(buffer: bytes, type: ctypes.LittleEndianStructure):
        v = type.from_buffer_copy(buffer)
        b = buffer[ctypes.sizeof(type) :]
        return v, b

    def decode(self, buffer: bytes):
        output = []
        buffer_time = None

        while len(buffer) > 3:
            header, buffer = self._buffer_pull(buffer, self.CoreHeader)
            time_flags = header.id_flags & self.flags.TIMESTAMP_MASK

            tdf_id = header.id_flags & 0x0FFF
            id_type = tdf_definitions.id_type_mapping[tdf_id]

            if time_flags == self.flags.TIMESTAMP_NONE:
                time = None
            elif time_flags == self.flags.TIMESTAMP_ABSOLUTE:
                t, buffer = self._buffer_pull(buffer, self.AbsoluteTime)
                buffer_time = t.seconds * 65536 + t.subseconds
                time = InfuseTime.unix_time_from_civil(buffer_time)
            elif time_flags == self.flags.TIMESTAMP_RELATIVE:
                t, buffer = self._buffer_pull(buffer, self.RelativeTime)
                buffer_time += t.offset
                time = InfuseTime.unix_time_from_civil(buffer_time)
            elif time_flags == self.flags.TIMESTAMP_EXTENDED_RELATIVE:
                t, buffer = self._buffer_pull(buffer, self.ExtendedRelativeTime)
                buffer_time += t.offset
                time = InfuseTime.unix_time_from_civil(buffer_time)

            array_header = None
            if header.id_flags & self.flags.TIME_ARRAY:
                array_header, buffer = self._buffer_pull(buffer, self.ArrayHeader)
                total_len = array_header.num * header.len
                total_data = buffer[:total_len]
                buffer = buffer[total_len:]

                time = InfuseTime.unix_time_from_civil(buffer_time)
                data = [
                    id_type.from_buffer_copy(total_data[x : x + header.len])
                    for x in range(0, total_len, header.len)
                ]
            else:
                data_bytes = buffer[: header.len]
                buffer = buffer[header.len :]

                data = [id_type.from_buffer_copy(data_bytes)]

            reading = {"time": time, "data": data}
            if array_header is not None:
                reading["period"] = array_header.period / 65536

            output.append(reading)

        return output
