from enum import Enum


class GetDiffsByOrganisationIdAndApplicationIdOrderBy(str, Enum):
    CREATEDAT = "createdAt"
    FROMAPPLICATIONID = "fromApplicationId"
    FROMRELEASEID = "fromReleaseId"
    TORELEASEID = "toReleaseId"
    UPDATEDAT = "updatedAt"

    def __str__(self) -> str:
        return str(self.value)
