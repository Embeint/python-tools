#!/usr/bin/env python3

import ctypes

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.util.ctypes import UINT16_MAX
from infuse_iot.zephyr.errno import errno


class infuse_states_update(InfuseRpcCommand, defs.infuse_states_update):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--state", "-s", type=int, required=True, help="State ID to update")
        option = parser.add_mutually_exclusive_group(required=True)
        option.add_argument("--set", action="store_true", help="Enable the state permanently")
        option.add_argument("--clear", action="store_true", help="Disable the state")
        option.add_argument("--timeout", type=int, help="Enable the state for a duration (seconds)")

    def __init__(self, args):
        self.args = args

    def request_struct(self):
        class request(ctypes.LittleEndianStructure):
            _fields_ = [
                ("num", ctypes.c_uint8),
                ("state", defs.rpc_struct_infuse_state),
            ]

        timeout = 0 if self.args.set else (UINT16_MAX if self.args.clear else self.args.timeout)
        state = defs.rpc_struct_infuse_state(self.args.state, timeout)

        return request(1, state)

    def request_json(self):
        return {}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to update state {self.args.state} ({errno.strerror(-return_code)})")
        else:
            print(f"Updated state {self.args.state}")
