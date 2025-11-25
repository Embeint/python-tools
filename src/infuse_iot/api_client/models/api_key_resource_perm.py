from enum import Enum


class APIKeyResourcePerm(str, Enum):
    ADMIN = "admin"
    CREATE = "create"
    DELETE = "delete"
    UPDATE = "update"
    VIEW = "view"

    def __str__(self) -> str:
        return str(self.value)
