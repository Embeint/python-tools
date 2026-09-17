from enum import Enum


class GetReleasesByOrganisationIdAndApplicationIdOrderBy(str, Enum):
    BOARDID = "boardId"
    BOARDTARGET = "boardTarget"
    CREATEDAT = "createdAt"
    UPDATEDAT = "updatedAt"
    VERSION = "version"

    def __str__(self) -> str:
        return str(self.value)
