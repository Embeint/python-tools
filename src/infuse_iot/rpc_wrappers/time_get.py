#!/usr/bin/env python3

from infuse_iot.commands import InfuseRpcCommand
import infuse_iot.generated.rpc_definitions as defs


class time_get(InfuseRpcCommand, defs.time_get):
    @classmethod
    def add_parser(cls, parser):
        pass

    def __init__(self, args):
        pass

    def request_struct(self):
        return self.request()

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query current time ({return_code})")
            return

        from infuse_iot.time import InfuseTime, InfuseTimeSource
        import time

        t_remote = InfuseTime.unix_time_from_epoch(response.epoch_time)
        t_local = time.time()

        print(f"\t     Source: {InfuseTimeSource(response.time_source)}")
        print(f"\tRemote Time: {InfuseTime.utc_time_string(t_remote)}")
        print(f"\t Local Time: {InfuseTime.utc_time_string(t_local)}")
        print(f"\t     Synced: {response.sync_age} seconds ago")
