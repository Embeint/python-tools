from enum import Enum


class GetDiffsByOrganisationIdAndApplicationIdAndReleaseIdOrderBy(str, Enum):
    CREATEDAT = "createdAt"
    FROMAPPLICATIONID = "fromApplicationId"
    FROMRELEASEID = "fromReleaseId"
    UPDATEDAT = "updatedAt"

    def __str__(self) -> str:
        return str(self.value)
