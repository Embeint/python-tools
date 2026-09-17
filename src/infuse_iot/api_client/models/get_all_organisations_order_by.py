from enum import Enum


class GetAllOrganisationsOrderBy(str, Enum):
    CREATEDAT = "createdAt"
    NAME = "name"
    UPDATEDAT = "updatedAt"

    def __str__(self) -> str:
        return str(self.value)
