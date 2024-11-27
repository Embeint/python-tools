#!/usr/bin/env python3

import argparse
import pathlib
import re
from typing import cast


class ValidFile:
    """Filesystem path that exists"""

    def __new__(cls, string) -> pathlib.Path:  # type: ignore
        p = pathlib.Path(string)
        if p.exists():
            return p
        else:
            raise argparse.ArgumentTypeError(f"{string} does not exist")


class BtLeAddress:
    """Bluetooth Low-Energy address"""

    def __new__(cls, string) -> int:  # type: ignore
        pattern = r"((([0-9a-fA-F]{2}):){5})([0-9a-fA-F]{2})"

        if re.match(pattern, string):
            mac_cleaned = string.replace(":", "").replace("-", "")
            addr = int(mac_cleaned, 16)
        else:
            try:
                addr = int(string, 16)
            except ValueError:
                raise argparse.ArgumentTypeError(f"{string} is not a Bluetooth address")
        return addr

    @classmethod
    def integer_value(cls, string) -> int:
        return cast(int, cls(string))
