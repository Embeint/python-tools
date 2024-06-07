#!/usr/bin/env python3

import ctypes

from infuse_iot.commands import InfuseRpcCommand


class reboot(InfuseRpcCommand):
    HELP = "Reboot the device"
    DESCRIPTION = "Reboot the device"
    COMMAND_ID = 1

    class request(ctypes.LittleEndianStructure):
        _fields_ = [
            ("delay_ms", ctypes.c_uint32),
        ]
        _pack_ = 1

    class response(ctypes.LittleEndianStructure):
        _fields_ = [
            ("delay_ms", ctypes.c_uint32),
        ]
        _pack_ = 1

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--delay", type=int, default=0, help="Delay until reboot (ms)"
        )

    def __init__(self, args):
        self._delay_ms = args.delay

    def request_struct(self):
        return self.request(self._delay_ms)

    def handle_response(self, return_code, response):
        if return_code == 0:
            print(f"Rebooting in {response.delay_ms} ms")
        else:
            print(f"Failed to trigger reboot ({return_code})")
