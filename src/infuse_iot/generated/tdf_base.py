#!/usr/bin/env python3

import ctypes

from typing import Generator, Callable, Tuple
from typing_extensions import Self


class TdfStructBase(ctypes.LittleEndianStructure):
    def iter_fields(
        self,
    ) -> Generator[Tuple[str, ctypes._SimpleCData, str, Callable], None, None]:
        for field in self._fields_:
            if field[0][0] == "_":
                f_name = field[0][1:]
            else:
                f_name = field[0]
            val = getattr(self, f_name)
            yield f_name, val, self._postfix_[f_name], self._display_fmt_[f_name]


class TdfReadingBase(ctypes.LittleEndianStructure):
    def iter_fields(
        self,
    ) -> Generator[Tuple[str, ctypes._SimpleCData, str, Callable], None, None]:
        for field in self._fields_:
            if field[0][0] == "_":
                f_name = field[0][1:]
            else:
                f_name = field[0]
            val = getattr(self, f_name)
            if isinstance(val, ctypes.LittleEndianStructure):
                for (
                    subfield_name,
                    subfield_val,
                    subfield_postfix,
                    display_fmt,
                ) in val.iter_fields():
                    yield (
                        f"{f_name}.{subfield_name}",
                        subfield_val,
                        subfield_postfix,
                        display_fmt,
                    )
            elif isinstance(val, ctypes.Array):
                yield (
                    f_name,
                    list(val),
                    self._postfix_[f_name],
                    self._display_fmt_[f_name],
                )
            else:
                yield f_name, val, self._postfix_[f_name], self._display_fmt_[f_name]

    @classmethod
    def from_buffer_consume(cls, source: bytes, offset: int = 0) -> Self:
        last_field = cls._fields_[-1]

        # Last value not a VLA
        if getattr(last_field[1], "_length_", 1) != 0:
            return cls.from_buffer_copy(source, offset)

        base_size = ctypes.sizeof(cls)
        var_name = last_field[0]
        var_type = last_field[1]._type_
        var_type_size = ctypes.sizeof(var_type)

        source_var_len = len(source) - base_size
        if source_var_len % var_type_size != 0:
            raise RuntimeError
        source_var_num = source_var_len // var_type_size

        # Dynamically create subclass with correct length
        class TdfVLA(ctypes.LittleEndianStructure):
            name = cls.name
            _fields_ = cls._fields_[:-1] + [(var_name, source_var_num * var_type)]
            _pack_ = 1
            _postfix_ = cls._postfix_
            _display_fmt_ = cls._display_fmt_
            iter_fields = cls.iter_fields

        return TdfVLA.from_buffer_copy(source, offset)
