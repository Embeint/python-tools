#!/usr/bin/env python3
# Copyright (c) 2026 Embeint Holdings Pty Ltd
#
# SPDX-License-Identifier: Apache-2.0

import pylink

from infuse_iot.util.soc.soc import ProvisioningInterface


class SilabsFamily:
    DEVINFO_ADDRESS: int
    USERDATA_ADDRESS: int
    SOC: str

    # Offsets into the DEVINFO block
    PART_OFFSET = 0x04
    MSIZE_OFFSET = 0x0C
    EUI64L_OFFSET = 0x48
    EUI64H_OFFSET = 0x4C

    @classmethod
    def jlink_device(cls, part: int, msize: int) -> str:
        raise NotImplementedError


class EFR32MG24(SilabsFamily):
    DEVINFO_ADDRESS = 0x0FE08000
    USERDATA_ADDRESS = 0x0FE00000
    SOC = "EFR32MG24"

    @classmethod
    def jlink_device(cls, part: int, msize: int) -> str:
        # DEVICE_NUM encodes the part letter as (letter_index * 1000) + number
        device_num = part & 0xFFFF
        letter = chr(ord("A") + (device_num // 1000))
        flash_kb = msize & 0xFFFF
        return f"EFR32MG24{letter}xxxF{flash_kb}"


# Mapping of (DEVINFO_PART.FAMILY, DEVINFO_PART.FAMILYNUM) to family
DEVICE_FAMILY_MAPPING: dict[tuple[int, int], type[SilabsFamily]] = {
    (1, 24): EFR32MG24,
}

# All currently supported Series 2 parts share a common DEVINFO address
_SERIES2_DEVINFO_ADDRESS = 0x0FE08000


class Interface(ProvisioningInterface):
    def _open(self, snr: int):
        self._jlink.open(serial_no=snr)
        # Hide the flash download progress window and other GUI popups.
        # `JLink.disable_dialog_boxes` is not used as it also enables silent firmware updates.
        for cmd in [
            "DisableInfoWinFlashDL",
            "DisableInfoWinFlashBPs",
            "HideDeviceSelection = 1",
            "SuppressControlPanel",
        ]:
            self._jlink.exec_command(cmd)
        self._jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)

    def __init__(self, snr: int | None):
        self._jlink = pylink.JLink()
        emulators = self._jlink.connected_emulators()
        if len(emulators) == 0:
            raise RuntimeError("No J-Link probes found")
        if snr is None:
            if len(emulators) > 1:
                serials = ",".join([str(e.SerialNumber) for e in emulators])
                raise RuntimeError(f"Multiple J-Link probes found without a SNR provided (Found: {serials})")
            snr = emulators[0].SerialNumber
        elif not any(e.SerialNumber == snr for e in emulators):
            raise RuntimeError(f"J-Link probe with SNR {snr} not found")

        self._open(snr)

        # Connect as a generic core to identify the exact part
        self._jlink.connect("Cortex-M33")
        part = self._jlink.memory_read32(_SERIES2_DEVINFO_ADDRESS + SilabsFamily.PART_OFFSET, 1)[0]
        family_key = ((part >> 24) & 0x3F, (part >> 16) & 0x3F)
        if family_key not in DEVICE_FAMILY_MAPPING:
            raise NotImplementedError(f"Unhandled Silicon Labs part (DEVINFO.PART=0x{part:08x})")
        self._family = DEVICE_FAMILY_MAPPING[family_key]
        msize = self._jlink.memory_read32(self._family.DEVINFO_ADDRESS + SilabsFamily.MSIZE_OFFSET, 1)[0]

        # Reconnect with the specific device name so the flash loader is available
        self._jlink.close()
        self._open(snr)
        self._jlink.connect(self._family.jlink_device(part, msize))

    @property
    def soc_name(self) -> str:
        return self._family.SOC

    @property
    def unique_device_id_len(self) -> int:
        return 8

    def unique_device_id(self) -> int:
        """Retrieve the 64 bit EUI64, matching `SYSTEM_GetUnique` and `hwinfo_silabs_series2`"""
        base = self._family.DEVINFO_ADDRESS
        eui64l = self._jlink.memory_read32(base + SilabsFamily.EUI64L_OFFSET, 1)[0]
        eui64h = self._jlink.memory_read32(base + SilabsFamily.EUI64H_OFFSET, 1)[0]
        return (eui64h << 32) | eui64l

    def read_provisioned_data(self, num: int) -> bytes:
        return bytes(self._jlink.memory_read8(self._family.USERDATA_ADDRESS, num))

    def write_provisioning_data(self, data: bytes):
        # Pad to 32bit alignment
        if mod := len(data) % 4:
            data += b"\xff" * (4 - mod)
        # Flash download API handles the page erase and read-modify-write
        self._jlink.flash_write8(self._family.USERDATA_ADDRESS, list(data))
        if self.read_provisioned_data(len(data)) != data:
            raise RuntimeError("USERDATA verification failed")

    def close(self):
        self._jlink.reset(halt=False)
        self._jlink.close()
