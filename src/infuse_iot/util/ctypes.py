#!/usr/bin/env python3

import ctypes


def bytes_to_uint8(b: bytes):
    return (len(b) * ctypes.c_uint8)(*b)
