#!/usr/bin/env python3

import ctypes
import os
import random
import subprocess
import sys

import pytest

from infuse_iot.cpatch import Encoder, ValidationError, cpatch, stream
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
@pytest.mark.parametrize(
    ("delta", "stream_thumb2"), [(False, False), (True, False), (False, True)], ids=["base", "delta", "stream-thumb2"]
)
def test_validation_patch_can_generate_invalid_output_metadata(
    invalid_length, invalid_crc, message, delta, stream_thumb2
):
    original = stream_firmware(0, 0) if stream_thumb2 else validation_original(delta)
    patch = cpatch.validation(
        original, invalid_length=invalid_length, invalid_crc=invalid_crc, delta=delta, stream_thumb2=stream_thumb2
    )

    with pytest.raises(ValidationError, match=message):
        cpatch.patch(original, patch)


@pytest.mark.parametrize(
    ("encoder", "version_major", "version_minor"),
    [
        (Encoder.GREEDY, 1, 0),
        (Encoder.SHORTEST_PATH, 1, 1),
        (Encoder.SHORTEST_PATH_DELTA, 2, 0),
        (Encoder.STREAM_THUMB2, 3, 0),
    ],
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


def test_stream_elements_round_trip():
    elements = [
        stream.Element(0, stream.Add(0)),
        stream.Element(14, stream.Add(stream.HISTORY_SIZE - 1)),
        stream.Element(15, stream.AddExplicit(0x1234)),
        stream.Element(142, stream.Literal(b"\x01")),
        stream.Element(143, stream.Literal(b"\x01\x02")),
        stream.Element(1 << 20, stream.Literal(b"\x07" * 300)),
        stream.Element(3, stream.Shift(-64)),
        stream.Element(0, stream.Shift(1 << 30)),
        stream.Element(0, stream.LiteralShift(b"\x05", 63)),
        stream.Element(2, stream.LiteralShift(b"\x09" * 200, -(1 << 20))),
        stream.Element(1, stream.NoOp()),
    ]
    for element in elements:
        data = bytes(element)
        assert len(data) == len(element)
        assert stream.Element.from_bytes(data, 0) == (element, len(data))
    preamble = stream.Preamble(
        stream.FLAG_BRANCH | stream.FLAG_POINTER,
        0x0801_0000,
        [(0x10, -5), (0x1000, 0x7F_FFFF), (0xFF_FFFF, -0x80_0000)],
        [stream.Region(0x2000_0000, 0x4_0000, [(0x100, 8)])],
    )
    data = stream.encode(preamble, elements)
    assert len(bytes(preamble)) == len(preamble)
    assert stream.decode(data) == (preamble, elements)


def test_stream_history_move_to_front():
    history = stream.History()
    assert history.use(2, 0) == 2
    assert history.deltas[:3] == [2, 1, 0xFFFF]
    assert history.use(None, 0x1234) == 0x1234
    assert history.deltas[0] == 0x1234
    assert history.use(stream.HISTORY_SIZE - 1, 0) == 5


def stream_firmware(inserted: int, ram_shift: int) -> bytes:
    """Functions that call each other, with literal pools of pointers to functions and RAM
    variables. `inserted` bytes of new code are placed before function 40."""
    func_len, base = 256, 0x1_0000
    rng = random.Random(11)
    bodies = [bytearray(rng.getrandbits(8) for _ in range(func_len)) for _ in range(100)]

    def start(f: int) -> int:
        return f * func_len + (inserted if f >= 40 else 0)

    image = bytearray()
    for f, body in enumerate(bodies):
        if f == 40:
            image += b"\xa5" * inserted
        body = bytearray(body)
        for i in range(4):
            # Call to another function
            at = start(f) + 16 + 32 * i
            encoded = stream.thumb_branch_encode(0xF800, start((f * 7 + i) % 100) - (at + 4))
            assert encoded is not None
            body[16 + 32 * i : 20 + 32 * i] = encoded[0].to_bytes(2, "little") + encoded[1].to_bytes(2, "little")
            # Pointers to a function and a RAM variable
            function = base + start((f * 3 + i) % 100) + 1
            variable = 0x2000_0000 + (f * 4 + i) * 8 + (ram_shift if f >= 50 else 0)
            body[128 + 8 * i : 132 + 8 * i] = function.to_bytes(4, "little")
            body[132 + 8 * i : 136 + 8 * i] = variable.to_bytes(4, "little")
        image += body
    return bytes(image)


def test_stream_thumb2_encoder_relocates_moved_code():
    original, expected = stream_firmware(0, 0), stream_firmware(100, 16)
    patch = cpatch.generate(original, expected, verbose=False, encoder=Encoder.STREAM_THUMB2)
    meta, _ = cpatch._patch_load(patch)
    preamble = meta["preamble"]

    assert preamble.flags == stream.FLAG_BRANCH | stream.FLAG_POINTER
    assert preamble.base == 0x1_0000
    assert len(preamble.regions) == 1
    assert cpatch.patch(original, patch) == expected
    # Without relocation every moved call and pointer needs an addition
    assert len(patch) - ctypes.sizeof(cpatch.PatchHeader) < 400


def test_thumb_branches_round_trip():
    rng = random.Random(7)
    for _ in range(10_000):
        offset = rng.randrange(-(1 << 24), 1 << 24) & ~1
        for h2_original in (0xF800, 0x9000):
            encoded = stream.thumb_branch_encode(h2_original, offset)
            assert encoded is not None
            assert stream.thumb_branch_offset(*encoded) == offset
    assert stream.thumb_branch_encode(0xF800, 0) == (0xF000, 0xF800)
    assert stream.thumb_branch_encode(0xF800, 1 << 24) is None


def test_validation_patch_stream_thumb2_runs_every_operation_and_relocation():
    original = stream_firmware(0, 0)
    patch = cpatch.validation(original, invalid_length=False, invalid_crc=False, stream_thumb2=True)
    meta, elements = cpatch._patch_load(patch)

    assert cpatch.patch(original, patch) == original
    assert meta["version"] == (cpatch.PatchHeader.VERSION_MAJOR_STREAM_THUMB2, 0)
    assert all(count > 0 for _, count in stream.op_counts(elements))
    assert {e.op.index for e in elements if isinstance(e.op, stream.Add)} == set(range(stream.HISTORY_SIZE))
    assert {e.copy for e in elements} >= {*range(1, 16), 142, 143}
    preamble = meta["preamble"]
    assert preamble.flags == stream.FLAG_BRANCH | stream.FLAG_POINTER
    assert any(shift for _, shift in preamble.map)
    assert any(shift for region in preamble.regions for _, shift in region.map)
    # Sites are relocated by non-zero shifts, so appliers that do not relocate fail
    assert stream.apply(original, stream.Preamble(), elements) != original
