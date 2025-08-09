#!/usr/bin/env python3


import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno


class last_reboot(InfuseRpcCommand, defs.last_reboot):
    @classmethod
    def add_parser(cls, parser):
        pass

    def __init__(self, args):
        pass

    def request_struct(self):
        return self.request()

    def request_json(self):
        return {}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query reboot info ({errno.strerror(-return_code)})")
            return

        from infuse_iot.time import InfuseTime, InfuseTimeSource

        t_remote = InfuseTime.unix_time_from_epoch(response.epoch_time)

        print(f"\t     Reason: {response.reason}")
        print(f"\t   Hardware: 0x{response.hardware_flags:08x}")
        print(f"\tReboot Time: {InfuseTime.utc_time_string(t_remote)} ({InfuseTimeSource(response.epoch_time_source)})")
        print(f"\t     Uptime: {response.uptime}")
        print(f"\t    Param 1: 0x{response.param_1:08x}")
        print(f"\t    Param 2: 0x{response.param_2:08x}")
        print(f"\t     Thread: {response.thread.decode('utf-8')}")
