#!/usr/bin/env python3

import json
import os
import pathlib
import subprocess
from collections.abc import Mapping
from pathlib import Path
from unittest.mock import patch

import platformdirs

import infuse_iot.credentials as cred

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def profile_test_env(tmp_path, monkeypatch=None) -> dict[str, str]:
    config_root = tmp_path / "config"
    env = os.environ.copy()
    updates = {
        "XDG_CONFIG_HOME": str(config_root),
        "APPDATA": str(config_root),
        "LOCALAPPDATA": str(config_root),
        "WIN_PD_OVERRIDE_APPDATA": str(config_root),
        "WIN_PD_OVERRIDE_LOCAL_APPDATA": str(config_root),
    }
    for name in updates:
        for existing_name in list(env):
            if existing_name.upper() == name:
                del env[existing_name]
    env.update(updates)
    if monkeypatch is not None:
        for name, value in updates.items():
            monkeypatch.setenv(name, value)
    return env


def profile_store_path(env: Mapping[str, str]) -> Path:
    with patch.dict(os.environ, env, clear=True):
        return Path(platformdirs.user_config_dir("infuse-iot", "Embeint")) / "profiles.json"


def test_profile_configure_and_list(tmp_path):
    env = profile_test_env(tmp_path)

    output = subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env).decode()
    assert "Created profile test" in output

    store_path = profile_store_path(env)
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
    env = profile_test_env(tmp_path)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)
    output = subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env).decode()

    assert "Updated profile test" in output

    store_path = profile_store_path(env)
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)
    assert list(profiles["profiles"]) == ["test"]


def test_profile_configure_with_custom_paths(tmp_path):
    custom_tools_path = pathlib.Path(__file__).parent.parent / "scripts" / "custom_tools"
    custom_definitions_path = tmp_path / "definitions"
    custom_definitions_path.mkdir()
    env = profile_test_env(tmp_path)

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

    store_path = profile_store_path(env)
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)

    assert profiles["profiles"]["test"]["custom_tools"] == str(custom_tools_path.absolute())
    assert profiles["profiles"]["test"]["custom_definitions"] == str(custom_definitions_path.absolute())

    output = subprocess.check_output(["infuse", "profile", "list"], env=env).decode()
    assert str(custom_tools_path.absolute()) in output
    assert str(custom_definitions_path.absolute()) in output


def test_profile_configure_with_api_key(tmp_path, monkeypatch):
    env = profile_test_env(tmp_path, monkeypatch)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test", "--api-key", "profile-key"], env=env)

    store_path = profile_store_path(env)
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)

    api_key_id = profiles["profiles"]["test"]["api_key_id"]
    assert api_key_id is not None
    assert api_key_id != "profile-key"
    assert cred.get_profile_api_key(api_key_id) == "profile-key"
    assert cred.get_api_key() == "profile-key"


def test_profile_set_active(tmp_path):
    env = profile_test_env(tmp_path)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)
    output = subprocess.check_output(["infuse", "profile", "set", "--name", "test"], env=env).decode()
    assert "Active profile set to test" in output

    store_path = profile_store_path(env)
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)
    assert profiles["active_profile"] == "test"
    assert list(profiles["profiles"]) == ["test"]

    output = subprocess.check_output(["infuse", "profile", "list"], env=env).decode()
    assert "test" in output
    assert "yes" in output


def test_profile_configure_updates_custom_paths(tmp_path):
    custom_tools_path = pathlib.Path(__file__).parent.parent / "scripts" / "custom_tools"
    custom_definitions_path = tmp_path / "definitions"
    custom_definitions_path.mkdir()
    env = profile_test_env(tmp_path)

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

    store_path = profile_store_path(env)
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)

    assert profiles["profiles"]["test"]["custom_tools"] == str(custom_tools_path.absolute())
    assert profiles["profiles"]["test"]["custom_definitions"] == str(custom_definitions_path.absolute())


def test_profile_configure_updates_api_key(tmp_path, monkeypatch):
    env = profile_test_env(tmp_path, monkeypatch)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test", "--api-key", "first-key"], env=env)
    store_path = profile_store_path(env)
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
    env = profile_test_env(tmp_path, monkeypatch)

    try:
        cred.set_api_key("legacy-key")
        subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)

        assert cred.get_api_key() == "legacy-key"
    finally:
        cred.delete_api_key()


def test_profile_custom_tools_are_loaded(tmp_path):
    custom_tools_path = pathlib.Path(__file__).parent.parent / "scripts" / "custom_tools"
    env = profile_test_env(tmp_path)

    subprocess.check_output(
        ["infuse", "profile", "configure", "--name", "test", "--custom-tools", str(custom_tools_path)],
        env=env,
    )

    output = subprocess.check_output(["infuse", "custom_tool", "--echo", "test_string"], env=env).decode()

    assert "test_string" in output


def test_profile_configure_does_not_replace_active_profile(tmp_path):
    env = profile_test_env(tmp_path)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "first"], env=env)
    subprocess.check_output(["infuse", "profile", "configure", "--name", "second"], env=env)

    store_path = profile_store_path(env)
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)

    assert profiles["active_profile"] == "first"
    assert sorted(profiles["profiles"]) == ["first", "second"]


def test_profile_set_missing_errors(tmp_path):
    env = profile_test_env(tmp_path)

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
    env = profile_test_env(tmp_path)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)
    subprocess.check_output(["infuse", "profile", "set", "--name", "test"], env=env)

    output = subprocess.check_output(["infuse", "profile", "dump"], env=env).decode().strip()

    assert "\n" in output
    dumped_profiles = json.loads(output)
    assert dumped_profiles["active_profile"] == "test"
    assert dumped_profiles["profiles"]["test"]["api_key_id"] is None
    assert "creation_time" in dumped_profiles["profiles"]["test"]


def test_profile_dump_empty(tmp_path):
    env = profile_test_env(tmp_path)

    output = subprocess.check_output(["infuse", "profile", "dump"], env=env).decode().strip()

    assert output == "No profiles configured"


def banner_probe(env) -> subprocess.CompletedProcess:
    """Run a command that is not 'infuse profile', which never prints the banner"""
    return subprocess.run(
        ["infuse", "credentials", "--api-key-print"],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )


def test_profile_banner_disabled_by_default(tmp_path):
    env = profile_test_env(tmp_path)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)

    assert "[profile: test]" not in banner_probe(env).stderr


def test_profile_banner_not_shown_for_profile_commands(tmp_path):
    env = profile_test_env(tmp_path)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)
    subprocess.check_output(["infuse", "profile", "banner", "--enable"], env=env)

    result = subprocess.run(
        ["infuse", "profile", "list"],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )

    assert "[profile: test]" not in result.stderr


def test_profile_banner_enable_and_disable(tmp_path):
    env = profile_test_env(tmp_path)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)

    output = subprocess.check_output(["infuse", "profile", "banner", "--enable"], env=env).decode()
    assert "Banner enabled for profile test" in output

    store_path = profile_store_path(env)
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)
    assert profiles["profiles"]["test"]["banner"] is True

    assert "[profile: test]" in banner_probe(env).stderr

    output = subprocess.check_output(["infuse", "profile", "banner", "--disable"], env=env).decode()
    assert "Banner disabled for profile test" in output

    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)
    assert profiles["profiles"]["test"]["banner"] is False


def test_profile_banner_survives_configure(tmp_path):
    env = profile_test_env(tmp_path)

    subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)
    subprocess.check_output(["infuse", "profile", "banner", "--enable"], env=env)
    subprocess.check_output(["infuse", "profile", "configure", "--name", "test"], env=env)

    store_path = profile_store_path(env)
    with store_path.open("r", encoding="utf-8") as f:
        profiles = json.load(f)

    assert profiles["profiles"]["test"]["banner"] is True


def test_profile_banner_without_active_profile_errors(tmp_path):
    env = profile_test_env(tmp_path)

    result = subprocess.run(
        ["infuse", "profile", "banner", "--enable"],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 1
    assert "no active profile" in result.stderr
