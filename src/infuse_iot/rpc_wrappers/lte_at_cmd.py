#!/usr/bin/env python3

import ctypes

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.util.ctypes import VLACompatLittleEndianStruct
from infuse_iot.zephyr.errno import errno


class lte_at_cmd(InfuseRpcCommand, defs.lte_at_cmd):
    class request(ctypes.LittleEndianStructure):
        _pack_ = 1

    class response(VLACompatLittleEndianStruct):
        vla_field = ("rsp", 0 * ctypes.c_char)

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--cmd", "-c", type=str, help="Command string")

    def __init__(self, args):
        self.args = args

    def request_struct(self):
        return self.args.cmd.encode("utf-8") + b"\x00"

    def request_json(self):
        return {"cmd": self.args.cmd}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to run command ({errno.strerror(-return_code)})")
            return
        decoded = bytes(response.rsp).decode("utf-8").strip()

        print(decoded)
