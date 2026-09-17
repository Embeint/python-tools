from enum import Enum


class GetDeviceApplicationUpdatesByDeviceIDOrderBy(str, Enum):
    COMPLETEDAT = "completedAt"
    CREATEDAT = "createdAt"
    LASTATTEMPTAT = "lastAttemptAt"
    LASTERROR = "lastError"
    RELEASEID = "releaseId"
    STATUS = "status"
    UPDATEDAT = "updatedAt"

    def __str__(self) -> str:
        return str(self.value)
