#!/usr/bin/env python3

import ctypes
from collections.abc import Generator

from typing_extensions import Any, Self


def bytes_to_uint8(b: bytes):
    return (len(b) * ctypes.c_uint8)(*b)


class VLACompatLittleEndianStruct(ctypes.LittleEndianStructure):
    vla_field: tuple[str, type[Any]] | None = None

    @classmethod
    def vla_from_buffer_copy(cls, source, offset=0) -> Self:
        base = cls.from_buffer_copy(source, offset)
        if cls.vla_field is None:
            return base

        remainder = source[ctypes.sizeof(cls) :]
        vla_field_name, vla_field_type = cls.vla_field  # type: ignore

        if issubclass(vla_field_type, ctypes.Array):
            array_base: ctypes._CData = vla_field_type._type_  # type: ignore

            # Determine the number of VLA elements on "source"
            vla_byte_len = (len(source) - offset) - ctypes.sizeof(cls)
            vla_element_size = ctypes.sizeof(array_base)
            if vla_byte_len % vla_element_size != 0:
                raise TypeError(f"Unaligned VLA buffer for {cls} (len {len(source)})")
            vla_num = vla_byte_len // vla_element_size
            vla_type = vla_num * array_base
            vla_val = vla_type.from_buffer_copy(remainder)
        elif issubclass(vla_field_type, VLACompatLittleEndianStruct):
            vla_val = vla_field_type.vla_from_buffer_copy(remainder)
        else:
            raise RuntimeError(f"Unhandled VLA type {vla_field_type}")

        setattr(base, vla_field_name, vla_val)
        return base

    def iter_fields(self, prefix: str = "") -> Generator[tuple[str, Any], None, None]:
        for field_name, _field_type in self._fields_:
            val = getattr(self, field_name)
            if isinstance(val, VLACompatLittleEndianStruct):
                yield from val.iter_fields(f"{field_name}.")
            else:
                yield (f"{prefix}{field_name}", val)
        if vla_field := self.vla_field:
            val = getattr(self, vla_field[0])
            if isinstance(val, VLACompatLittleEndianStruct):
                yield from val.iter_fields(f"{vla_field[0]}.")
            else:
                yield (f"{prefix}{vla_field[0]}", val)
