#!/usr/bin/env python3

import os
import subprocess
import sys

import pytest

from infuse_iot.cpatch import ValidationError, cpatch

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def apply_generated_patch(tmp_path, original: bytes, expected: bytes) -> bytes:
    original_file = tmp_path / "original.bin"
    new_file = tmp_path / "new.bin"
    patch_file = tmp_path / "update.cpatch"
    output_file = tmp_path / "output.bin"

    original_file.write_bytes(original)
    new_file.write_bytes(expected)

    subprocess.run(
        [sys.executable, "-m", "infuse_iot.cpatch", "generate", original_file, new_file, patch_file],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [sys.executable, "-m", "infuse_iot.cpatch", "patch", original_file, patch_file, output_file],
        check=True,
        stdout=subprocess.DEVNULL,
    )

    return output_file.read_bytes()


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        pytest.param(bytes(range(64)), bytes(range(64)), id="unchanged"),
        pytest.param(bytes(range(64)), bytes(range(16)) + b"HELLO" + bytes(range(21, 64)), id="rewrite"),
        pytest.param(bytes(range(64)), bytes(range(64)) + b"TAIL", id="append"),
        pytest.param(bytes(range(64)), bytes(range(16)) + bytes(range(24, 64)), id="delete"),
        pytest.param(b"abcdefgh" * 8 + b"ijklmnop" * 8, b"ijklmnop" * 8 + b"abcdefgh" * 8, id="reuse"),
    ],
)
def test_cli_generates_patch_that_reconstructs_expected_output(tmp_path, original, expected):
    assert apply_generated_patch(tmp_path, original, expected) == expected


def test_patch_rejects_wrong_original_contents():
    original = bytes(range(64))
    expected = bytes(range(16)) + b"HELLO" + bytes(range(21, 64))
    patch = cpatch.generate(original, expected, verbose=False)

    with pytest.raises(ValidationError, match="Original file CRC"):
        cpatch.patch(bytes(reversed(original)), patch)


def test_validation_patch_reconstructs_original():
    original = bytes(range(256)) * 5
    patch = cpatch.validation(original, invalid_length=False, invalid_crc=False)

    assert cpatch.patch(original, patch) == original


@pytest.mark.parametrize(
    ("invalid_length", "invalid_crc", "message"),
    [
        pytest.param(True, False, "length does not match", id="invalid-length"),
        pytest.param(False, True, "CRC does not match", id="invalid-crc"),
    ],
)
def test_validation_patch_can_generate_invalid_output_metadata(invalid_length, invalid_crc, message):
    original = bytes(range(256)) * 5
    patch = cpatch.validation(original, invalid_length=invalid_length, invalid_crc=invalid_crc)

    with pytest.raises(ValidationError, match=message):
        cpatch.patch(original, patch)
