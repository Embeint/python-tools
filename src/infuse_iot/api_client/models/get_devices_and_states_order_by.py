from enum import Enum


class GetDevicesAndStatesOrderBy(str, Enum):
    BOARDID = "boardId"
    CREATEDAT = "createdAt"
    DEVICEID = "deviceId"
    FIRSTPACKETTIME = "firstPacketTime"
    LASTROUTETIME = "lastRouteTime"
    LASTROUTEUDPTIME = "lastRouteUdpTime"
    MCUID = "mcuId"
    ORGANISATIONID = "organisationId"
    UPDATEDAT = "updatedAt"

    def __str__(self) -> str:
        return str(self.value)
