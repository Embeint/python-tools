# Copyright (c) 2020 Teslabs Engineering S.L.
# Copyright (c) 2025 Embeint Inc
#
# SPDX-License-Identifier: Apache-2.0


from pynrfjprog import LowLevel, Parameters

from infuse_iot.util.soc.soc import ProvisioningInterface


class NRFFamily:
    DEVICE_ID_OFFSET: int
    CUSTOMER_OFFSET: int

    @staticmethod
    def soc(device_info):
        raise NotImplementedError


class nRF52840(NRFFamily):
    DEVICE_ID_OFFSET = 0x60
    CUSTOMER_OFFSET = 0x80

    @staticmethod
    def soc(device_info):
        assert device_info[1] == Parameters.DeviceName.NRF52840
        return "nRF52840"


class nRF5340(NRFFamily):
    DEVICE_ID_OFFSET = 0x204
    CUSTOMER_OFFSET = 0x100

    @staticmethod
    def soc(device_info):
        assert device_info[1] == Parameters.DeviceName.NRF5340
        return "nRF5340"


class nRF91(NRFFamily):
    DEVICE_ID_OFFSET = 0x204
    CUSTOMER_OFFSET = 0x108

    @staticmethod
    def soc(device_info):
        if device_info[1] == Parameters.DeviceName.NRF9160:
            return "nRF9160"
        elif device_info[1] == Parameters.DeviceName.NRF9120:
            # Use version to determine nRF9151 vs nRF9161
            if device_info[0] == Parameters.DeviceVersion.NRF9120_xxAA_REV3:
                return "nRF9151"
            else:
                raise NotImplementedError(f"Unknown device: {device_info[0]}")
        else:
            raise NotImplementedError(f"Unknown device {device_info[1]}")


DEVICE_FAMILY_MAPPING: dict[str, type[NRFFamily]] = {
    "NRF52": nRF52840,
    "NRF53": nRF5340,
    "NRF91": nRF91,
}


class Interface(ProvisioningInterface):
    def __init__(self, snr: int | None):
        self._api = LowLevel.API()
        self._api.open()
        if snr is None:
            self._api.connect_to_emu_without_snr()
        else:
            self._api.connect_to_emu_with_snr(snr)
        self._family = DEVICE_FAMILY_MAPPING[self._api.read_device_family()]
        self._device_info = self._api.read_device_info()
        self._soc_name = self._family.soc(self._device_info)

    def close(self):
        self._api.pin_reset()
        self._api.disconnect_from_emu()
        self._api.close()

    def _find_region(self, memory_type: Parameters.MemoryType):
        for desc in self._api.read_memory_descriptors():
            if desc.type == memory_type:
                return desc
        raise RuntimeError(f"Could not find memory region {memory_type}")

    @property
    def soc_name(self) -> str:
        return self._soc_name

    @property
    def unique_device_id_len(self) -> int:
        return 8

    def unique_device_id(self) -> int:
        ficr = self._find_region(Parameters.MemoryType.FICR)
        dev_id_addr = ficr.start + self._family.DEVICE_ID_OFFSET

        dev_id_bytes = bytes(self._api.read(dev_id_addr, 8))
        return int.from_bytes(dev_id_bytes, "big")

    def read_provisioned_data(self, num: int) -> bytes:
        uicr = self._find_region(Parameters.MemoryType.UICR)
        customer_addr = uicr.start + self._family.CUSTOMER_OFFSET

        return bytes(self._api.read(customer_addr, num))

    def write_provisioning_data(self, data: bytes):
        uicr = self._find_region(Parameters.MemoryType.UICR)
        customer_addr = uicr.start + self._family.CUSTOMER_OFFSET

        self._api.write(customer_addr, data, True)
