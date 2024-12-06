from enum import Enum


class RouteType(str, Enum):
    UDP = "udp"

    def __str__(self) -> str:
        return str(self.value)
