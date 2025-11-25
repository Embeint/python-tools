from enum import Enum


class DeviceEntryUpdateStatus(str, Enum):
    CANCELLED = "cancelled"
    FAILED = "failed"
    PENDING = "pending"
    SUCCESS = "success"

    def __str__(self) -> str:
        return str(self.value)
