"""Inspect bounded Infuse releases without flashing devices or running archive contents."""

import binascii
import ctypes
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from infuse_iot.cpatch import cpatch
from infuse_iot.services.device_operations import DeviceError
from infuse_iot.util.release import ota_image_paths, ota_images

VERSION = re.compile(r"\d+\.\d+\.\d+\+[0-9a-f]{8}")
APPLICATION = re.compile(r"0x[0-9a-fA-F]{8}")
DIGEST = re.compile(r"[0-9a-f]{64}")
# The default names of `tempfile` files and directories
TEMPORARY = re.compile(r"tmp[a-z0-9_]{8}")
MCUBOOT_MAGIC = bytes.fromhex("77c295f360d2ef7f3552500f2cb67980")
MAX_FILE = 8 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
ARCHIVE_SECONDS = 120
CACHE_SECONDS = 24 * 3600


def _bounded_read(path: Path, root: Path, maximum: int = MAX_FILE) -> bytes:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file() or resolved.stat().st_size > maximum:
        raise ValueError("Release file escapes its root or exceeds its size limit")
    with resolved.open("rb") as file:
        value = file.read(maximum + 1)
    if len(value) > maximum:
        raise ValueError("Release file exceeds its size limit")
    return value


def _remove(path: Path) -> None:
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError:
        pass


def prune_cache(directory: Path, pattern: re.Pattern, keep: Path | None, max_entries: int) -> None:
    """Remove cache entries unused for a day, or beyond the newest `max_entries` once an hour old

    Temporary files left by interrupted staging or plan writes are removed once an hour old.
    """
    entries, abandoned = [], []
    now = time.time()
    for path in directory.iterdir():
        if path == keep:
            continue
        try:
            modified = path.stat().st_mtime
        except OSError:
            continue
        if pattern.fullmatch(path.name):
            entries.append((modified, path))
        elif TEMPORARY.fullmatch(path.name) and now - modified > 3600:
            abandoned.append(path)
    for index, (modified, path) in enumerate(sorted(entries, reverse=True)):
        if now - modified > CACHE_SECONDS or (index >= max_entries and now - modified > 3600):
            _remove(path)
    for path in abandoned:
        _remove(path)


def _check_cancelled(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise DeviceError("cancelled", "Release inspection was cancelled", True)


def _extract_output(
    arguments: list[str], maximum: int, deadline: float, cancel: threading.Event | None = None
) -> bytes:
    # -so streams a single member into memory; no archive paths are written to disk.
    _check_cancelled(cancel)
    remaining = min(30, deadline - time.monotonic())
    if remaining <= 0:
        raise ValueError("Archive inspection exceeded its time limit")
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=errors)
        finished = threading.Event()

        def watch():
            # Stop the extractor at its time limit, or once the caller cancels.
            stop = time.monotonic() + remaining
            while not finished.wait(0.05):
                if time.monotonic() >= stop or (cancel is not None and cancel.is_set()):
                    process.kill()
                    return

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        chunks, length = [], 0
        try:
            assert process.stdout is not None
            while chunk := process.stdout.read(65536):
                length += len(chunk)
                if length > maximum:
                    raise ValueError("Archive output exceeds its limit")
                chunks.append(chunk)
            if process.wait() != 0:
                _check_cancelled(cancel)
                raise ValueError("Archive could not be read within its time and format limits")
            _check_cancelled(cancel)
            return b"".join(chunks)
        finally:
            finished.set()
            watcher.join()
            if process.poll() is None:
                process.kill()
            process.wait()
            if process.stdout is not None:
                process.stdout.close()


def _archive_members(
    source: Path, cancel: threading.Event | None = None
) -> tuple[str, list[str], Callable[..., bytes]]:
    executable = shutil.which("7zz") or shutil.which("7z") or shutil.which("7za")
    if executable is None:
        raise ValueError("missing_extractor: install 7-Zip or supply an extracted release directory")
    if source.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Archive exceeds 64 MiB")
    deadline = time.monotonic() + ARCHIVE_SECONDS
    arguments = [executable, "l", "-slt", "-ba", "--", str(source)]
    try:
        listing = _extract_output(arguments, 1024 * 1024, deadline, cancel).decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Archive member names are not valid UTF-8") from error
    names, total = [], 0
    for block in listing.replace("\r\n", "\n").strip().split("\n\n"):
        values = dict(line.split(" = ", 1) for line in block.splitlines() if " = " in line)
        name = values.get("Path")
        if not name:
            continue
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or "\x00" in name:
            raise ValueError("Unsafe archive member path")
        try:
            length = int(values.get("Size") or "0")
        except ValueError:
            length = -1
        if length < 0:
            raise ValueError("Invalid archive member size")
        total += length
        names.append(name)
    if len(set(names)) != len(names):
        raise ValueError("Duplicate archive member")
    if len(names) > 1024 or total > MAX_TOTAL:
        raise ValueError("Archive exceeds entry or expansion limits")
    manifests = [name for name in names if PurePosixPath(name).name == "manifest.yaml"]
    if len(manifests) != 1:
        raise ValueError("Archive must contain exactly one release manifest")
    prefix = str(PurePosixPath(manifests[0]).parent)
    prefix = "" if prefix == "." else prefix + "/"

    def read(member: str, maximum: int = MAX_FILE) -> bytes:
        full = prefix + member
        if full not in names:
            raise ValueError(f"Missing release member: {member}")
        arguments = [executable, "x", "-so", "-spd", "-bd", "--", str(source), full]
        return _extract_output(arguments, maximum, deadline, cancel)

    return prefix, names, read


def inspect_image(image: bytes, public_key: Path | None = None) -> dict:
    if len(image) < 32:
        raise ValueError("Truncated MCUboot image")
    magic, _load, header, protected, size, flags, major, minor, revision, build = struct.unpack_from(
        "<IIHHIIBBHI", image
    )
    if magic != 0x96F3B83D or header < 32 or size == 0:
        raise ValueError("Unsupported MCUboot application image")
    if flags:
        # Encrypted, compressed, RAM-load and ROM-fixed images need handling that host checks cannot verify.
        raise ValueError(f"Unsupported MCUboot image flags 0x{flags:08x}; only plain application images are accepted")
    offset = header + size + protected
    if offset + 4 > len(image):
        raise ValueError("Truncated MCUboot image data")
    if protected:
        protected_magic, protected_length = struct.unpack_from("<HH", image, header + size)
        if protected_magic != 0x6908 or protected_length != protected:
            raise ValueError("Invalid protected MCUboot TLV area")
    tlv_magic, length = struct.unpack_from("<HH", image, offset)
    end = offset + length
    if tlv_magic != 0x6907 or length < 4 or end > len(image):
        raise ValueError("Invalid MCUboot TLV area")
    # `imgtool sign --pad` fills the slot with erased flash, ending in the boot trailer magic. Accept only
    # that, so unsigned bytes cannot set image state, as `--confirm` does.
    trailer = image[end:].removesuffix(MCUBOOT_MAGIC)
    if trailer.strip(b"\xff") and trailer.strip(b"\x00"):
        raise ValueError("Bytes after the MCUboot TLV area are not erased padding")
    cursor, tlvs = offset + 4, {}
    while cursor < end:
        if cursor + 4 > end:
            raise ValueError("Truncated TLV header")
        kind, count = struct.unpack_from("<HH", image, cursor)
        cursor += 4
        if cursor + count > end or kind in tlvs:
            raise ValueError("Truncated or duplicate MCUboot TLV")
        tlvs[kind] = image[cursor : cursor + count]
        cursor += count
    if tlvs.get(0x10) != hashlib.sha256(image[:offset]).digest():
        raise ValueError("MCUboot image digest mismatch")
    signatures = {kind: value for kind, value in tlvs.items() if kind in (0x20, 0x22, 0x23, 0x24)}
    if not signatures:
        raise ValueError("Application image has no signature")
    status = "present_unverified"
    key_hash = None
    if public_key is not None:
        key_bytes = _bounded_read(public_key, public_key.resolve().parent, 16384)
        if len(key_bytes) > 16384:
            raise ValueError("Public key is too large")
        try:
            key = serialization.load_pem_public_key(key_bytes)
        except (ValueError, TypeError, UnsupportedAlgorithm) as error:
            # The library's messages describe the parse failure, not which file failed.
            raise ValueError("Trusted public key is not a supported PEM public key") from error
        if not isinstance(key, rsa.RSAPublicKey) or key.key_size not in (2048, 3072):
            raise ValueError("Host verification currently supports MCUboot RSA-2048 and RSA-3072 public keys")
        signature = signatures.get(0x20 if key.key_size == 2048 else 0x23)
        if signature is None:
            raise ValueError("Image signature does not match the public key algorithm")
        try:
            key.verify(
                signature,
                image[:offset],
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=32),
                hashes.SHA256(),
            )
        except InvalidSignature as error:
            raise ValueError("Image signature verification failed") from error
        key_hash, status = hashlib.sha256(key_bytes).hexdigest(), "verified"
    return {
        "version": f"{major}.{minor}.{revision}+{build:08x}",
        "size_bytes": len(image),
        "sha256": hashlib.sha256(image).hexdigest(),
        "image_digest_verified": True,
        "signature_status": status,
        "trusted_public_key_sha256": key_hash,
    }


def inspect_patch(patch: bytes, target: bytes) -> dict:
    size = ctypes.sizeof(cpatch.PatchHeader)
    if len(patch) < size:
        raise ValueError("Truncated patch header")
    header = cpatch.PatchHeader.from_buffer_copy(patch)
    if header.magic != cpatch.PatchHeader.magic_value:
        raise ValueError("Unsupported patch format")
    # Minor versions only identify the encoder; deployed appliers reject newer major versions
    if header.version_major != cpatch.PatchHeader.VERSION_MAJOR:
        raise ValueError(f"Unsupported patch format version {header.version_major}.{header.version_minor}")
    if binascii.crc32(patch[: size - 4]) != header.header_crc:
        raise ValueError("Patch header CRC mismatch")
    if header.patch_file.length != len(patch) - size or binascii.crc32(patch[size:]) != header.patch_file.crc:
        raise ValueError("Patch payload validation failed")
    if header.constructed_file.length != len(target) or header.constructed_file.crc != binascii.crc32(target):
        raise ValueError("Patch header output does not match the selected signed application image")
    if not 0 < header.original_file.length <= MAX_FILE:
        raise ValueError("Invalid patch source length")
    return {
        "size_bytes": len(patch),
        "sha256": hashlib.sha256(patch).hexdigest(),
        "source_length": header.original_file.length,
        "source_crc32": f"0x{header.original_file.crc:08x}",
    }


def _stage(destination: Path, files: dict[str, bytes]) -> None:
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staging = Path(temporary) / "release"
        staging.mkdir()
        for name, value in files.items():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        try:
            os.rename(staging, destination)
        except OSError:
            if not destination.is_dir():
                raise


def _staged(destination: Path, file_hashes: dict[str, str]) -> bool:
    try:
        return all(
            hashlib.sha256(_bounded_read(destination / name, destination)).hexdigest() == expected
            for name, expected in file_hashes.items()
        )
    except (OSError, ValueError):
        return False


def _discard(destination: Path) -> None:
    # Move the entry aside first, so it is never used again while partly deleted.
    discarded = Path(tempfile.mkdtemp(dir=destination.parent))
    try:
        os.rename(destination, discarded / "release")
    except OSError:
        pass  # Already replaced, or held open; checked again by the caller.
    shutil.rmtree(discarded, ignore_errors=True)


def inspect_release(
    source: Path, cache: Path, trusted_public_key: Path | None = None, cancel: threading.Event | None = None
) -> dict:
    """Inspect and stage a release; setting `cancel` stops it with a `cancelled` `DeviceError`"""
    source = source.resolve(strict=True)
    names: list[str] | None
    if source.is_dir():
        root = source

        def read(member: str, maximum: int = MAX_FILE) -> bytes:
            _check_cancelled(cancel)
            return _bounded_read(root / member, root, maximum)

        names = None
    elif source.is_file() and source.suffix.lower() == ".7z":
        prefix, archived, read = _archive_members(source, cancel)
        names = [name[len(prefix) :] for name in archived if name.startswith(prefix)]
    else:
        raise ValueError("Supply an Infuse release directory or .7z archive")
    manifest_bytes = read("manifest.yaml", 65536)
    try:
        manifest = yaml.safe_load(manifest_bytes)
    except (yaml.YAMLError, RecursionError) as error:
        raise ValueError("Release manifest is not valid YAML") from error
    if not isinstance(manifest, dict) or not isinstance(manifest.get("application"), dict):
        raise ValueError("Release must contain an application manifest")
    application = manifest["application"]
    primary, version, board = application.get("primary"), application.get("version"), application.get("board")
    if (
        not isinstance(primary, str)
        or not isinstance(version, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", primary)
        or not VERSION.fullmatch(version)
    ):
        raise ValueError("Invalid application name or version")
    if not isinstance(board, str) or not 1 <= len(board) <= 128:
        raise ValueError("Invalid application board")
    application_id = application.get("id")
    if not isinstance(application_id, int) or not 0 <= application_id < 2**32:
        raise ValueError("Invalid application ID")
    if names is None:
        images, _ = ota_image_paths(root, primary)
        diffs = root / "diffs"
        names = [path.relative_to(root).as_posix() for path in (*diffs.glob("*.bin"), *diffs.glob("*/*.bin"))]
    else:
        images, _ = ota_images(names, primary)
    # The same image the cloud upload selects; release diffs are generated against it.
    if len(images) != 1:
        raise ValueError(
            f"Release must contain exactly one OTA image (ota-*.bin, or {primary}/zephyr/"
            f"tfm_s_zephyr_ns_signed.bin or zephyr.signed.bin), found {len(images)}"
        )
    image_name = images[0]
    image = read(image_name)
    image_info = inspect_image(image, trusted_public_key)
    if image_info["version"] != version:
        raise ValueError("Manifest version does not match signed image")
    files = {"manifest.yaml": manifest_bytes, image_name: image}
    own_application = f"0x{application_id:08x}"
    patches: dict[str, dict[str, Any]] = {}
    migration_patches: dict[str, dict[str, dict[str, Any]]] = {}
    ignored = []
    rejected: list[dict[str, str]] = []
    for name in sorted(names):
        path = PurePosixPath(name)
        if path.parts[:1] != ("diffs",) or path.suffix != ".bin" or len(path.parts) not in (2, 3):
            continue
        source_application = own_application if len(path.parts) == 2 else path.parts[1].lower()
        # Like the cloud upload, skip files that are not named after a source version (e.g. `._*` metadata).
        if (
            not VERSION.fullmatch(path.stem)
            or not APPLICATION.fullmatch(source_application)
            or (len(path.parts) == 3 and source_application == own_application)
        ):
            ignored.append(name)
            continue
        if len(patches) + sum(map(len, migration_patches.values())) + len(rejected) >= 256:
            raise ValueError("Too many release patches")
        patch = read(name)
        try:
            details = {**inspect_patch(patch, image), "file": name}
        except ValueError as error:
            # A stale or damaged diff is only unavailable itself; its devices are planned without it.
            rejected.append(
                {
                    "file": name,
                    "source_application_id": source_application,
                    "source_version": path.stem,
                    "reason": str(error),
                }
            )
            continue
        if source_application == own_application:
            patches[path.stem] = details
        else:
            migration_patches.setdefault(source_application, {})[path.stem] = details
        files[name] = patch
        if sum(map(len, files.values())) > MAX_TOTAL:
            raise ValueError("Release exceeds total file limit")
    _check_cancelled(cancel)
    file_hashes = {name: hashlib.sha256(value).hexdigest() for name, value in files.items()}
    package_hash = hashlib.sha256(json.dumps(file_hashes, sort_keys=True).encode()).hexdigest()
    destination = cache / "packages" / package_hash
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    for attempt in range(2):
        if not destination.exists():
            _stage(destination, files)
        if _staged(destination, file_hashes):
            break
        if attempt:
            raise ValueError("Cached release package is damaged and could not be replaced")
        # Partly deleted, for example by an interrupted prune, or modified: stage it again from the release.
        _discard(destination)
    os.utime(destination)
    prune_cache(destination.parent, DIGEST, destination, 16)
    return {
        "source": str(source),
        "package_sha256": package_hash,
        "staged_directory": str(destination),
        "application_id": own_application,
        "board": board,
        "version": version,
        "image": {**image_info, "file": image_name},
        "patches": patches,
        "migration_patches": migration_patches,
        "rejected_patches": rejected,
        "ignored_files": ignored[:64],
        "file_hashes": file_hashes,
        "trusted_public_key": str(trusted_public_key.resolve()) if trusted_public_key else None,
    }
