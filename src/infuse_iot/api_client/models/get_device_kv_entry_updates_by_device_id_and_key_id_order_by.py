from enum import Enum


class GetDeviceKVEntryUpdatesByDeviceIDAndKeyIDOrderBy(str, Enum):
    CREATEDAT = "createdAt"
    LASTATTEMPTAT = "lastAttemptAt"
    LASTERROR = "lastError"
    STATUS = "status"
    UPDATEDAT = "updatedAt"

    def __str__(self) -> str:
        return str(self.value)
