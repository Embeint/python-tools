#!/usr/bin/env python3

import ctypes

from infuse_iot.commands import InfuseRpcCommand


class fault(InfuseRpcCommand):
    HELP = "Trigger a fault on the device"
    DESCRIPTION = "Trigger a fault on the device"
    COMMAND_ID = 2

    class request(ctypes.LittleEndianStructure):
        _fields_ = [
            ("fault", ctypes.c_uint8),
            ("zero", ctypes.c_uint32),
        ]
        _pack_ = 1

    class response(ctypes.LittleEndianStructure):
        _fields_ = []
        _pack_ = 1

    @classmethod
    def add_parser(cls, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--div-0",
            dest="fault",
            action="store_const",
            const=30,
            help="Divide by zero exception",
        )
        group.add_argument(
            "--null-deref",
            dest="fault",
            action="store_const",
            const=19,
            help="NULL dereference exception",
        )
        group.add_argument(
            "--stack-overflow",
            dest="fault",
            action="store_const",
            const=2,
            help="Stack overflow exception",
        )
        group.add_argument(
            "--undef-instr",
            dest="fault",
            action="store_const",
            const=36,
            help="Undefined instruction exception",
        )
        group.add_argument(
            "--instr-access",
            dest="fault",
            action="store_const",
            const=20,
            help="Instruction access exception",
        )
        group.add_argument(
            "--wdog",
            dest="fault",
            action="store_const",
            const=128,
            help="Watchdog timeout exception",
        )

    def __init__(self, args):
        self._fault_type = args.fault

    def request_struct(self):
        return self.request(self._fault_type, 0)

    def handle_response(self, return_code, _):
        print(f"Failed to trigger exception ({return_code})")
