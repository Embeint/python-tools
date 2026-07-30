#!/usr/bin/env python3

import os
import pathlib
import subprocess
import sys

import pytest

import infuse_iot.credentials as cred
from infuse_iot.app.main import InfuseApp

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

    custom_tools_path = pathlib.Path(__file__).parent.parent / "scripts" / "custom_tools"

    subprocess.check_output(["infuse", "credentials", "--custom-tools", str(custom_tools_path)])

    output = subprocess.check_output(["infuse", "custom_tool", "--echo", echo_string]).decode()
    assert echo_string in output

    cred.delete_custom_tool_path()

    with pytest.raises(subprocess.CalledProcessError):
        subprocess.check_output(["infuse", "custom_tool", "--echo", echo_string])


def test_custom_tool_path_requires_registry(tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.check_output(["infuse", "credentials", "--custom-tools", str(tmp_path)])


def test_extension_tool_registry_loading():
    custom_tools_path = pathlib.Path(__file__).parent.parent / "scripts" / "custom_tools"

    try:
        cred.set_custom_tool_path(str(custom_tools_path))
        sys.modules.pop("infuse_iot_custom_tools.custom_tool", None)

        app = InfuseApp()

        assert "custom_tool" in app._tools
        assert app._tools["custom_tool"].spec.module == "custom_tool"
        assert "custom_tool" not in app._loaded_tools
        assert "infuse_iot_custom_tools.custom_tool" not in sys.modules

        app._load_selected_tool(["custom_tool", "--echo", "test_string"])

        assert "custom_tool" in app._loaded_tools
    finally:
        cred.delete_custom_tool_path()
