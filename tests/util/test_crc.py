import os

import infuse_iot.util.crc as crc

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"

test_string = "123456789"
test_bytes = test_string.encode("utf-8")


def test_crc16_kermit():
    # Check bytes from https://reveng.sourceforge.io/crc-catalogue/all.htm
    # Algorithm: CRC-16/KERMIT
    assert crc.crc16_kermit(test_bytes) == 0x2189


def test_crc16_ccitt():
    # Check bytes from https://reveng.sourceforge.io/crc-catalogue/all.htm
    # Algorithm: CRC-16/KERMIT
    assert crc.crc16_ccitt(test_bytes) == 0x2189
