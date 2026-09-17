from enum import Enum


class GetRPCsOrderBy(str, Enum):
    COMMANDID = "commandId"
    COMPLETEDAT = "completedAt"
    CREATEDAT = "createdAt"
    DEVICEID = "deviceId"
    EXPIRESAT = "expiresAt"
    SENTAT = "sentAt"
    STATUS = "status"
    UPDATEDAT = "updatedAt"

    def __str__(self) -> str:
        return str(self.value)
