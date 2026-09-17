from enum import Enum


class GetBoardsOrderBy(str, Enum):
    CREATEDAT = "createdAt"
    NAME = "name"
    PUBLIC = "public"
    UPDATEDAT = "updatedAt"

    def __str__(self) -> str:
        return str(self.value)
