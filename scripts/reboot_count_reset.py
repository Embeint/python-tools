#!/usr/bin/env python3

import argparse

from rich.live import Live
from rich.status import Status
from rich.table import Table

import infuse_iot.generated.kv_definitions as kv
import infuse_iot.generated.rpc_definitions as rpc
from infuse_iot.definitions.tdf import readings
from infuse_iot.epacket.packet import Auth
from infuse_iot.rpc_client import RpcClient
from infuse_iot.socket_comms import (
    GatewayRequestConnectionRequest,
    LocalClient,
    default_multicast_address,
)
from infuse_iot.tdf import TDF


class RebootCountResetter:
    def __init__(self, args: argparse.Namespace):
        self.app_id = args.app
        self.count = args.count
        self.client = LocalClient(default_multicast_address(), 1.0)
        self.decoder = TDF()
        self.state = "Scanning"

        self.already: list[int] = []
        self.updated: list[int] = []

    def progress_table(self):
        table = Table()
        table.add_column()
        table.add_column("Count")
        table.add_row("Updated", str(len(self.updated)))
        table.add_row("Already", str(len(self.already)))

        meta = Table(box=None)
        meta.add_column()
        meta.add_row(table)
        meta.add_row(Status(self.state))

        return meta

    def state_update(self, live: Live, state: str):
        self.state = state
        live.update(self.progress_table())

    def announce_observed(self, live: Live, infuse_id: int, pkt: readings.announce):
        if pkt.application != self.app_id:
            return
        if pkt.reboots == self.count:
            if (infuse_id not in self.already) and (infuse_id not in self.updated):
                self.already.append(infuse_id)
            return
        try:
            self.state_update(live, f"Connecting to {infuse_id:016X}")
            with self.client.connection(infuse_id, GatewayRequestConnectionRequest.DataType.COMMAND) as mtu:
                rpc_client = RpcClient(self.client, mtu, infuse_id)

                key_val = bytes(kv.slots.reboots(self.count))
                all_vals = bytes(rpc.rpc_struct_kv_store_value(kv.slots.reboots.BASE_ID, len(key_val))) + key_val
                params = bytes(rpc.kv_write.request(1)) + all_vals

                hdr, _ = rpc_client.run_standard_cmd(
                    rpc.kv_write.COMMAND_ID, Auth.DEVICE, params, rpc.kv_write.response.from_buffer_copy
                )
                if hdr.return_code == 0:
                    self.updated.append(infuse_id)

        except ConnectionRefusedError:
            self.state_update(live, "Scanning")
            return
        self.state_update(live, "Scanning")

    def run(self):
        with Live(self.progress_table(), refresh_per_second=4) as live:
            for source, announce in self.client.observe_announce():
                self.announce_observed(live, source.infuse_id, announce)
                live.update(self.progress_table())


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Reset reboot counters to a common value")
    addr_group = parser.add_mutually_exclusive_group(required=True)
    addr_group.add_argument("--app", type=lambda x: int(x, 0), help="Application ID to reset")
    parser.add_argument("--count", type=int, default=0, help="Value to reset count to")

    args = parser.parse_args()

    try:
        tool = RebootCountResetter(args)
        tool.run()
    except KeyboardInterrupt:
        pass
