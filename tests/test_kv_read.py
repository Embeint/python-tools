#!/usr/bin/env python3

import ctypes
import os

from infuse_iot.rpc_wrappers.kv_read import _append_decoded_field
from infuse_iot.util.ctypes import VLACompatLittleEndianStruct

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


class Child(VLACompatLittleEndianStruct):
    _fields_ = [
        ("status", ctypes.c_uint8),
        ("count", ctypes.c_uint16),
    ]
    _pack_ = 1


class Parent(VLACompatLittleEndianStruct):
    _fields_ = [
        ("first", Child),
    ]
    vla_field = ("remainder", 0 * Child)
    _pack_ = 1


def test_append_decoded_field_decodes_struct_arrays():
    value = Parent.vla_from_buffer_copy(b"\x01\x02\x00\x03\x04\x00\x05\x06\x00")

    fields: list[tuple[str, object]] = []
    for field_name, field_val in value.iter_fields():
        _append_decoded_field(fields, field_name, field_val)

    assert fields == [
        ("first.status", 1),
        ("first.count", 2),
        ("remainder[0].status", 3),
        ("remainder[0].count", 4),
        ("remainder[1].status", 5),
        ("remainder[1].count", 6),
    ]
