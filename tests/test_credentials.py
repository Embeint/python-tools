#!/usr/bin/env python3

import os
import subprocess

import pytest

import infuse_iot.credentials as cred

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def _run_credentials(*args):
    return subprocess.run(
        ["infuse", "credentials", *args],
        check=True,
        capture_output=True,
        text=True,
    )


def test_credentials():
    # Validate the credentials API

    try:
        cred.delete_api_key()
    except Exception as _:
        pass

    with pytest.raises(FileNotFoundError):
        cred.get_api_key()

    test_api_key = "ABCDEFGHIJKLMNOP"
    test_api_key_2 = "ABCDEFGHIJKLMNOP123456"

    output = subprocess.check_output(["infuse", "credentials", "--api-key-print"]).decode()
    assert "API Key: N/A" in output

    subprocess.check_output(["infuse", "credentials", "--api-key", test_api_key]).decode()
    assert test_api_key == cred.get_api_key()

    output = subprocess.check_output(["infuse", "credentials", "--api-key-print"]).decode()
    assert test_api_key in output

    cred.set_api_key(test_api_key_2)

    output = subprocess.check_output(["infuse", "credentials", "--api-key-print"]).decode()
    assert test_api_key_2 in output

    cred.delete_api_key()

    output = subprocess.check_output(["infuse", "credentials", "--api-key-print"]).decode()
    assert "API Key: N/A" in output


def test_credentials_deprecated_messages(tmp_path):
    custom_tools_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "custom_tools")
    custom_definitions_path = tmp_path / "definitions"
    custom_definitions_path.mkdir()

    cases = [
        (("--api-key", "ABCDEFGHIJKLMNOP"), "--api-key"),
        (("--api-key-print",), "--api-key-print"),
        (("--custom-tools", custom_tools_path), "--custom-tools"),
        (("--custom-definitions", str(custom_definitions_path)), "--custom-definitions"),
    ]

    for args, option in cases:
        result = _run_credentials(*args)
        assert f"'infuse credentials {option}' is deprecated" in result.stderr


def test_credentials_network_not_deprecated(tmp_path):
    network_path = tmp_path / "network.yaml"
    network_path.write_text("id: 1\nkey: 000102030405060708090a0b0c0d0e0f\n", encoding="utf-8")

    result = _run_credentials("--network", str(network_path))

    assert "deprecated" not in result.stderr
