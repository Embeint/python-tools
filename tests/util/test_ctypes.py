import ctypes
import os

from infuse_iot.util.ctypes import VLACompatLittleEndianStruct

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


class VLABase(VLACompatLittleEndianStruct):
    _fields_ = [
        ("first", ctypes.c_uint32),
    ]
    vla_field = ("vla", 0 * ctypes.c_uint32)
    _pack_ = 1


class VLACountedBy(VLACompatLittleEndianStruct):
    _fields_ = [
        ("count", ctypes.c_uint8),
    ]
    vla_field = ("data", 0 * ctypes.c_uint8)
    vla_counted_by = "count"
    _pack_ = 1


class VLANested(VLACompatLittleEndianStruct):
    _fields_ = [
        ("first", ctypes.c_uint32),
    ]
    vla_field = ("vla", VLABase)
    _pack_ = 1


class VLADualNested(VLACompatLittleEndianStruct):
    _fields_ = [
        ("num", ctypes.c_uint8),
    ]
    vla_field = ("values", 0 * VLACountedBy)
    _pack_ = 1


class VLANone(VLACompatLittleEndianStruct):
    _fields_ = [
        ("first", ctypes.c_uint32),
        ("second", ctypes.c_uint32),
    ]
    _pack_ = 1


def test_vla_compat_struct():
    b = b"".join(x.to_bytes(4, "little") for x in range(2, 10))

    base = VLABase.vla_from_buffer_copy(b)
    assert base.first == 2
    assert len(base.vla) == 7
    for idx, val in enumerate(base.vla):
        assert val == idx + 3

    nested = VLANested.vla_from_buffer_copy(b)
    assert nested.first == 2
    assert nested.vla.first == 3
    assert len(nested.vla.vla) == 6
    for idx, val in enumerate(nested.vla.vla):
        assert val == idx + 4

    none = VLANone.vla_from_buffer_copy(b)
    assert none.first == 2
    assert none.second == 3

    one_element = b"\x01\x01\xff"
    two_element = b"\x02\x01\x33\x02\xaa\x55"
    dual_nested_one = VLADualNested.vla_from_buffer_copy(one_element)
    assert dual_nested_one.num == 1
    assert len(dual_nested_one.values) == 1
    assert dual_nested_one.values[0].count == 1
    assert len(dual_nested_one.values[0].data) == 1
    assert dual_nested_one.values[0].data[0] == 0xFF
    dual_nested_two = VLADualNested.vla_from_buffer_copy(two_element)
    assert dual_nested_two.num == 2
    assert len(dual_nested_two.values) == 2
    assert dual_nested_two.values[0].count == 1
    assert len(dual_nested_one.values[0].data) == 1
    assert dual_nested_two.values[0].data[0] == 0x33
    assert dual_nested_two.values[1].count == 2
    assert len(dual_nested_two.values[1].data) == 2
    assert dual_nested_two.values[1].data[0] == 0xAA
    assert dual_nested_two.values[1].data[1] == 0x55

    unaligned = b"\x00" * 31
    try:
        VLABase.vla_from_buffer_copy(unaligned)
        raise AssertionError()
    except TypeError:
        pass
    try:
        VLANested.vla_from_buffer_copy(unaligned)
        raise AssertionError()
    except TypeError:
        pass
