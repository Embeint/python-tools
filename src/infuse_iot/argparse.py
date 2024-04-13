#!/usr/bin/env python3

import argparse
import pathlib

class ValidFile:
    def __new__(self, string) -> pathlib.Path:
        p = pathlib.Path(string)
        if p.exists():
            return p
        else:
            raise argparse.ArgumentTypeError(f'{string} does not exist')
