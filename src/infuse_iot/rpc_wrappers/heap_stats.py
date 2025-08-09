#!/usr/bin/env python3

import tabulate

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno


class heap_stats(InfuseRpcCommand, defs.heap_stats):
    @classmethod
    def add_parser(cls, parser):
        pass

    def __init__(self, args):
        self.args = args

    def request_struct(self):
        return self.request()

    def request_json(self):
        return {}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query heap stats ({errno.strerror(-return_code)})")
            return

        stats = []
        for heap in response.stats:
            total = heap.free_bytes + heap.allocated_bytes
            current_percent = 100 * (heap.allocated_bytes / total)
            max_percent = 100 * (heap.max_allocated_bytes / total)
            stats.append(
                [
                    f"0x{heap.addr:08x}",
                    total,
                    heap.allocated_bytes,
                    f"{current_percent:4.1f}%",
                    heap.max_allocated_bytes,
                    f"{max_percent:4.1f}%",
                ]
            )

        print(tabulate.tabulate(stats, headers=["Address", "Total Size", "Current Usage", "", "Max Usage", ""]))
