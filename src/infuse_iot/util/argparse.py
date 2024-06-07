#!/usr/bin/env python3

import argparse
import pathlib


class ValidFile:
    """Filesystem path that exists"""

    def __new__(cls, string) -> pathlib.Path:
        p = pathlib.Path(string)
        if p.exists():
            return p
        else:
            raise argparse.ArgumentTypeError(f"{string} does not exist")
