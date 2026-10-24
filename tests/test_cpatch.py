#!/usr/bin/env python3

import os
import random
import subprocess
import sys

import pytest

from infuse_iot.cpatch import Encoder, ValidationError, cpatch
from infuse_iot.cpatch.instructions import Instr, PatchDeltaInstr

assert "TOXTEMPDIR" in os.environ, "you must run these tests using tox"


def apply_generated_patch(tmp_path, original: bytes, expected: bytes, encoder: Encoder) -> bytes:
    original_file = tmp_path / "original.bin"
    new_file = tmp_path / "new.bin"
    patch_file = tmp_path / "update.cpatch"
    output_file = tmp_path / "output.bin"

    original_file.write_bytes(original)
    new_file.write_bytes(expected)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "infuse_iot.cpatch",
            "generate",
            "--encoder",
            encoder.value,
            original_file,
            new_file,
            patch_file,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        [sys.executable, "-m", "infuse_iot.cpatch", "patch", original_file, patch_file, output_file],
        check=True,
        stdout=subprocess.DEVNULL,
    )

    return output_file.read_bytes()


@pytest.mark.parametrize("encoder", list(Encoder), ids=lambda e: e.value)
@pytest.mark.parametrize(
    ("original", "expected"),
    [
        pytest.param(bytes(range(64)), bytes(range(64)), id="unchanged"),
        pytest.param(bytes(range(64)), bytes(range(16)) + b"HELLO" + bytes(range(21, 64)), id="rewrite"),
        pytest.param(bytes(range(64)), bytes(range(64)) + b"TAIL", id="append"),
        pytest.param(bytes(range(64)), bytes(range(16)) + bytes(range(24, 64)), id="delete"),
        pytest.param(b"abcdefgh" * 8 + b"ijklmnop" * 8, b"ijklmnop" * 8 + b"abcdefgh" * 8, id="reuse"),
        pytest.param(b"abc", b"abd", id="tiny"),
        pytest.param(bytes(range(64)) + b"\xff" * 32, bytes(range(64)) + b"\xff" * 1000, id="padding"),
    ],
)
def test_cli_generates_patch_that_reconstructs_expected_output(tmp_path, original, expected, encoder):
    assert apply_generated_patch(tmp_path, original, expected, encoder) == expected


@pytest.mark.parametrize("encoder", list(Encoder), ids=lambda e: e.value)
def test_patch_rejects_wrong_original_contents(encoder):
    original = bytes(range(64))
    expected = bytes(range(16)) + b"HELLO" + bytes(range(21, 64))
    patch = cpatch.generate(original, expected, verbose=False, encoder=encoder)

    with pytest.raises(ValidationError, match="Original file CRC"):
        cpatch.patch(bytes(reversed(original)), patch)


def validation_original(delta: bool) -> bytes:
    if not delta:
        return bytes(range(256)) * 5
    # PATCH_DELTA validation searches the file for values that exercise each history entry
    rng = random.Random(0)
    return bytes(rng.getrandbits(8) for _ in range(16384))


@pytest.mark.parametrize(("delta", "version_major"), [(False, 1), (True, 2)], ids=["base", "delta"])
def test_validation_patch_reconstructs_original(delta, version_major):
    original = validation_original(delta)
    patch = cpatch.validation(original, invalid_length=False, invalid_crc=False, delta=delta)

    assert cpatch.patch(original, patch) == original
    assert cpatch.PatchHeader.from_buffer_copy(patch).version_major == version_major
    _, instructions = cpatch._patch_load(patch)
    assert any(isinstance(instr, PatchDeltaInstr) for instr in instructions) == delta


def test_validation_patch_delta_runs_every_element_type():
    original = validation_original(True)
    patch = cpatch.validation(original, invalid_length=False, invalid_crc=False, delta=True)
    _, instructions = cpatch._patch_load(patch)
    elements = [e for instr in instructions if isinstance(instr, PatchDeltaInstr) for e in instr.elements]

    assert {addition for _, addition, _ in elements} == set(range(16))
    assert {copy_len for copy_len, _, _ in elements} >= {*range(15), PatchDeltaInstr.MAX_COPY}


@pytest.mark.parametrize(
    ("invalid_length", "invalid_crc", "message"),
    [
        pytest.param(True, False, "length does not match", id="invalid-length"),
        pytest.param(False, True, "CRC does not match", id="invalid-crc"),
    ],
)
@pytest.mark.parametrize("delta", [False, True], ids=["base", "delta"])
def test_validation_patch_can_generate_invalid_output_metadata(invalid_length, invalid_crc, message, delta):
    original = validation_original(delta)
    patch = cpatch.validation(original, invalid_length=invalid_length, invalid_crc=invalid_crc, delta=delta)

    with pytest.raises(ValidationError, match=message):
        cpatch.patch(original, patch)


@pytest.mark.parametrize(
    ("encoder", "version_major", "version_minor"),
    [(Encoder.GREEDY, 1, 0), (Encoder.SHORTEST_PATH, 1, 1), (Encoder.SHORTEST_PATH_DELTA, 2, 0)],
)
def test_patch_version_identifies_encoder(encoder, version_major, version_minor):
    original = bytes(range(64))
    expected = bytes(range(16)) + b"HELLO" + bytes(range(21, 64))
    patch = cpatch.generate(original, expected, verbose=False, encoder=encoder)
    header = cpatch.PatchHeader.from_buffer_copy(patch)

    assert header.version_major == version_major
    assert header.version_minor == version_minor


def test_patch_delta_instruction_round_trip():
    elements = [
        (0, PatchDeltaInstr.EXPLICIT, 0x1234),
        (5, 0, 0),
        (14, 13, 0),
        (15, PatchDeltaInstr.NONE, 0),
        (PatchDeltaInstr.MAX_COPY, PatchDeltaInstr.EXPLICIT, 0xFFFF),
    ]
    instr = PatchDeltaInstr(elements)
    data = bytes(instr)
    decoded, length, original_offset = Instr.from_bytes(data, 0, 0)

    assert isinstance(decoded, PatchDeltaInstr)
    assert decoded.elements == elements
    assert length == len(data) == len(instr)
    assert original_offset == sum(c for c, _, _ in elements) + 2 * 4


def test_delta_encoder_encodes_relocated_values():
    rng = random.Random(0)
    original = bytes(rng.getrandbits(8) for _ in range(8192))
    # Halfwords throughout the file change by a small number of deltas
    modified = bytearray(original)
    for offset in range(0, len(modified) - 2, 32):
        val = int.from_bytes(modified[offset : offset + 2], "little")
        delta = (1, 4, 0xFFFC)[offset % 3]
        modified[offset : offset + 2] = ((val + delta) & 0xFFFF).to_bytes(2, "little")
    expected = bytes(modified)

    patch_shortest_path = cpatch.generate(original, expected, verbose=False, encoder=Encoder.SHORTEST_PATH)
    patch_delta = cpatch.generate(original, expected, verbose=False, encoder=Encoder.SHORTEST_PATH_DELTA)

    assert len(patch_delta) < len(patch_shortest_path)
    assert cpatch.patch(original, patch_delta) == expected
