#!/usr/bin/env python3

import importlib
import os
import subprocess
from contextlib import nullcontext
from types import SimpleNamespace
from typing import Any

import pytest

from infuse_iot.api_client.models import Error
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
        attribute = "sync"
    elif resource == "coap":
        argv += ["list"]
        endpoint = module.get_coap_files
        attribute = "sync"
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
    response: Any = SimpleNamespace(filenames=[]) if argv[1] == "coap" else []
    monkeypatch.setattr(endpoint, attribute, lambda *_args, **_kwargs: response)
    InfuseApp().run(argv)


@pytest.mark.parametrize("response", [None, Error(code=503, message="Unavailable")])
def test_cloud_request_failure_exits_nonzero(cloud_list, monkeypatch, response):
    argv, endpoint, attribute = cloud_list
    monkeypatch.setattr(endpoint, attribute, lambda *_args, **_kwargs: response)
    with pytest.raises(SystemExit) as error:
        InfuseApp().run(argv)
    assert isinstance(error.value.code, str)
    assert "No response" in error.value.code if response is None else "503" in error.value.code


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
