#!/usr/bin/env python3

import os
import subprocess

import pytest

import infuse_iot.credentials as cred

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


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
