from enum import Enum


class BtLeRouteType(str, Enum):
    PUBLIC = "public"
    RANDOM = "random"
    UNKNOWN = "unknown"

    def __str__(self) -> str:
        return str(self.value)
