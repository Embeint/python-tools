import argparse
import os
import pathlib

import pytest

from infuse_iot.util.argparse import BtLeAddress, ValidDir, ValidFile

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def test_valid_file():
    test_file = __file__
    test_dir = str(pathlib.Path(test_file).parent)

    with pytest.raises(argparse.ArgumentTypeError):
        ValidFile("random_file_doesnt_exist.txt")
    with pytest.raises(argparse.ArgumentTypeError):
        ValidFile(test_dir)
    parsed = ValidFile(test_file)
    assert isinstance(parsed, pathlib.Path)


def test_valid_directory():
    test_file = __file__
    test_dir = str(pathlib.Path(test_file).parent)

    with pytest.raises(argparse.ArgumentTypeError):
        ValidDir("random_folder_doesnt_exist")
    with pytest.raises(argparse.ArgumentTypeError):
        ValidDir(test_file)
    parsed = ValidDir(test_dir)
    assert isinstance(parsed, pathlib.Path)


def test_bt_le_address():
    with pytest.raises(argparse.ArgumentTypeError):
        BtLeAddress("NotAnAddress")
    with pytest.raises(argparse.ArgumentTypeError):
        BtLeAddress("XX:XX:XX:XX:XX:XX")
    with pytest.raises(argparse.ArgumentTypeError):
        BtLeAddress("12:34:56:aa:FF")
    addr = BtLeAddress("12:34:56:aa:FF:4A")
    assert isinstance(addr, int)
    addr = BtLeAddress("123456aaFF4A")
    assert isinstance(addr, int)
