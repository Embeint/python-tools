from enum import Enum


class DefinitionsRPCCommandDefaultAuth(str, Enum):
    EPACKET_AUTH_DEVICE = "EPACKET_AUTH_DEVICE"
    EPACKET_AUTH_NETWORK = "EPACKET_AUTH_NETWORK"

    def __str__(self) -> str:
        return str(self.value)
