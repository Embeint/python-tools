from enum import Enum


class DefinitionsFieldDisplayFmt(str, Enum):
    FLOAT = "float"
    HEX = "hex"

    def __str__(self) -> str:
        return str(self.value)
