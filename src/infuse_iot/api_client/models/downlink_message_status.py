from enum import Enum


class DownlinkMessageStatus(str, Enum):
    COMPLETED = "completed"
    SENT = "sent"
    WAITING = "waiting"

    def __str__(self) -> str:
        return str(self.value)
