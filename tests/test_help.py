#!/usr/bin/env python3

import os
import subprocess
import sys

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def test_help():
    # A quick check that the package can be executed as a module which
    # takes arguments, using e.g. "python3 -m west --version" to
    # produce the same results as "west --version", and that both are
    # sane (i.e. the actual version number is printed instead of
    # simply an error message to stderr).

    subprocess.check_output([sys.executable, "-m", "infuse_iot", "--help"])
    subprocess.check_output(["infuse", "--help"])


def test_completion_loads_selected_tool(monkeypatch):
    from infuse_iot.app.main import InfuseApp

    command_line = "infuse credentials --api"
    monkeypatch.setenv("COMP_LINE", command_line)
    monkeypatch.setenv("COMP_POINT", str(len(command_line)))
    monkeypatch.setenv("_ARGCOMPLETE", "1")

    app = InfuseApp()
    assert "infuse_iot.tools.credentials" not in sys.modules

    app._load_selected_completion_tool()
    assert "infuse_iot.tools.credentials" in sys.modules
