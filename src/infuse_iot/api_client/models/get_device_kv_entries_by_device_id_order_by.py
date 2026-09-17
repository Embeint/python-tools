from enum import Enum


class GetDeviceKVEntriesByDeviceIDOrderBy(str, Enum):
    CREATEDAT = "createdAt"
    KEYID = "keyId"
    UPDATEDAT = "updatedAt"

    def __str__(self) -> str:
        return str(self.value)
