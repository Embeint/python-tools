#!/usr/bin/env python3

import importlib
import os
import subprocess
from contextlib import nullcontext
from http import HTTPStatus
from types import SimpleNamespace
from typing import Any

import pytest

from infuse_iot.api_client.types import Response
from infuse_iot.app.main import InfuseApp
from infuse_iot.tools.cloud_commands.base import CloudSubCommand

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


@pytest.fixture(params=["orgs", "boards", "device", "coap", "apps"])
def cloud_list(request, monkeypatch):
    resource = request.param
    module_name = {
        "orgs": "organisations",
        "apps": "applications",
        "boards": "boards",
        "device": "device",
        "coap": "coap",
    }
    module = importlib.import_module(f"infuse_iot.tools.cloud_commands.{module_name[resource]}")
    argv = ["cloud", resource]
    if resource == "device":
        argv += ["kv_state", "--id", "1"]
        endpoint = module.get_device_kv_entries_by_device_id
        attribute = "sync_detailed"
    elif resource == "coap":
        argv += ["list"]
        endpoint = module.get_coap_files
        attribute = "sync_detailed"
    else:
        argv += ["list"]
        if resource == "apps":
            argv += ["--org", "00000000-0000-0000-0000-000000000001"]
        endpoint = module
        attribute = "fetch_all"
    monkeypatch.setattr(CloudSubCommand, "client", lambda _: nullcontext(None))
    return argv, endpoint, attribute


def test_cloud_resource_dispatch(cloud_list, monkeypatch):
    argv, endpoint, attribute = cloud_list
    parsed: Any = SimpleNamespace(filenames=[]) if argv[1] == "coap" else []
    response = Response(status_code=HTTPStatus.OK, content=b"", headers={}, parsed=parsed)
    monkeypatch.setattr(endpoint, attribute, lambda *_args, **_kwargs: response)
    InfuseApp().run(argv)


def _run_cloud_list(resource: str) -> str:
    api_key = os.environ.get("INFUSE_PLATFORM_TEST_API_KEY")
    if not api_key:
        pytest.skip("INFUSE_PLATFORM_TEST_API_KEY is not set")

    result = subprocess.run(
        ["infuse", "cloud", "--api-key", api_key, resource, "list"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"`infuse cloud {resource} list` failed:\n{result.stderr}", pytrace=False)
    return result.stdout


def test_cloud_orgs_list():
    output = _run_cloud_list("orgs")

    assert len(output.splitlines()) > 2


def test_cloud_boards_list():
    output = _run_cloud_list("boards")

    assert "nRF52840dk" in output


@pytest.mark.parametrize("show_devstate", [False, True])
def test_device_kv_state_preserves_devstate_filter(monkeypatch, capsys, show_devstate):
    from infuse_iot.api_client.types import UNSET
    from infuse_iot.tools.cloud_commands import device

    monkeypatch.setattr(CloudSubCommand, "client", lambda _: nullcontext(None))
    entries = [SimpleNamespace(key_id=1, key_name="Z_DEVSTATE", data="AQ==", decoded=UNSET)]
    response = Response(status_code=HTTPStatus.OK, content=b"", headers={}, parsed=entries)
    monkeypatch.setattr(device.get_device_kv_entries_by_device_id, "sync_detailed", lambda **_kwargs: response)
    argv = ["cloud", "device", "kv_state", "--id", "1", "--hex"]
    if show_devstate:
        argv.append("--devstate")
    InfuseApp().run(argv)
    assert ("Z_DEVSTATE" in capsys.readouterr().out) == show_devstate
