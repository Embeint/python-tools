from enum import Enum


class DeviceMetadataUpdateOperation(str, Enum):
    PATCH = "patch"
    REPLACE = "replace"

    def __str__(self) -> str:
        return str(self.value)
