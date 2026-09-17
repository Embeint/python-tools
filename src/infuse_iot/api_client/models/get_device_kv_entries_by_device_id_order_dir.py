from enum import Enum


class GetDeviceKVEntriesByDeviceIDOrderDir(str, Enum):
    ASC = "asc"
    DESC = "desc"

    def __str__(self) -> str:
        return str(self.value)
