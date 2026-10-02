#!/usr/bin/env python3

import os
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import infuse_iot.version
from infuse_iot.app.main import InfuseApp
from infuse_iot.tools.registry import ToolSpec

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


@pytest.mark.parametrize("error", [None, RuntimeError("failed"), KeyboardInterrupt()])
def test_app_closes_command_on_every_exit(monkeypatch, error):
    tool = Mock()
    tool.run.side_effect = error

    class TestCommand:
        @classmethod
        def add_parser(cls, _parser):
            pass

        def __new__(cls, _args):
            return tool

    app = InfuseApp()
    app._register_tool(ToolSpec("test", "Test command", "Test command", "test_module"))
    monkeypatch.setattr(app, "_import_tool_module", lambda _: SimpleNamespace(SubCommand=TestCommand))
    if error is None:
        app.run(["test"])
    else:
        with pytest.raises(type(error)):
            app.run(["test"])
    tool.close.assert_called_once()


def test_main():
    # A quick check that the package can be executed as a module which
    # takes arguments, using e.g. "python3 -m west --version" to
    # produce the same results as "west --version", and that both are
    # sane (i.e. the actual version number is printed instead of
    # simply an error message to stderr).

    output_as_module = subprocess.check_output([sys.executable, "-m", "infuse_iot", "--version"]).decode()
    output_directly = subprocess.check_output(["infuse", "--version"]).decode()
    assert infuse_iot.version.__version__ in output_as_module
    assert output_as_module == output_directly
