from enum import Enum


class GetApplicationsByOrganisationIdOrderBy(str, Enum):
    APPLICATIONID = "applicationId"
    CREATEDAT = "createdAt"
    NAME = "name"
    UPDATEDAT = "updatedAt"

    def __str__(self) -> str:
        return str(self.value)
