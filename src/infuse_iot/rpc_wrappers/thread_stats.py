#!/usr/bin/env python3

import ctypes

import tabulate

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr.errno import errno


class thread_stats(InfuseRpcCommand, defs.thread_stats):
    RPC_DATA_RECEIVE = True

    @classmethod
    def add_parser(cls, parser):
        sort = parser.add_mutually_exclusive_group()
        sort.add_argument("--sort-percentage", action="store_true", help="Sort threads by stack usage (%)")
        sort.add_argument("--sort-bytes", action="store_true", help="Sort threads by bytes bytes")

    def __init__(self, args):
        self.args = args
        self._info = []

    def request_struct(self):
        return self.request()

    def request_json(self):
        return {}

    def data_recv_cb(self, offset: int, data: bytes) -> None:
        base_size = ctypes.sizeof(defs.rpc_struct_thread_stats)
        while len(data) > 0:
            base = defs.rpc_struct_thread_stats.from_buffer_copy(data)
            data = data[base_size:]
            name_len = data.find(b"\x00") + 1
            name = data[:name_len].decode()
            data = data[name_len:]
            percent = int(100 * base.stack_used / base.stack_size)
            unused = base.stack_size - base.stack_used
            self._info.append((name, base.stack_used, unused, base.stack_size, percent, base.utilization))

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query thread stats ({errno.strerror(-return_code)})")
            return

        if self.args.sort_percentage:
            # Sort by stack usage percent
            display = sorted(self._info, key=lambda x: x[4], reverse=True)
        elif self.args.sort_bytes:
            # Sort by stack bytes free
            display = sorted(self._info, key=lambda x: x[2], reverse=True)
        else:
            display = self._info

        headings = ["Thread", "Stack Used", "Stack Free", "Stack Size", "Stack %", "CPU %"]
        print(tabulate.tabulate(display, headers=headings))
