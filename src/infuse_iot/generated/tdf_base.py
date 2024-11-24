#!/usr/bin/env python3

import ctypes

from typing import Generator, Callable, Tuple


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
