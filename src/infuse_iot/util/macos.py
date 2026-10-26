"""Native macOS power state queries; importing this module is safe on other platforms."""

import ctypes
import functools
import os


class _Timeval(ctypes.Structure):
    # Darwin's timeval uses a 64-bit time_t and a 32-bit suseconds_t, with native alignment.
    _fields_ = [("seconds", ctypes.c_long), ("microseconds", ctypes.c_int)]


@functools.cache
def _sysctlbyname():
    system = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True)
    query = system.sysctlbyname
    query.argtypes = [
        ctypes.c_char_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_void_p,
        ctypes.c_size_t,
    ]
    query.restype = ctypes.c_int
    return query


def wake_time() -> tuple[int, int]:
    """Read the kernel's last system wake timestamp, without a subprocess or GUI event loop."""
    value = _Timeval()
    size = ctypes.c_size_t(ctypes.sizeof(value))
    if _sysctlbyname()(b"kern.waketime", ctypes.byref(value), ctypes.byref(size), None, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), "kern.waketime")
    return value.seconds, value.microseconds
