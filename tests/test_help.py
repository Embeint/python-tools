#!/usr/bin/env python3

import importlib.util
import os
import subprocess
import sys
from argparse import Namespace

import pytest

from infuse_iot.app.main import InfuseApp

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def test_help():
    # A quick check that the package can be executed as a module which
    # takes arguments, using e.g. "python3 -m west --version" to
    # produce the same results as "west --version", and that both are
    # sane (i.e. the actual version number is printed instead of
    # simply an error message to stderr).

    subprocess.check_output([sys.executable, "-m", "infuse_iot", "--help"])
    subprocess.check_output(["infuse", "--help"])


def test_no_subcommand_lists_subcommands():
    output = subprocess.check_output(["infuse"]).decode()

    assert "Available sub commands:" in output
    assert "credentials" in output
    assert "Manage Infuse-IoT credentials" in output


def test_nested_subcommand_lists_subcommands(capsys, monkeypatch):
    monkeypatch.setattr("infuse_iot.app.main.get_custom_tool_path", lambda: None)

    InfuseApp().run(["schedule"])
    output = capsys.readouterr().out
    assert "Available sub commands:" in output
    assert "decode" in output
    assert "Decode a task schedule" in output

    InfuseApp().run(["cloud"])
    output = capsys.readouterr().out
    assert "Available sub commands:" in output
    assert "device" in output
    assert "Infuse-IoT devices" in output

    InfuseApp().run(["cloud", "device"])
    output = capsys.readouterr().out
    assert "Available sub commands:" in output
    assert "kv_state" in output
    assert "Key-Value device state" in output

    InfuseApp().run(["rpc", "--gateway"])
    output = capsys.readouterr().out
    assert "Available sub commands:" in output
    assert "application_info" in output
    assert "Query basic application versions and state" in output

    InfuseApp().run(["rpc_cloud"])
    output = capsys.readouterr().out
    assert "Available sub commands:" in output
    assert "queue" in output
    assert "Queue a RPC to be sent" in output

    InfuseApp().run(["rpc_cloud", "queue", "--id", "1"])
    output = capsys.readouterr().out
    assert "Available sub commands:" in output
    assert "application_info" in output
    assert "Query basic application versions and state" in output


def test_completion_loads_selected_tool(monkeypatch):
    command_line = "infuse profile configure --api"
    monkeypatch.setenv("COMP_LINE", command_line)
    monkeypatch.setenv("COMP_POINT", str(len(command_line)))
    monkeypatch.setenv("_ARGCOMPLETE", "1")

    app = InfuseApp()
    assert "infuse_iot.tools.profile" not in sys.modules

    app._load_selected_completion_tool()
    assert "infuse_iot.tools.profile" in sys.modules


def test_mcp_help_does_not_require_the_optional_sdk():
    output = subprocess.check_output(["infuse", "mcp", "--help"]).decode()
    assert "--transport" in output
    assert "--server-port" in output


def mcp_command():
    from infuse_iot.tools.mcp import SubCommand

    return SubCommand(
        Namespace(server_sock=("127.0.0.1", 1), transport="stdio", allow_writes=False, state_directory=None)
    )


def test_mcp_explains_an_unsupported_python_or_sdk(monkeypatch):
    find_spec = importlib.util.find_spec
    monkeypatch.setattr(sys, "version_info", (3, 10, 14, "final", 0))
    with pytest.raises(SystemExit, match=r"Python 3\.11 or newer, but this is Python 3\.10"):
        mcp_command().run()
    monkeypatch.undo()

    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *args: None if name == "mcp" else find_spec(name, *args)
    )
    with pytest.raises(SystemExit, match=r'optional extra: pip install "infuse-iot\[mcp\]"$'):
        mcp_command().run()
    monkeypatch.undo()

    # An SDK outside the supported range lacks what the server imports
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *args: object() if name == "mcp" else find_spec(name, *args)
    )
    monkeypatch.delitem(sys.modules, "infuse_iot.mcp_server.server", raising=False)
    monkeypatch.setitem(sys.modules, "mcp.server", None)
    with pytest.raises(SystemExit, match=r"needs mcp>=2\.3,<3, but version \S+ is installed"):
        mcp_command().run()


def test_mcp_does_not_blame_the_sdk_for_other_import_failures(monkeypatch):
    pytest.importorskip("mcp")
    monkeypatch.delitem(sys.modules, "infuse_iot.mcp_server.server", raising=False)
    monkeypatch.setitem(sys.modules, "infuse_iot.mcp_server.schemas", None)
    with pytest.raises(ImportError) as failure:
        mcp_command().run()
    assert failure.value.name == "infuse_iot.mcp_server.schemas"
