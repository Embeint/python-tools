from enum import Enum


class APIKeyResourceName(str, Enum):
    BOARD = "board"
    DEVICE = "device"
    NETWORK = "network"

    def __str__(self) -> str:
        return str(self.value)
