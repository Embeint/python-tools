#!/usr/bin/env python3

import ctypes

from infuse_iot.commands import InfuseRpcCommand


class time_get(InfuseRpcCommand):
    HELP = "Get the current device time"
    DESCRIPTION = "Get the current device time"
    COMMAND_ID = 3

    class request(ctypes.LittleEndianStructure):
        _fields_ = []
        _pack_ = 1

    class response(ctypes.LittleEndianStructure):
        _fields_ = [
            ("time_source", ctypes.c_uint8),
            ("civil_time", ctypes.c_uint64),
            ("sync_age", ctypes.c_uint32),
        ]
        _pack_ = 1

    @classmethod
    def add_parser(cls, parser):
        pass

    def __init__(self, args):
        pass

    def request_struct(self):
        return self.request()

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query current time ({return_code})")
            return

        from infuse_iot.time import InfuseTime, InfuseTimeSource
        import time

        t_remote = InfuseTime.unix_time_from_civil(response.civil_time)
        t_local = time.time()

        print(f"\t     Source: {InfuseTimeSource(response.time_source)}")
        print(f"\tRemote Time: {InfuseTime.utc_time_string(t_remote)}")
        print(f"\t Local Time: {InfuseTime.utc_time_string(t_local)}")
        print(f"\t     Synced: {response.sync_age} seconds ago")
