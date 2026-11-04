#!/usr/bin/env python3

"""Locate the OTA image of an Infuse-IoT release"""

from collections.abc import Iterable
from fnmatch import fnmatchcase
from pathlib import Path

OTA_IMAGE_PATTERN = "ota-*.bin"


def legacy_ota_images(primary: str) -> tuple[str, ...]:
    """Signed images of the primary application, in preference order, for releases without `ota-*.bin`"""
    return (f"{primary}/zephyr/tfm_s_zephyr_ns_signed.bin", f"{primary}/zephyr/zephyr.signed.bin")


def ota_images(members: Iterable[str], primary: str) -> tuple[list[str], bool]:
    """Select OTA image candidates from release-relative POSIX paths

    Returns the candidates and whether they come from a legacy release layout.
    """
    names = set(members)
    current = sorted(name for name in names if "/" not in name and fnmatchcase(name, OTA_IMAGE_PATTERN))
    if current:
        return current, False
    return [name for name in legacy_ota_images(primary) if name in names][:1], True


def ota_image_paths(directory: Path, primary: str) -> tuple[list[str], bool]:
    """`ota_images` for an extracted release directory"""
    members = [path.name for path in directory.glob(OTA_IMAGE_PATTERN) if path.is_file()]
    members += [name for name in legacy_ota_images(primary) if (directory / name).is_file()]
    return ota_images(members, primary)
