#!/usr/bin/env python3

import enum
import uuid


class InfuseType(enum.IntEnum):
    """Infuse Data Types"""

    ECHO_REQ = 0
    ECHO_RSP = 1
    TDF = 2
    RPC_CMD = 3
    RPC_DATA = 4
    RPC_DATA_ACK = 5
    RPC_RSP = 6
    RECEIVED_EPACKET = 7
    ACK = 8
    EPACKET_FORWARD = 9
    SERIAL_LOG = 10
    MEMFAULT_CHUNK = 30

    KEY_IDS = 127


class InfuseID(enum.IntEnum):
    """Hardcoded Infuse IDs"""

    GATEWAY = -1


class InfuseBluetoothUUID:
    SERVICE_UUID = uuid.UUID("0000fc74-0000-1000-8000-00805f9b34fb")
    COMMAND_CHAR = uuid.UUID("dc0b71b7-fc74-fc74-aa01-8aba434a893d")
    DATA_CHAR = uuid.UUID("dc0b71b7-fc74-fc74-aa02-8aba434a893d")
    LOGGING_CHAR = uuid.UUID("dc0b71b7-fc74-fc74-aa03-8aba434a893d")
