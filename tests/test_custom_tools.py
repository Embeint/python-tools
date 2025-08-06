#!/usr/bin/env python3

import os
import pathlib
import subprocess

import pytest

import infuse_iot.credentials as cred

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def test_custom_tool_integration():
    # Validate custom tool integration
    echo_string = "test_string"

    try:
        cred.delete_custom_tool_path()
    except Exception as _:
        pass

    with pytest.raises(subprocess.CalledProcessError):
        subprocess.check_output(["infuse", "custom_tool", "--echo", echo_string])

    custom_tools_path = pathlib.Path(__file__).parent.parent / 'scripts' / 'custom_tools'

    subprocess.check_output(["infuse", "credentials", "--custom-tools", str(custom_tools_path)])

    output = subprocess.check_output(["infuse", "custom_tool", "--echo", echo_string]).decode()
    assert echo_string in output

    cred.delete_custom_tool_path()

    with pytest.raises(subprocess.CalledProcessError):
        subprocess.check_output(["infuse", "custom_tool", "--echo", echo_string])
