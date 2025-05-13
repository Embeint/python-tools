from enum import Enum


class DefinitionsFieldConversionInt(str, Enum):
    BIG = "big"
    LITTLE = "little"

    def __str__(self) -> str:
        return str(self.value)
