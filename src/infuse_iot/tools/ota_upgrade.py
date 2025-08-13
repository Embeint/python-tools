#!/usr/bin/env python3

"""Automatically OTA upgrade observed devices"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import argparse
import binascii
import sys
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
from infuse_iot.common import InfuseID
from infuse_iot.definitions.rpc import bt_file_copy_basic, file_write_basic, rpc_enum_file_action
from infuse_iot.epacket.packet import Auth, HopReceived
from infuse_iot.rpc_client import RpcClient
from infuse_iot.socket_comms import (
    GatewayRequestConnectionRequest,
    LocalClient,
    default_multicast_address,
)
from infuse_iot.util.argparse import ValidFile, ValidRelease
from infuse_iot.zephyr.errno import errno


class SubCommand(InfuseCommand):
    NAME = "ota_upgrade"
    HELP = "Automatically OTA upgrade observed devices"
    DESCRIPTION = "Automatically OTA upgrade observed devices"

    def __init__(self, args):
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._conn_timeout = args.conn_timeout
        self._min_rssi: int | None = args.rssi
        self._explicit_ids: list[int] = []
        if args.release:
            self._release: ValidRelease = args.release
            self._single_diff = None
        elif args.single:
            # Find the associated release
            diff_folder = args.single.parent
            release_folder = diff_folder.parent
            if diff_folder.name != "diffs":
                raise argparse.ArgumentTypeError(f"{args.single} is not in a diff folder")
            self._release = ValidRelease(str(release_folder))
            self._single_diff = args.single
        else:
            raise NotImplementedError("Unknow upgrade type")
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
        if args.log is None:
            self._log = None
        else:
            self._log = open(args.log, "+a", encoding="utf-8")  # noqa: SIM115

        if args.id is not None:
            self._explicit_ids.append(args.id)
        elif args.list is not None:
            with args.list.open("r") as f:
                for line in f.readlines():
                    self._explicit_ids.append(int(line.strip(), 0))

    @classmethod
    def add_parser(cls, parser):
        upgrade_type = parser.add_mutually_exclusive_group(required=True)
        upgrade_type.add_argument("--release", "-r", type=ValidRelease, help="Application release to upgrade to")
        upgrade_type.add_argument("--single", type=ValidFile, help="Single diff")
        parser.add_argument("--rssi", type=int, help="Minimum RSSI to attempt upgrade process")
        parser.add_argument("--log", type=str, help="File to write upgrade results to")
        parser.add_argument(
            "--conn-timeout", type=int, default=10000, help="Timeout to wait for a connection to the device (ms)"
        )
        explicit = parser.add_mutually_exclusive_group()
        explicit.add_argument("--id", type=lambda x: int(x, 0), help="Single device to upgrade")
        explicit.add_argument("--list", type=ValidFile, help="File containing a list of IDs to upgrade")

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

    def gateway_diff_load(self):
        assert self._single_diff is not None
        with self._single_diff.open("rb") as f:
            patch_file = f.read()

        with self._client.connection(InfuseID.GATEWAY, GatewayRequestConnectionRequest.DataType.COMMAND, 10) as _mtu:
            rpc_client = RpcClient(self._client, _mtu, InfuseID.GATEWAY)
            params = file_write_basic.request(rpc_enum_file_action.FILE_FOR_COPY, binascii.crc32(patch_file))

            print(f"Writing '{self._single_diff}' to gateway")
            hdr, _rsp = rpc_client.run_data_send_cmd(
                file_write_basic.COMMAND_ID,
                Auth.DEVICE,
                bytes(params),
                patch_file,
                None,
                file_write_basic.response.from_buffer_copy,
            )
            if hdr.return_code != 0:
                sys.exit(f"Failed to save diff file to gateway (({errno.strerror(-hdr.return_code)}))")
            print(f"'{self._single_diff}' written to gateway")

    def run_file_upload(self, live: Live, mtu: int, source: HopReceived):
        self.state_update(live, f"Uploading patch file to {source.infuse_id:016X}")
        rpc_client = RpcClient(self._client, mtu, source.infuse_id)

        params = file_write_basic.request(rpc_enum_file_action.APP_CPATCH, binascii.crc32(self.patch_file))

        hdr, _rsp = rpc_client.run_data_send_cmd(
            file_write_basic.COMMAND_ID,
            Auth.DEVICE,
            bytes(params),
            self.patch_file,
            self.data_progress_cb,
            file_write_basic.response.from_buffer_copy,
        )

        if hdr.return_code == 0:
            self._pending[source.infuse_id] = time.time() + 60

    def run_file_copy(self, live: Live, mtu: int, source: HopReceived):
        self.state_update(live, f"Copying patch file to {source.infuse_id:016X}")
        rpc_client = RpcClient(self._client, mtu, InfuseID.GATEWAY)

        params = bt_file_copy_basic.request(
            source.interface_address.val.to_rpc_struct(),
            rpc_enum_file_action.APP_CPATCH,
            0,
            len(self.patch_file),
            binascii.crc32(self.patch_file),
            1,
            3,
        )

        hdr, _rsp = rpc_client.run_standard_cmd(
            bt_file_copy_basic.COMMAND_ID,
            Auth.DEVICE,
            bytes(params),
            bt_file_copy_basic.response.from_buffer_copy,
        )
        if hdr.return_code == 0:
            self._pending[source.infuse_id] = time.time() + 60

    def run(self):
        if self._single_diff:
            self.gateway_diff_load()

        with Live(self.progress_table(), refresh_per_second=4) as live:
            for source, announce in self._client.observe_announce():
                self.state_update(live, "Scanning")
                if len(self._explicit_ids):
                    if source.infuse_id not in self._explicit_ids:
                        continue
                    if len(self._handled) == len(self._explicit_ids):
                        # We've handled all devices
                        self.state_update(live, "All devices updated")
                        return
                else:
                    if announce.application != self._app_id:
                        continue
                if source.infuse_id in self._handled:
                    continue
                v = announce.version
                v_str = f"{v.major}.{v.minor}.{v.revision}+{v.build_num:08x}"

                # Check against pending upgrades
                if source.infuse_id in self._pending:
                    if (v_str != self._new_ver) and (time.time() < self._pending[source.infuse_id]):
                        # Device could still be applying the upgrade
                        continue
                    self._pending.pop(source.infuse_id)
                    self._handled.append(source.infuse_id)
                    if v_str == self._new_ver:
                        self._updated += 1
                        result = "upgraded"
                    else:
                        self._failed += 1
                        result = "failed"
                    if self._log:
                        self._log.write(
                            f"{time.time()},0x{source.infuse_id:016x},0x{self._app_id:08x},{v_str},{result}\n"
                        )
                        self._log.flush()
                    continue

                # Already running the requested version?
                if v_str == self._new_ver:
                    self._handled.append(source.infuse_id)
                    self._already += 1
                    self.state_update(live, "Scanning")
                    if self._log:
                        self._log.write(
                            f"{time.time()},0x{source.infuse_id:016x},0x{self._app_id:08x},{v_str},already\n"
                        )
                        self._log.flush()
                    continue

                # Do we have a valid diff?
                diff_file = self._release.dir / "diffs" / f"{v_str}.bin"
                if self._single_diff and self._single_diff != diff_file:
                    # Not the file we've copied to the gateway flash
                    self._missing_diffs.add(v_str)
                    self._handled.append(source.infuse_id)
                    self._no_diff += 1
                    self.state_update(live, "Scanning")
                    continue

                if not diff_file.exists():
                    # Is this a single diff from a different application we know about?
                    diff_file = self._release.dir / "diffs" / f"0x{announce.application:08x}" / f"{v_str}.bin"
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
                        source.infuse_id, GatewayRequestConnectionRequest.DataType.COMMAND, self._conn_timeout
                    ) as mtu:
                        if self._single_diff:
                            self.run_file_copy(live, mtu, source)
                        else:
                            self.run_file_upload(live, mtu, source)

                except ConnectionRefusedError:
                    self.state_update(live, "Scanning")
                except ConnectionAbortedError:
                    self.state_update(live, "Scanning")

                if self.task is not None:
                    self.progress.remove_task(self.task)
                    self.task = None

                self.state_update(live, "Scanning")
