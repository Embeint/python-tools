import ctypes
import os

from infuse_iot.util.ctypes import VLACompatLittleEndianStruct

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


class VLABase(VLACompatLittleEndianStruct):
    _fields_ = [
        ("first", ctypes.c_uint32),
    ]
    vla_field = ("vla", 0 * ctypes.c_uint32)


class VLANested(VLACompatLittleEndianStruct):
    _fields_ = [
        ("first", ctypes.c_uint32),
    ]
    vla_field = ("vla", VLABase)


class VLANone(VLACompatLittleEndianStruct):
    _fields_ = [
        ("first", ctypes.c_uint32),
        ("second", ctypes.c_uint32),
    ]


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
