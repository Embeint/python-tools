from enum import Enum


class KeyInterface(str, Enum):
    BT_ADV = "bt_adv"
    BT_GATT = "bt_gatt"
    SERIAL = "serial"
    UDP = "udp"

    def __str__(self) -> str:
        return str(self.value)
