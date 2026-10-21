"""Offline release package inspection and caching."""

import hashlib
import os
import shutil
import struct
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from infuse_iot.cpatch import Encoder, cpatch
from infuse_iot.services.device_operations import DeviceError
from infuse_iot.services.release_package import (
    DIGEST,
    MCUBOOT_MAGIC,
    _extract_output,
    inspect_image,
    inspect_release,
    prune_cache,
)

APP = 0xCE710003
TARGET = "1.3.1+7bee09d5"
PREVIOUS = "1.3.0+f715affe"


def tlv(kind, value):
    return struct.pack("<HH", kind, len(value)) + value


def image_for(payload=b"example application" * 8, flags=0, signature=0x20, extra=b""):
    header = struct.pack("<IIHHIIBBHI", 0x96F3B83D, 0, 32, 0, len(payload), flags, 1, 3, 1, 0x7BEE09D5)
    signed = header + bytes(4) + payload
    # Inspection without a trusted key only requires a signature TLV to be present.
    tlvs = tlv(0x10, hashlib.sha256(signed).digest()) + extra
    if signature is not None:
        tlvs += tlv(signature, bytes(256))
    return signed + struct.pack("<HH", 0x6907, 4 + len(tlvs)) + tlvs


def make_release(tmp_path, image=None):
    root = tmp_path / "release"
    image = image or image_for()
    image_path = root / "logger/zephyr/zephyr.signed.bin"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(image)
    (root / "manifest.yaml").write_text(
        f"application:\n  primary: logger\n  id: {APP}\n  board: sr2202/nrf52840\n  version: {TARGET}\n",
        encoding="utf-8",
    )
    (root / "diffs").mkdir()
    patch = cpatch.generate(b"previous application" * 12, image, False)
    (root / "diffs" / f"{PREVIOUS}.bin").write_bytes(patch)
    return SimpleNamespace(root=root, image=image, image_path=image_path, patch=patch)


@pytest.fixture
def release(tmp_path):
    return make_release(tmp_path)


@pytest.mark.parametrize("damage", ["deleted_file", "modified_file", "empty_directory"])
def test_damaged_cache_entry_is_staged_again_from_the_release(release, tmp_path, damage):
    cache = tmp_path / "cache"
    staged = Path(inspect_release(release.root, cache)["staged_directory"])
    image = staged / "logger/zephyr/zephyr.signed.bin"
    if damage == "deleted_file":
        # For example a prune that failed halfway through removing the entry
        image.unlink()
    elif damage == "modified_file":
        image.write_bytes(b"modified")
    else:
        shutil.rmtree(staged)
        staged.mkdir()
    package = inspect_release(release.root, cache)
    assert package["staged_directory"] == str(staged)
    assert image.read_bytes() == release.image
    assert (staged / f"diffs/{PREVIOUS}.bin").read_bytes() == release.patch
    # The damaged entry is not left behind under another name.
    assert sorted(path.name for path in staged.parent.iterdir()) == [staged.name]


def test_abandoned_temporary_files_are_pruned_once_an_hour_old(tmp_path):
    old, recent = time.time() - 2 * 3600, time.time() - 60
    staging, plan, fresh = tmp_path / "tmpab_c1234", tmp_path / "tmpzz9_8765", tmp_path / "tmp12345678"
    (staging / "release").mkdir(parents=True)
    plan.write_text("{}")
    fresh.mkdir()
    other = tmp_path / "notes.txt"
    other.write_text("kept")
    for path in (staging, plan, other):
        os.utime(path, (old, old))
    os.utime(fresh, (recent, recent))
    prune_cache(tmp_path, DIGEST, None, 16)
    assert sorted(path.name for path in tmp_path.iterdir()) == ["notes.txt", "tmp12345678"]


@pytest.mark.parametrize(
    "manifest",
    [b"application: [unclosed", b"application:\n  primary: \x80\x81", b"[" * 5000, b"a: !!python/object:os.system x"],
)
def test_malformed_manifest_is_an_invalid_release(release, tmp_path, manifest):
    (release.root / "manifest.yaml").write_bytes(manifest)
    with pytest.raises(ValueError, match="^Release manifest is not valid YAML$"):
        inspect_release(release.root, tmp_path / "cache")


@pytest.mark.parametrize("key", [b"not a key", b"-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----\n"])
def test_unparseable_trusted_key_is_an_invalid_release(release, tmp_path, key):
    path = tmp_path / "trusted.pem"
    path.write_bytes(key)
    with pytest.raises(ValueError, match="^Trusted public key is not a supported PEM public key$"):
        inspect_release(release.root, tmp_path / "cache", path)


@pytest.mark.parametrize(
    "listing,error",
    [(b"Path = \xff.yaml\nSize = 1", "not valid UTF-8"), (b"Path = manifest.yaml\nSize = many", "member size")],
)
def test_unparseable_archive_listing_is_an_invalid_release(tmp_path, monkeypatch, listing, error):
    archive = tmp_path / "release.7z"
    archive.write_bytes(b"placeholder")
    monkeypatch.setattr("infuse_iot.services.release_package.shutil.which", lambda _: "7zz")
    monkeypatch.setattr("infuse_iot.services.release_package._extract_output", lambda *args: listing)
    with pytest.raises(ValueError, match=error) as raised:
        inspect_release(archive, tmp_path / "cache")
    assert "many" not in str(raised.value) and "\\x" not in str(raised.value)


@pytest.mark.parametrize("trailer", [b"\xff" * 4000 + MCUBOOT_MAGIC, b"\xff" * 61, b"\x00" * 64])
def test_padded_images_are_accepted(tmp_path, trailer):
    release = make_release(tmp_path, image_for() + trailer)
    package = inspect_release(release.root, tmp_path / "cache")
    assert package["image"]["size_bytes"] == len(release.image)
    # Diffs construct the padded file.
    assert PREVIOUS in package["patches"]


@pytest.mark.parametrize("trailer", [b"\xff" * 60 + b"\x01" + b"\xff" * 3 + MCUBOOT_MAGIC, b"unsigned"])
def test_unsigned_bytes_after_the_tlv_area_are_rejected(trailer):
    with pytest.raises(ValueError, match="not erased padding"):
        inspect_image(image_for() + trailer)


def test_vendor_tlvs_are_not_mistaken_for_digests_or_signatures():
    # `imgtool --custom-tlv` types share their low byte with the digest and RSA-2048 signature types.
    signed = inspect_image(image_for(extra=tlv(0xA010, b"vendor")))
    assert (signed["image_digest_verified"], signed["signature_status"]) == (True, "present_unverified")
    with pytest.raises(ValueError, match="no signature"):
        inspect_image(image_for(signature=None, extra=tlv(0xA020, bytes(256))))


@pytest.mark.parametrize("flags", [0x4, 0x20, 0x100])
def test_flagged_images_are_rejected(tmp_path, flags):
    # Encrypted, RAM-load and ROM-fixed images
    release = make_release(tmp_path, image_for(flags=flags))
    with pytest.raises(ValueError, match=f"image flags 0x{flags:08x}"):
        inspect_release(release.root, tmp_path / "cache")


def test_stale_diff_is_rejected_without_rejecting_the_release(release, tmp_path):
    stale = cpatch.generate(b"previous application" * 12, image_for(b"older build" * 8), False)
    (release.root / "diffs" / "1.2.0+17bf41bf.bin").write_bytes(stale)
    migration = release.root / "diffs" / "0xCE710004" / "1.0.0+0000abcd.bin"
    migration.parent.mkdir()
    migration.write_bytes(b"truncated")
    delta = cpatch.generate(b"previous application" * 12, release.image, False, Encoder.SHORTEST_PATH_DELTA)
    (release.root / "diffs" / "1.1.0+0000beef.bin").write_bytes(delta)
    package = inspect_release(release.root, tmp_path / "cache")
    assert list(package["patches"]) == [PREVIOUS] and package["migration_patches"] == {}
    assert package["rejected_patches"] == [
        {
            "file": "diffs/0xCE710004/1.0.0+0000abcd.bin",
            "source_application_id": "0xce710004",
            "source_version": "1.0.0+0000abcd",
            "reason": "Truncated patch header",
        },
        {
            "file": "diffs/1.1.0+0000beef.bin",
            "source_application_id": f"0x{APP:08x}",
            "source_version": "1.1.0+0000beef",
            "reason": "Unsupported patch format version 2.0",
        },
        {
            "file": "diffs/1.2.0+17bf41bf.bin",
            "source_application_id": f"0x{APP:08x}",
            "source_version": "1.2.0+17bf41bf",
            "reason": "Patch header output does not match the selected signed application image",
        },
    ]
    # Rejected diffs are not staged.
    assert sorted(package["file_hashes"]) == [
        f"diffs/{PREVIOUS}.bin",
        "logger/zephyr/zephyr.signed.bin",
        "manifest.yaml",
    ]


def test_cancel_stops_a_running_extractor():
    cancel = threading.Event()
    threading.Timer(0.2, cancel.set).start()
    started = time.monotonic()
    with pytest.raises(DeviceError) as error:
        # A stand-in for 7-Zip reading a slow archive
        _extract_output([sys.executable, "-c", "import time; time.sleep(30)"], 1024, time.monotonic() + 60, cancel)
    assert (error.value.code, error.value.retryable) == ("cancelled", True)
    assert time.monotonic() - started < 5


def test_cancelled_inspection_stages_nothing(release, tmp_path):
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(DeviceError, match="cancelled"):
        inspect_release(release.root, tmp_path / "cache", cancel=cancel)
    assert not (tmp_path / "cache").exists()
