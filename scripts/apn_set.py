#!/usr/bin/env python3

import argparse
import ctypes

from rich.live import Live
from rich.status import Status
from rich.table import Table

import infuse_iot.definitions.kv as kv
import infuse_iot.definitions.rpc as rpc
from infuse_iot.definitions.tdf import readings
from infuse_iot.epacket.packet import Auth
from infuse_iot.rpc_client import RpcClient
from infuse_iot.socket_comms import (
    GatewayRequestConnectionRequest,
    LocalClient,
    default_multicast_address,
)
from infuse_iot.tdf import TDF
from infuse_iot.util.ctypes import VLACompatLittleEndianStruct


class APNSetter:
    def __init__(self, args: argparse.Namespace):
        self.app_id = args.app
        self.apn = args.apn
        self.family = args.family
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
        meta.add_row(Status(self.state))
        meta.add_row(table)

        return meta

    class response(VLACompatLittleEndianStruct):
        _fields_ = []
        vla_field = ("rc", 0 * ctypes.c_int16)
        _pack_ = 1

    def state_update(self, live: Live, state: str):
        self.state = state
        live.update(self.progress_table())

    def announce_observed(self, live: Live, infuse_id: int, pkt: readings.announce | readings.announce_v2):
        if infuse_id in self.updated or infuse_id in self.already:
            return
        if pkt.application != self.app_id:
            return
        try:
            self.state_update(live, f"Connecting to {infuse_id:016X}")
            with self.client.connection(infuse_id, GatewayRequestConnectionRequest.DataType.COMMAND) as mtu:
                rpc_client = RpcClient(self.client, mtu, infuse_id)

                family_bytes = self.family.to_bytes(1, "little")
                apn_bytes = self.apn.encode("utf-8") + b"\x00"
                val_bytes = family_bytes + len(apn_bytes).to_bytes(1, "little") + apn_bytes

                all_vals = (
                    bytes(rpc.rpc_struct_kv_store_value(kv.slots.lte_pdp_config.BASE_ID, len(val_bytes))) + val_bytes
                )
                params = bytes(rpc.kv_write.request(1)) + all_vals

                hdr, rsp = rpc_client.run_standard_cmd(
                    rpc.kv_write.COMMAND_ID, Auth.DEVICE, params, self.response.vla_from_buffer_copy
                )
                if hdr is None:
                    return
                if hdr.return_code == 0:
                    assert rsp is not None and hasattr(rsp, "rc")
                    if rsp.rc[0] == 0:
                        self.already.append(infuse_id)
                    else:
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
    parser = argparse.ArgumentParser("Configure the LTE APN of devices")
    addr_group = parser.add_mutually_exclusive_group(required=True)
    addr_group.add_argument("--app", type=lambda x: int(x, 0), help="Application ID to configure")
    parser.add_argument("--apn", type=str, required=True, help="LTE APN value")
    family_group = parser.add_mutually_exclusive_group()
    family_group.add_argument("--ipv4", dest="family", action="store_const", const=0, help="IPv4")
    family_group.add_argument("--ipv6", dest="family", action="store_const", const=1, help="IPv6")
    family_group.add_argument("--ipv4v6", dest="family", action="store_const", default=2, const=2, help="IPv4v6")
    family_group.add_argument("--nonip", dest="family", action="store_const", const=3, help="NonIP")

    args = parser.parse_args()

    try:
        tool = APNSetter(args)
        tool.run()
    except KeyboardInterrupt:
        pass
