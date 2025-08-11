#!/usr/bin/env python3

import ctypes
from collections.abc import Generator
from typing import Any, cast

from typing_extensions import Self


def _public_name(internal_field):
    if internal_field[0][0] == "_":
        return internal_field[0][1:]
    return internal_field[0]


class TdfField:
    def __init__(self, field: str, subfield: str | None, postfix: str, display_fmt: str, val: Any):
        self.field = field
        self.subfield = subfield
        self.postfix = postfix
        self._display_fmt = display_fmt
        self.val = val

    @property
    def name(self) -> str:
        if self.subfield:
            return f"{self.field}.{self.subfield}"
        return self.field

    def val_fmt(self) -> str:
        return self._display_fmt.format(self.val)


class TdfStructBase(ctypes.LittleEndianStructure):
    def iter_fields(
        self,
        field: str,
    ) -> Generator[TdfField, None, None]:
        for subfield in self._fields_:
            sf_name = _public_name(subfield)
            val = getattr(self, sf_name)
            yield TdfField(
                field,
                sf_name,
                self._postfix_[sf_name],
                self._display_fmt_[sf_name],
                val,
            )


class TdfReadingBase(ctypes.LittleEndianStructure):
    NAME: str
    ID: int

    def iter_fields(self, nested_iter: bool = True) -> Generator[TdfField, None, None]:
        for field in self._fields_:
            f_name = _public_name(field)
            val = getattr(self, f_name)
            if nested_iter and isinstance(val, TdfStructBase):
                yield from val.iter_fields(f_name)
            else:
                if isinstance(val, ctypes.Array):
                    val = list(val)
                yield TdfField(
                    f_name,
                    None,
                    self._postfix_[f_name],
                    self._display_fmt_[f_name],
                    val,
                )

    @classmethod
    def field_information(cls):
        info = []
        for field in cls._fields_:
            f_name = _public_name(field)

            if issubclass(field[1], ctypes.LittleEndianStructure):
                subfields = []
                for subfield in field[1]._fields_:
                    sf_name = _public_name(subfield)
                    subfields.append({"name": sf_name, "type": subfield[1]})
                info.append({"name": f_name, "type": field[1], "subfields": subfields})
            elif isinstance(field[1], ctypes.Array):
                info.append({"name": f_name, "type": list})
            else:
                info.append({"name": f_name, "type": field[1]})
        return info

    @classmethod
    def from_buffer_consume(cls, source: bytes, offset: int = 0) -> Self:
        last_field = cls._fields_[-1]

        # Last value not a VLA
        if not issubclass(last_field[1], ctypes.Array):
            return cls.from_buffer_copy(source, offset)
        last_field_type: ctypes.Array = last_field[1]  # type: ignore
        if last_field_type._length_ != 0:
            return cls.from_buffer_copy(source, offset)

        base_size = ctypes.sizeof(cls)
        var_name = last_field[0]
        var_type = last_field_type._type_
        var_type_size = ctypes.sizeof(var_type)

        source_var_len = len(source) - base_size
        if source_var_len % var_type_size != 0:
            raise RuntimeError
        source_var_num = source_var_len // var_type_size

        # No trailing VLA
        if source_var_num == 0:
            return cls.from_buffer_copy(source, offset)

        # Dynamically create subclass with correct length
        class TdfVLA(ctypes.LittleEndianStructure):
            NAME = cls.NAME
            ID = cls.ID
            _fields_ = cls._fields_[:-1] + [(var_name, source_var_num * var_type)]  # type: ignore
            _pack_ = 1
            _postfix_ = cls._postfix_
            _display_fmt_ = cls._display_fmt_
            _vla_field_ = var_name
            iter_fields = cls.iter_fields
            field_information = cls.field_information

        # Copy convertor functions for fields
        for f in cls._fields_:
            if f[0][0] == "_":
                f_name = f[0][1:]
                setattr(TdfVLA, f_name, getattr(cls, f_name))

        # Create the object instance
        return cast(Self, TdfVLA.from_buffer_copy(source, offset))
