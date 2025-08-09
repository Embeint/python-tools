#!/usr/bin/env python3


import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno


class time_set(InfuseRpcCommand, defs.time_set):
    @classmethod
    def add_parser(cls, parser):
        pass

    def __init__(self, args):
        pass

    def request_struct(self):
        import time

        from infuse_iot.time import InfuseTime

        return self.request(InfuseTime.epoch_time_from_unix(time.time()))

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to set current time ({errno.strerror(-return_code)})")
            return
        else:
            print("Set current time on device")
