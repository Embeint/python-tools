#!/usr/bin/env python3

import os
import subprocess

import pytest

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


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
