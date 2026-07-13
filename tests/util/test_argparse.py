#!/usr/bin/env python3

import argparse
import os
import pathlib

import pytest

from infuse_iot.util.argparse import (
    BtLeAddress,
    HexString,
    InfuseDeviceId,
    ServerPort,
    ValidDir,
    ValidFile,
    add_server_port_parser,
)

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


def test_infuse_device_id():
    with pytest.raises(argparse.ArgumentTypeError):
        InfuseDeviceId("NotHex")
    with pytest.raises(argparse.ArgumentTypeError):
        InfuseDeviceId("aabb::00")
    assert InfuseDeviceId("0x00aa") == 0xAA
    assert InfuseDeviceId("00aa") == 0xAA
    assert InfuseDeviceId("0x99") == 0x99
    assert InfuseDeviceId("99") == 0x99
    assert InfuseDeviceId("0x1234aa43bc") == 0x1234AA43BC
    assert InfuseDeviceId("1234aa43bc") == 0x1234AA43BC


def test_hexstring():
    with pytest.raises(argparse.ArgumentTypeError):
        HexString("NotHex")
    with pytest.raises(argparse.ArgumentTypeError):
        HexString("aa:bb::00")
    with pytest.raises(argparse.ArgumentTypeError):
        HexString("0xaa")
    assert HexString("aabb") == b"\xaa\xbb"
    assert HexString("AABB") == b"\xaa\xbb"
    assert HexString("aa00bb") == b"\xaa\x00\xbb"
    assert HexString("00AABB") == b"\x00\xaa\xbb"

def test_server_port():
    with pytest.raises(argparse.ArgumentTypeError):
        ServerPort("NotAnInt")
    with pytest.raises(argparse.ArgumentTypeError):
        ServerPort("-1")
    with pytest.raises(argparse.ArgumentTypeError):
        ServerPort("65536")
    with pytest.raises(argparse.ArgumentError):
        # Must be odd
        ServerPort("2")
    with pytest.raises(argparse.ArgumentTypeError):
        # Cannot be wildcard port
        ServerPort("0")
    assert ServerPort("1") == ("224.1.1.1", 1)
    assert ServerPort("8751") == ("224.1.1.1", 8751)
    assert ServerPort("65535") == ("224.1.1.1", 65535)

def test_server_port_parser(capsys):
    parser = argparse.ArgumentParser()
    add_server_port_parser(parser)

    args = parser.parse_args([])
    assert args.server_sock == ("224.1.1.1", 8751)
    args = parser.parse_args(["--server-port", "8751"])
    assert args.server_sock == ("224.1.1.1", 8751)
    args = parser.parse_args(["--server-port", "8753"])
    assert args.server_sock == ("224.1.1.1", 8753)
    with pytest.raises(SystemExit):
        # Additional port supplied when not supported
        args = parser.parse_args(["--server-port", "8751", "8753"])

    parser = argparse.ArgumentParser()
    add_server_port_parser(parser, multi_port=True)

    args = parser.parse_args([])
    assert args.server_sock == [("224.1.1.1", 8751)]
    args = parser.parse_args(["--server-port", "8751"])
    assert args.server_sock == [("224.1.1.1", 8751)]
    args = parser.parse_args(["--server-port", "8753"])
    assert args.server_sock == [("224.1.1.1", 8753)]
    args = parser.parse_args(["--server-port", "8751", "8753"])
    assert args.server_sock == [("224.1.1.1", 8751), ("224.1.1.1", 8753)]
