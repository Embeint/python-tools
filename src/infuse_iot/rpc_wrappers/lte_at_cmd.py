#!/usr/bin/env python3

import ctypes
import errno

from infuse_iot.commands import InfuseRpcCommand
import infuse_iot.generated.rpc_definitions as defs


class lte_at_cmd(InfuseRpcCommand, defs.lte_at_cmd):
    class request(ctypes.LittleEndianStructure):
        _pack_ = 1

    class response(InfuseRpcCommand.VariableSizeResponse):
        var_name = "rsp"
        var_type = ctypes.c_char

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--cmd", "-c", type=str, help="Command string")

    def __init__(self, args):
        self.args = args

    def request_struct(self):
        return self.args.cmd.encode("utf-8") + b"\x00"

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to run command ({errno.errorcode[-return_code]})")
            return
        decoded = response.rsp.decode("utf-8").strip()

        print(decoded)
