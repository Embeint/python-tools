from enum import Enum


class APIKeyOrgUserType(str, Enum):
    ADMIN = "admin"
    STANDARD = "standard"

    def __str__(self) -> str:
        return str(self.value)
