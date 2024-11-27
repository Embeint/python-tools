import os
import time

from infuse_iot.util.threading import SignaledThread

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


count = 0


def dummy_work():
    global count
    count += 1
    time.sleep(0.1)


def test_signaled_thread():
    t = SignaledThread(dummy_work)
    t.start()
    assert t.is_alive()
    time.sleep(1.0)
    assert t.is_alive()
    t.stop()
    t.join(0.5)
    assert not t.is_alive()
    assert 10 <= count <= 11
