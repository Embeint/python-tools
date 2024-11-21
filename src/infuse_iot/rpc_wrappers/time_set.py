#!/usr/bin/env python3

from infuse_iot.commands import InfuseRpcCommand
import infuse_iot.generated.rpc_definitions as defs


class time_set(InfuseRpcCommand, defs.time_set):
    @classmethod
    def add_parser(cls, parser):
        pass

    def __init__(self, args):
        pass

    def request_struct(self):
        from infuse_iot.time import InfuseTime
        import time

        return self.request(InfuseTime.epoch_time_from_unix(time.time()))

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to set current time ({return_code})")
            return
        else:
            print("Set current time on device")
