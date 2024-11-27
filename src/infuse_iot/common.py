#!/usr/bin/env python3

import enum


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
