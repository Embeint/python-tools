#!/usr/bin/env python3

import ctypes


class RequestHeader(ctypes.LittleEndianStructure):
    """RPC_CMD packet header"""

    _fields_ = [
        ("request_id", ctypes.c_uint32),
        ("command_id", ctypes.c_uint16),
    ]
    _pack_ = 1


class RequestDataHeader(ctypes.LittleEndianStructure):
    """RPC_CMD additional header for RPC_DATA"""

    _fields_ = [
        ("size", ctypes.c_uint32),
        ("rx_ack_period", ctypes.c_uint8),
    ]
    _pack_ = 1


class DataHeader(ctypes.LittleEndianStructure):
    """RPC_DATA header"""

    _fields_ = [
        ("request_id", ctypes.c_uint32),
        ("offset", ctypes.c_uint32),
    ]
    _pack_ = 1


class DataAck(ctypes.LittleEndianStructure):
    """RPC_DATA_ACK payload"""

    _fields_ = [
        ("request_id", ctypes.c_uint32),
        ("offset", 0 * ctypes.c_uint32),
    ]
    _pack_ = 1


class ResponseHeader(ctypes.LittleEndianStructure):
    """RPC_RSP packet header"""

    _fields_ = [
        ("request_id", ctypes.c_uint32),
        ("command_id", ctypes.c_uint16),
        ("return_code", ctypes.c_int16),
    ]
    _pack_ = 1
