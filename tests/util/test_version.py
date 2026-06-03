#!/usr/bin/env python3

import os

import pytest

from infuse_iot.util.version import Version

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def test_version_parsing():
    with pytest.raises(ValueError):
        Version.from_string("random string")
    with pytest.raises(ValueError):
        Version.from_string("1.2.3")
    with pytest.raises(ValueError):
        Version.from_string("1.2+aaaaaaaa")

    def equality(str, major, minor, rev, build):
        from_str = Version.from_string("1.2.3+aaaaaaaa")
        from_int = Version(1, 2, 3, 0xAAAAAAAA)
        assert from_str == from_int
        assert hash(from_str) == hash(from_int)

    equality("1.2.3+aaaaaaaa", 1, 2, 3, 0xAAAAAAAA)
    equality("10.2.3+12345678", 10, 2, 3, 0x12345678)
    equality("1.20.354+50", 1, 20, 354, 0x50)

    def round_trip(string: str):
        assert str(Version.from_string(string)) == string

    round_trip("1.2.3+aaaaaaaa")
    round_trip("10.2.3+12345678")
    round_trip("2.20.1+00000aaa")
