#!/usr/bin/env python3

import ctypes

from infuse_iot.commands import InfuseRpcCommand


class epacket_udp_reconnect(InfuseRpcCommand):
    HELP = "Request device to reconnect to UDP server"
    DESCRIPTION = "Request device to reconnect to UDP server"
    COMMAND_ID = 15

    class request(ctypes.LittleEndianStructure):
        _fields_ = []
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
        return self.request()

    def handle_response(self, return_code, response):
        print(return_code)
        if return_code != 0:
            print(f"Failed to request reconnect ({return_code})")
            return
