#!/usr/bin/env python3

import json
import os
import pathlib
import subprocess
from pathlib import Path

import infuse_iot.credentials as cred

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
    assert profiles["profiles"]["test"]["api_key_id"] is None
    assert profiles["profiles"]["test"]["custom_definitions"] is None
    assert profiles["profiles"]["test"]["custom_tools"] is None
    assert "creation_time" in profiles["profiles"]["test"]

    output = subprocess.check_output(["infuse", "profile", "list"], env=env).decode()
    assert "test" in output
    assert "yes" in output
    assert profiles["profiles"]["test"]["creation_time"] not in output


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


def test_profile_configure_with_custom_paths(tmp_path):
    config_root = tmp_path / "config"
    custom_tools_path = pathlib.Path(__file__).parent.parent / "scripts" / "custom_tools"
    custom_definitions_path = tmp_path / "definitions"
    custom_definitions_path.mkdir()
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(config_root)

    subprocess.check_output(
        [
            "infuse",
            "profile",
            "configure",
            "--name",
            "test",
            "--custom-tools",
            str(custom_tools_path),
            "--custom-definitions",
            str(custom_definitions_path),
        ],
        env=env,
    )

    store_path = Path(config_root) / "infuse-iot" / "profiles.json"
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)

    assert profiles["profiles"]["test"]["custom_tools"] == str(custom_tools_path.absolute())
    assert profiles["profiles"]["test"]["custom_definitions"] == str(custom_definitions_path.absolute())

    output = subprocess.check_output(["infuse", "profile", "list"], env=env).decode()
    assert str(custom_tools_path.absolute()) in output
    assert str(custom_definitions_path.absolute()) in output


def test_profile_configure_with_api_key(tmp_path, monkeypatch):
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    monkeypatch.setenv("XDG_CONFIG_HOME", env["XDG_CONFIG_HOME"])

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test", "--api-key", "profile-key"], env=env)

    store_path = Path(env["XDG_CONFIG_HOME"]) / "infuse-iot" / "profiles.json"
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)

    api_key_id = profiles["profiles"]["test"]["api_key_id"]
    assert api_key_id is not None
    assert api_key_id != "profile-key"
    assert cred.get_profile_api_key(api_key_id) == "profile-key"
    assert cred.get_api_key() == "profile-key"


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


def test_profile_configure_updates_custom_paths(tmp_path):
    config_root = tmp_path / "config"
    custom_tools_path = pathlib.Path(__file__).parent.parent / "scripts" / "custom_tools"
    custom_definitions_path = tmp_path / "definitions"
    custom_definitions_path.mkdir()
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(config_root)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)
    subprocess.check_output(
        [
            "infuse",
            "profile",
            "configure",
            "--name",
            "test",
            "--custom-tools",
            str(custom_tools_path),
            "--custom-definitions",
            str(custom_definitions_path),
        ],
        env=env,
    )

    store_path = Path(config_root) / "infuse-iot" / "profiles.json"
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)

    assert profiles["profiles"]["test"]["custom_tools"] == str(custom_tools_path.absolute())
    assert profiles["profiles"]["test"]["custom_definitions"] == str(custom_definitions_path.absolute())


def test_profile_configure_updates_api_key(tmp_path, monkeypatch):
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    monkeypatch.setenv("XDG_CONFIG_HOME", env["XDG_CONFIG_HOME"])

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test", "--api-key", "first-key"], env=env)
    store_path = Path(env["XDG_CONFIG_HOME"]) / "infuse-iot" / "profiles.json"
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)
    first_api_key_id = profiles["profiles"]["test"]["api_key_id"]

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test", "--api-key", "second-key"], env=env)

    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)

    api_key_id = profiles["profiles"]["test"]["api_key_id"]
    assert api_key_id == first_api_key_id
    assert cred.get_profile_api_key(api_key_id) == "second-key"
    assert cred.get_api_key() == "second-key"


def test_profile_without_api_key_uses_legacy_credentials(tmp_path, monkeypatch):
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    monkeypatch.setenv("XDG_CONFIG_HOME", env["XDG_CONFIG_HOME"])

    try:
        cred.set_api_key("legacy-key")
        subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)

        assert cred.get_api_key() == "legacy-key"
    finally:
        cred.delete_api_key()


def test_profile_custom_tools_are_loaded(tmp_path):
    custom_tools_path = pathlib.Path(__file__).parent.parent / "scripts" / "custom_tools"
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")

    subprocess.check_output(
        ["infuse", "profile", "configure", "--name", "test", "--custom-tools", str(custom_tools_path)],
        env=env,
    )

    output = subprocess.check_output(["infuse", "custom_tool", "--echo", "test_string"], env=env).decode()

    assert "test_string" in output


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

    assert "\n" in output
    dumped_profiles = json.loads(output)
    assert dumped_profiles["active_profile"] == "test"
    assert dumped_profiles["profiles"]["test"]["api_key_id"] is None
    assert "creation_time" in dumped_profiles["profiles"]["test"]


def test_profile_dump_empty(tmp_path):
    env = os.environ.copy()
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")

    output = subprocess.check_output(["infuse", "profile", "dump"], env=env).decode().strip()

    assert output == "No profiles configured"
