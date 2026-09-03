#!/usr/bin/env python3

import os
import subprocess
import sys

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
    command_line = "infuse credentials --api"
    monkeypatch.setenv("COMP_LINE", command_line)
    monkeypatch.setenv("COMP_POINT", str(len(command_line)))
    monkeypatch.setenv("_ARGCOMPLETE", "1")

    app = InfuseApp()
    assert "infuse_iot.tools.credentials" not in sys.modules

    app._load_selected_completion_tool()
    assert "infuse_iot.tools.credentials" in sys.modules
