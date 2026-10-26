import ctypes
import errno

import pytest

from infuse_iot.util import macos


def test_wake_time_reads_native_timeval(monkeypatch):
    def query(name, buffer, size, new_value, new_size):
        assert name == b"kern.waketime"
        assert new_value is None
        assert new_size == 0
        assert ctypes.cast(size, ctypes.POINTER(ctypes.c_size_t)).contents.value == ctypes.sizeof(macos._Timeval)
        value = ctypes.cast(buffer, ctypes.POINTER(macos._Timeval)).contents
        value.seconds = 1234567890
        value.microseconds = 987654
        return 0

    monkeypatch.setattr(macos, "_sysctlbyname", lambda: query)
    assert macos.wake_time() == (1234567890, 987654)


def test_wake_time_reports_native_query_failure(monkeypatch):
    def query(*_args):
        ctypes.set_errno(errno.ENOENT)
        return -1

    monkeypatch.setattr(macos, "_sysctlbyname", lambda: query)
    with pytest.raises(OSError) as error:
        macos.wake_time()
    assert error.value.errno == errno.ENOENT
    assert error.value.filename == "kern.waketime"
