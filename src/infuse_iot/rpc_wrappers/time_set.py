#!/usr/bin/env python3

import ctypes

from infuse_iot.commands import InfuseRpcCommand


class time_set(InfuseRpcCommand):
    HELP = "Set the current device time"
    DESCRIPTION = "Set the current device time"
    COMMAND_ID = 4

    class request(ctypes.LittleEndianStructure):
        _fields_ = [
            ("civil_time", ctypes.c_uint64),
        ]
        _pack_ = 1

    class response(ctypes.LittleEndianStructure):
        _fields_ = []
        _pack_ = 1

    @classmethod
    def add_parser(cls, parser):
        pass

    def __init__(self, args):
        pass

    def request_struct(self):
        from infuse_iot.time import InfuseTime
        import time

        return self.request(InfuseTime.civil_time_from_unix(time.time()))

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to set current time ({return_code})")
            return
        else:
            print("Set current time on device")
