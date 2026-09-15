#!/usr/bin/env python3

import json
import os
import subprocess
from pathlib import Path

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def test_profile_configure_and_list(tmp_path):
    config_root = tmp_path / "config"
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(config_root)

    output = subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env).decode()
    assert "Created profile test" in output

    store_path = Path(config_root) / "infuse-iot" / "profiles.json"
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)

    assert profiles["active_profile"] == "test"
    assert list(profiles["profiles"]) == ["test"]
    assert list(profiles["profiles"]["test"]) == ["creation_time"]

    output = subprocess.check_output(["infuse", "profile", "list"], env=env).decode()
    assert "test" in output
    assert "yes" in output
    assert profiles["profiles"]["test"]["creation_time"] in output


def test_profile_configure_existing_updates(tmp_path):
    env = os.environ.copy()
    config_root = tmp_path / "config"
    env["XDG_CONFIG_HOME"] = str(config_root)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)
    output = subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env).decode()

    assert "Updated profile test" in output

    store_path = Path(config_root) / "infuse-iot" / "profiles.json"
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)
    assert list(profiles["profiles"]) == ["test"]


def test_profile_set_active(tmp_path):
    config_root = tmp_path / "config"
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(config_root)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)
    output = subprocess.check_output(["infuse", "profile", "set", "--name", "test"], env=env).decode()
    assert "Active profile set to test" in output

    store_path = Path(config_root) / "infuse-iot" / "profiles.json"
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)
    assert profiles["active_profile"] == "test"
    assert list(profiles["profiles"]) == ["test"]

    output = subprocess.check_output(["infuse", "profile", "list"], env=env).decode()
    assert "test" in output
    assert "yes" in output


def test_profile_configure_does_not_replace_active_profile(tmp_path):
    config_root = tmp_path / "config"
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(config_root)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "first"], env=env)
    subprocess.check_output(["infuse", "profile", "configure", "--name", "second"], env=env)

    store_path = Path(config_root) / "infuse-iot" / "profiles.json"
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)

    assert profiles["active_profile"] == "first"
    assert sorted(profiles["profiles"]) == ["first", "second"]


def test_profile_set_missing_errors(tmp_path):
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")

    result = subprocess.run(
        ["infuse", "profile", "set", "--name", "test"],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "profile does not exist: test" in result.stderr


def test_profile_dump(tmp_path):
    config_root = tmp_path / "config"
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(config_root)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)
    subprocess.check_output(["infuse", "profile", "set", "--name", "test"], env=env)

    output = subprocess.check_output(["infuse", "profile", "dump"], env=env).decode().strip()

    assert output.startswith('{\n  "active_profile": "test",\n  "profiles": {\n    "test": {\n      "creation_time": "')
    assert "\n" in output
    assert json.loads(output)["active_profile"] == "test"


def test_profile_dump_empty(tmp_path):
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")

    output = subprocess.check_output(["infuse", "profile", "dump"], env=env).decode().strip()

    assert output == "No profiles configured"
