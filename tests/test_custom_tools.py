#!/usr/bin/env python3

import os
import pathlib
import subprocess
import sys

import pytest

import infuse_iot.credentials as cred
from infuse_iot.app.main import InfuseApp
from infuse_iot.commands import wrapper_from_command_id
from infuse_iot.tools.registry import RpcWrapperSpec, load_extension_rpc_wrappers, load_extension_tools
from infuse_iot.util.argparse import InfuseDeviceId, infuse_device_id_to_vendor

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def test_custom_tool_integration(tmp_path):
    # Validate custom tool integration
    echo_string = "test_string"
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")

    try:
        cred.delete_custom_tool_path()
    except Exception as _:
        pass

    with pytest.raises(subprocess.CalledProcessError):
        subprocess.check_output(["infuse", "custom_tool", "--echo", echo_string], env=env)

    custom_tools_path = pathlib.Path(__file__).parent.parent / "scripts" / "custom_tools"

    subprocess.check_output(["infuse", "credentials", "--custom-tools", str(custom_tools_path)], env=env)

    output = subprocess.check_output(["infuse", "custom_tool", "--echo", echo_string], env=env).decode()
    assert echo_string in output

    cred.delete_custom_tool_path()

    with pytest.raises(subprocess.CalledProcessError):
        subprocess.check_output(["infuse", "custom_tool", "--echo", echo_string], env=env)


def test_custom_tool_path_requires_registry(tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        subprocess.check_output(["infuse", "credentials", "--custom-tools", str(tmp_path)])


def test_extension_tool_registry_loading(tmp_path, monkeypatch):
    custom_tools_path = pathlib.Path(__file__).parent.parent / "scripts" / "custom_tools"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    try:
        cred.set_custom_tool_path(str(custom_tools_path))
        sys.modules.pop("infuse_iot_custom_tools.custom_tool", None)

        app = InfuseApp()

        assert "custom_tool" in app._tools
        assert InfuseDeviceId("custom-1234abcd") == 0x1234ABCD
        assert infuse_device_id_to_vendor(0x1234ABCD) == "custom-1234abcd"
        assert infuse_device_id_to_vendor(-1) is None
        assert infuse_device_id_to_vendor(0x12341234ABCD) is None
        assert app._tools["custom_tool"].spec.module == "custom_tool"
        assert "custom_tool" not in app._loaded_tools
        assert "infuse_iot_custom_tools.custom_tool" not in sys.modules

        app._load_selected_tool(["custom_tool", "--echo", "test_string"])

        assert "custom_tool" in app._loaded_tools
        assert wrapper_from_command_id(0xABCD).NAME == "custom_rpc"

        app._load_selected_tool(["rpc", "--gateway", "custom_rpc"])
    finally:
        cred.delete_custom_tool_path()


def test_extension_rpc_wrapper_registry_loading_without_tools(tmp_path):
    registry = tmp_path / "registry.py"
    registry.write_text(
        "\n".join(
            [
                "from infuse_iot.tools.registry import RpcWrapperSpec",
                "RPC_WRAPPERS = (RpcWrapperSpec(name='custom_rpc', module='custom_rpc'),)",
            ]
        )
    )
    (tmp_path / "custom_rpc.py").write_text("class custom_rpc: pass\n")

    assert load_extension_tools(tmp_path) == ()
    assert load_extension_rpc_wrappers(tmp_path) == (RpcWrapperSpec(name="custom_rpc", module="custom_rpc"),)
