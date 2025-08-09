#!/usr/bin/env python3


import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno


class time_get(InfuseRpcCommand, defs.time_get):
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
            print(f"Failed to query current time ({errno.strerror(-return_code)})")
            return

        import time

        from infuse_iot.time import InfuseTime, InfuseTimeSource

        t_remote = InfuseTime.unix_time_from_epoch(response.epoch_time)
        t_local = time.time()
        sync_age = f"{response.sync_age} seconds ago" if response.sync_age != 2**32 - 1 else "Never"

        print(f"\t     Source: {InfuseTimeSource(response.time_source)}")
        print(f"\tRemote Time: {InfuseTime.utc_time_string(t_remote)}")
        print(f"\t Local Time: {InfuseTime.utc_time_string(t_local)}")
        print(f"\t     Synced: {sync_age}")
