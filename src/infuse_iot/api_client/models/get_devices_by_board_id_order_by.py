from enum import Enum


class GetDevicesByBoardIdOrderBy(str, Enum):
    BOARDID = "boardId"
    CREATEDAT = "createdAt"
    DEVICEID = "deviceId"
    MCUID = "mcuId"
    ORGANISATIONID = "organisationId"
    UPDATEDAT = "updatedAt"

    def __str__(self) -> str:
        return str(self.value)
