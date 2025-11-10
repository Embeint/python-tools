#!/usr/bin/env

import ctypes
from abc import ABCMeta, abstractmethod


class ProvisioningInterface(metaclass=ABCMeta):
    "Generic SoC provisioning interface"

    class DefaultProvisioningStruct(ctypes.LittleEndianStructure):
        _fields_ = [
            ("device_id", ctypes.c_uint64),
        ]
        _pack_ = 1

    @property
    @abstractmethod
    def soc_name(self) -> str:
        "Infuse-IoT SoC name"

    @property
    @abstractmethod
    def unique_device_id_len(self) -> int:
        "Length of the unique device ID in bytes"

    @abstractmethod
    def unique_device_id(self) -> int:
        """Read unique device ID"""

    @abstractmethod
    def read_provisioned_data(self, num: int) -> bytes:
        """Read currently provisioned data from device"""

    @abstractmethod
    def write_provisioning_data(self, data: bytes):
        """Write provisioning data to device"""

    @abstractmethod
    def close(self) -> None:
        "Close any interfaces opened"
