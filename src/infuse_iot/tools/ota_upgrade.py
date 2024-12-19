#!/usr/bin/env python3

"""Automatically OTA upgrade observed devices"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import binascii
import time

from rich.live import Live
from rich.progress import (
    DownloadColumn,
    Progress,
    TransferSpeedColumn,
)
from rich.status import Status
from rich.table import Table

from infuse_iot.commands import InfuseCommand
from infuse_iot.epacket.packet import Auth
from infuse_iot.generated.rpc_definitions import file_write_basic, rpc_enum_file_action
from infuse_iot.rpc_client import RpcClient
from infuse_iot.socket_comms import (
    GatewayRequestConnectionRequest,
    LocalClient,
    default_multicast_address,
)
from infuse_iot.util.argparse import ValidRelease


class SubCommand(InfuseCommand):
    NAME = "ota_upgrade"
    HELP = "Automatically OTA upgrade observed devices"
    DESCRIPTION = "Automatically OTA upgrade observed devices"

    def __init__(self, args):
        self._client = LocalClient(default_multicast_address(), 60.0)
        self._min_rssi: int | None = args.rssi
        self._release: ValidRelease = args.release
        self._app_name = self._release.metadata["application"]["primary"]
        self._app_id = self._release.metadata["application"]["id"]
        self._new_ver = self._release.metadata["application"]["version"]
        self._handled: list[int] = []
        self._pending: dict[int, float] = {}
        self._missing_diffs: set[str] = set()
        self._already = 0
        self._updated = 0
        self._no_diff = 0
        self._failed = 0
        self.patch_file = b""
        self.state = "Scanning"
        self.progress = Progress(
            *Progress.get_default_columns(),
            DownloadColumn(),
            TransferSpeedColumn(),
        )
        self.task = None

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--release", "-r", type=ValidRelease, required=True, help="Application release to upgrade to"
        )
        parser.add_argument("--rssi", type=int, help="Minimum RSSI to attempt upgrade process")

    def progress_table(self):
        table = Table()
        table.add_column(f"{self._app_name}\n{self._new_ver}")
        table.add_column("Count")
        table.add_row("Updated", str(self._updated))
        table.add_row("Pending", str(len(self._pending)))
        table.add_row("Already", str(self._already))
        table.add_row("Failed", str(self._failed))
        table.add_row("No Diff", str(self._no_diff))

        if len(self._missing_diffs) > 0:
            table.add_section()
            table.add_row("Missing diffs", "\n".join(self._missing_diffs))

        meta = Table(box=None)
        meta.add_column()
        meta.add_row(table)
        meta.add_row(Status(self.state))
        meta.add_row(self.progress)

        return meta

    def state_update(self, live: Live, state: str):
        self.state = state
        live.update(self.progress_table())

    def data_progress_cb(self, offset):
        if self.task is None:
            self.state = "Writing patch file"
            self.task = self.progress.add_task("", total=len(self.patch_file))
        self.progress.update(self.task, completed=offset)

    def run(self):
        with Live(self.progress_table(), refresh_per_second=4) as live:
            for source, announce in self._client.observe_announce():
                self.state_update(live, "Scanning")
                if announce.application != self._app_id:
                    continue
                if source.infuse_id in self._handled:
                    continue
                v = announce.version
                v_str = f"{v.major}.{v.minor}.{v.revision}+{v.build_num:08x}"

                # Check against pending upgrades
                if source.infuse_id in self._pending:
                    if time.time() < self._pending[source.infuse_id]:
                        # Device could still be applying the upgrade
                        continue
                    self._pending.pop(source.infuse_id)
                    self._handled.append(source.infuse_id)
                    if v_str == self._new_ver:
                        self._updated += 1
                    else:
                        self._failed += 1
                    continue

                # Already running the requested version?
                if v_str == self._new_ver:
                    self._handled.append(source.infuse_id)
                    self._already += 1
                    self.state_update(live, "Scanning")
                    continue

                # Do we have a valid diff?
                diff_file = self._release.dir / "diffs" / f"{v_str}.bin"
                if not diff_file.exists():
                    self._missing_diffs.add(v_str)
                    self._handled.append(source.infuse_id)
                    self._no_diff += 1
                    self.state_update(live, "Scanning")
                    continue

                # Is signal strong enough to connect?
                if self._min_rssi and source.rssi < self._min_rssi:
                    continue

                # Load patch file
                with open(diff_file, "rb") as f:
                    self.patch_file = f.read()

                # Attempt to upload
                self.state_update(live, f"Connecting to {source.infuse_id:016X}")
                try:
                    with self._client.connection(
                        source.infuse_id, GatewayRequestConnectionRequest.DataType.COMMAND
                    ) as mtu:
                        self.state_update(live, f"Uploading patch file to {source.infuse_id:016X}")
                        rpc_client = RpcClient(self._client, mtu, source.infuse_id)

                        params = file_write_basic.request(
                            rpc_enum_file_action.APP_CPATCH, binascii.crc32(self.patch_file)
                        )

                        hdr, _rsp = rpc_client.run_data_send_cmd(
                            file_write_basic.COMMAND_ID,
                            Auth.DEVICE,
                            bytes(params),
                            self.patch_file,
                            self.data_progress_cb,
                            file_write_basic.response.from_buffer_copy,
                        )

                        if hdr.return_code == 0:
                            self._pending[source.infuse_id] = time.time() + 30

                except ConnectionRefusedError:
                    self.state_update(live, "Scanning")
                except ConnectionAbortedError:
                    self.state_update(live, "Scanning")

                if self.task is not None:
                    self.progress.remove_task(self.task)
                    self.task = None

                self.state_update(live, "Scanning")
