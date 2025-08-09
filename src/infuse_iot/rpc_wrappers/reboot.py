#!/usr/bin/env python3


import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno


class reboot(InfuseRpcCommand, defs.reboot):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--delay", type=int, default=0, help="Delay until reboot (ms)")

    def __init__(self, args):
        self._delay_ms = args.delay

    def request_struct(self):
        return self.request(self._delay_ms)

    def request_json(self):
        return {"delay_ms": str(self._delay_ms)}

    def handle_response(self, return_code, response):
        if return_code == 0:
            print(f"Rebooting in {response.delay_ms} ms")
        else:
            print(f"Failed to trigger reboot ({errno.strerror(-return_code)})")
