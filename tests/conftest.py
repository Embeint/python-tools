"""Reject test runs that could access a user's credential store."""

import os
from pathlib import Path

import keyring
import pytest


def pytest_sessionstart():
    test_root = os.environ.get("TOXTEMPDIR")
    if not test_root or os.environ.get("PYTHON_KEYRING_BACKEND") != "keyrings.alt.file.PlaintextKeyring":
        raise pytest.UsageError("Run these tests using tox to isolate credential storage")
    backend = keyring.get_keyring()
    keyring_path = getattr(backend, "file_path", None)
    if keyring_path is None or not Path(keyring_path).resolve().is_relative_to(Path(test_root).resolve()):
        raise pytest.UsageError("Test keyring must be stored inside TOXTEMPDIR")
