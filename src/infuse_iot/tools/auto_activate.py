#!/usr/bin/env python3

"""Automatically activate/deactivate observed devices"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2026, Embeint Holdings Pty Ltd"


from rich.live import Live
from rich.status import Status
from rich.table import Table

import infuse_iot.definitions.kv as kv
import infuse_iot.definitions.rpc as rpc
from infuse_iot.commands import InfuseCommand
from infuse_iot.epacket.packet import Auth
from infuse_iot.rpc_client import RpcClient
from infuse_iot.socket_comms import (
    GatewayRequestConnectionRequest,
    LocalClient,
    default_multicast_address,
)
from infuse_iot.tdf import TDF


class SubCommand(InfuseCommand):
    NAME = "auto_activate"
    HELP = "Automatically activate/deactivate observed devices"
    DESCRIPTION = "Automatically activate/deactivate observed devices"

    def __init__(self, args):
        self.app_ids = args.app
        self.active = args.active or False
        self.client = LocalClient(default_multicast_address(), 1.0)
        self.decoder = TDF()
        self.state = "Scanning"
        self.name = "Active" if args.active else "Inactive"

        self.correct: set[int] = set()
        self.updated: set[int] = set()

    @classmethod
    def add_parser(cls, parser):
        addr_group = parser.add_mutually_exclusive_group(required=True)
        addr_group.add_argument("--app", type=lambda x: int(x, 0), action="append", help="Application ID to control")
        mode_group = parser.add_mutually_exclusive_group(required=True)
        mode_group.add_argument("--active", action="store_true", help="Move all devices to active state")
        mode_group.add_argument("--inactive", action="store_true", help="Move all devices to inactive state")

    def progress_table(self):
        table = Table()
        table.add_column()
        table.add_column("Count")
        table.add_row(self.name, str(len(self.correct)))
        table.add_row("Updated", str(len(self.updated)))

        meta = Table(box=None)
        meta.add_column()
        meta.add_row(table)
        meta.add_row(Status(self.state))

        return meta

    def state_update(self, live: Live, state: str):
        self.state = state
        live.update(self.progress_table())

    def update_active_state(self, live: Live, infuse_id: int, active: bool):
        try:
            self.state_update(live, f"Connecting to {infuse_id:016X}")
            with self.client.connection(infuse_id, GatewayRequestConnectionRequest.DataType.COMMAND) as mtu:
                rpc_client = RpcClient(self.client, mtu, infuse_id)

                key_val = bytes(kv.slots.application_active(1 if active else 0))
                all_vals = (
                    bytes(rpc.rpc_struct_kv_store_value(kv.slots.application_active.BASE_ID, len(key_val))) + key_val
                )
                params = bytes(rpc.kv_write.request(1)) + all_vals

                hdr, _ = rpc_client.run_standard_cmd(
                    rpc.kv_write.COMMAND_ID, Auth.DEVICE, params, rpc.kv_write.response.from_buffer_copy
                )
                if hdr is None:
                    return
                if hdr.return_code == 0:
                    self.updated.add(infuse_id)

        except ConnectionRefusedError:
            self.state_update(live, "Scanning")
            return
        self.state_update(live, "Scanning")

    def run(self):
        with Live(self.progress_table(), refresh_per_second=4) as live:
            for source, announce in self.client.observe_announce():
                if announce.application not in self.app_ids:
                    continue
                application_active = not (announce.flags & 0x80)
                if self.active == application_active:
                    self.correct.add(source.infuse_id)
                else:
                    self.update_active_state(live, source.infuse_id, self.active)
                live.update(self.progress_table())
