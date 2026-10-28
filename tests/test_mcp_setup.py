"""Desktop host registration of the local MCP server."""

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

from infuse_iot.tools import mcp_setup
from infuse_iot.tools.mcp_setup import SubCommand, config_path


@pytest.fixture
def setup(monkeypatch, tmp_path):
    """Run `infuse mcp_setup` with a home directory in `tmp_path` and the MCP extra reported as installed."""
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home / ".config"))
    find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *args: object() if name == "mcp" else find_spec(name, *args)
    )
    monkeypatch.setattr(sys, "version_info", (3, 12, 0, "final", 0))

    def run(*arguments: str) -> None:
        parser = argparse.ArgumentParser()
        SubCommand.add_parser(parser)
        SubCommand(parser.parse_args(list(arguments))).run()

    return run


def test_config_paths_follow_each_platform(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    desktop = Path("Claude") / "claude_desktop_config.json"
    assert config_path("claude-desktop", "darwin", tmp_path) == tmp_path / "Library/Application Support" / desktop
    assert config_path("claude-desktop", "win32", tmp_path) == tmp_path / "Roaming" / desktop
    assert config_path("claude-desktop", "linux", tmp_path) == tmp_path / ".config" / desktop
    assert config_path("cursor", "win32", tmp_path) == tmp_path / ".cursor" / "mcp.json"


def test_registration_keeps_other_servers_and_starts_a_gateway(setup, capsys):
    desktop = config_path("claude-desktop")
    desktop.parent.mkdir(parents=True)
    existing = {"theme": "dark", "mcpServers": {"other": {"command": "other"}}}
    desktop.write_text(json.dumps(existing), encoding="utf-8")

    setup("--client", "claude-desktop", "--client", "cursor")
    config = json.loads(desktop.read_text(encoding="utf-8"))
    assert config["theme"] == "dark" and config["mcpServers"]["other"] == {"command": "other"}
    entry = config["mcpServers"]["infuse"]
    # The host does not search the shell PATH, so the command is absolute
    assert Path(entry["command"]).is_absolute()
    assert entry["args"][entry["args"].index("mcp") :] == [
        "mcp",
        "--server-port",
        "8751",
        "--scan-seconds",
        "20",
        "--start-gateway",
        "native_bt",
    ]
    assert json.loads(desktop.with_name(desktop.name + ".bak").read_text(encoding="utf-8")) == existing
    assert json.loads(config_path("cursor").read_text(encoding="utf-8"))["mcpServers"]["infuse"] == entry
    assert "restart Claude Desktop" in capsys.readouterr().out

    setup("--client", "claude-desktop")
    assert "already up to date" in capsys.readouterr().out

    setup("--client", "claude-desktop", "--remove")
    assert json.loads(desktop.read_text(encoding="utf-8"))["mcpServers"] == {"other": {"command": "other"}}


def test_serial_gateway_and_writes_are_opt_in(setup):
    with pytest.raises(SystemExit, match="--gateway-serial is needed"):
        setup("--client", "cursor", "--start-gateway", "serial")
    setup("--client", "cursor", "--start-gateway", "serial", "--gateway-serial", "COM4", "--allow-writes")
    args = json.loads(config_path("cursor").read_text(encoding="utf-8"))["mcpServers"]["infuse"]["args"]
    assert args[args.index("--start-gateway") :] == [
        "--start-gateway",
        "serial",
        "--gateway-serial",
        "COM4",
        "--gateway-baud",
        "115200",
        "--allow-writes",
    ]


def test_unreadable_config_is_left_unchanged(setup):
    cursor = config_path("cursor")
    cursor.parent.mkdir(parents=True)
    cursor.write_text("{not json", encoding="utf-8")
    with pytest.raises(SystemExit, match="not valid JSON"):
        setup("--client", "cursor")
    assert cursor.read_text(encoding="utf-8") == "{not json"


def test_print_changes_nothing(setup, capsys):
    setup("--print", "--start-gateway", "none")
    printed = json.loads(capsys.readouterr().out)
    assert "--start-gateway" not in printed["mcpServers"]["infuse"]["args"]
    assert not config_path("cursor").exists() and not config_path("claude-desktop").exists()


def test_registration_needs_the_mcp_extra(setup, monkeypatch):
    find_spec = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util, "find_spec", lambda name, *args: None if name == "mcp" else find_spec(name, *args)
    )
    with pytest.raises(SystemExit, match="optional extra"):
        setup("--client", "cursor")
    assert not config_path("cursor").exists()


@pytest.mark.skipif(sys.platform == "win32", reason="Uses a shell script in place of the claude command")
def test_claude_code_registration_replaces_the_user_server(setup, tmp_path, monkeypatch, capsys):
    log = tmp_path / "claude.log"
    claude = tmp_path / "bin" / "claude"
    claude.parent.mkdir()
    claude.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" >> {log}\necho ---- >> {log}\n', encoding="utf-8")
    claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{claude.parent}{os.pathsep}{os.environ['PATH']}")
    # Found without --client, alongside no desktop hosts
    setup()
    remove, add, _ = log.read_text(encoding="utf-8").split("----\n")
    assert remove.split() == ["mcp", "remove", "--scope", "user", "infuse"]
    arguments = add.splitlines()
    assert arguments[:5] == ["mcp", "add-json", "--scope", "user", "infuse"]
    specification = json.loads(arguments[5])
    assert specification["type"] == "stdio" and "--start-gateway" in specification["args"]
    assert "Registered with Claude Code" in capsys.readouterr().out
    assert mcp_setup.shutil.which("claude") == str(claude)
