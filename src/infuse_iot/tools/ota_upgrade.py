#!/usr/bin/env python3

"""Automatically OTA upgrade observed devices"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import argparse
import binascii
import sys
import threading
import time

from rich.live import Live
from rich.progress import (
    DownloadColumn,
    Progress,
    TaskID,
    TransferSpeedColumn,
)
from rich.status import Status
from rich.table import Table

from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseID
from infuse_iot.definitions.rpc import bt_file_copy_basic, file_write_basic, rpc_enum_file_action
from infuse_iot.epacket.packet import Auth, HopReceived
from infuse_iot.generated.tdf_definitions import readings
from infuse_iot.rpc_client import RpcClient
from infuse_iot.socket_comms import (
    GatewayRequestConnectionRequest,
    LocalClient,
)
from infuse_iot.util.argparse import InfuseDeviceId, ValidFile, ValidRelease, add_server_port_parser
from infuse_iot.util.crc import crc16_ccitt
from infuse_iot.zephyr.errno import errno


class SubCommand(InfuseCommand):
    NAME = "ota_upgrade"
    HELP = "Automatically OTA upgrade observed devices"
    DESCRIPTION = "Automatically OTA upgrade observed devices"

    def __init__(self, args):
        self._clients = [LocalClient(addr, 1.0) for addr in args.server_sock]
        self._conn_timeout = args.conn_timeout
        self._min_rssi: int | None = args.rssi
        self._explicit_ids: list[int] = []
        self._supported_apps: list[int] = []
        if args.release:
            self._release: ValidRelease = args.release
            self._single_diff = None
            # Also capture any releases for other applications.
            if args.cross_app:
                release_dir = self._release.dir / "diffs"
                # List out *.bin files in release_dir and filter where the parent folder is not the release_dir itself
                for diff_file in release_dir.glob("**/*.bin"):
                    if diff_file.parent != release_dir and diff_file.parent.parent == release_dir:
                        # This is a diff for a different application
                        diff_app_id = int(diff_file.parent.name, 0)
                        if diff_app_id not in self._supported_apps:
                            self._supported_apps.append(diff_app_id)

        elif args.single:
            # Find the associated release
            diff_folder = args.single.parent
            if diff_folder.name != "diffs":
                # Try the next level up
                diff_folder = diff_folder.parent
            if diff_folder.name != "diffs":
                raise argparse.ArgumentTypeError(f"{args.single} is not in a diff (sub)folder")
            release_folder = diff_folder.parent
            self._release = ValidRelease(str(release_folder))
            self._single_diff = args.single

            diff_app_id = int(args.single.parent.name, 0)
            if diff_app_id != self._release.metadata["application"]:
                self._supported_apps.append(diff_app_id)
            if args.cross_app and diff_app_id not in self._supported_apps:
                self._supported_apps.append(diff_app_id)
        else:
            raise NotImplementedError("Unknow upgrade type")
        app_meta = self._release.metadata["application"]
        self._app_name = app_meta["primary"]
        self._app_id = app_meta["id"]
        self._new_ver = app_meta["version"]
        self._board_crc = crc16_ccitt(app_meta["board"].encode("utf-8"))
        self._state_connecting: set[int] = set()
        self._state_copying: set[int] = set()
        self._state_uploading: set[int] = set()
        self._tasks: dict[LocalClient, TaskID] = {}
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
        self.end = False

    @classmethod
    def add_parser(cls, parser):
        upgrade_type = parser.add_mutually_exclusive_group(required=True)
        upgrade_type.add_argument("--release", "-r", type=ValidRelease, help="Application release to upgrade to")
        upgrade_type.add_argument("--single", type=ValidFile, help="Single diff")
        parser.add_argument("--cross-app", action="store_true", help="Allow upgrades from other applications")
        parser.add_argument("--rssi", type=int, help="Minimum RSSI to attempt upgrade process")
        parser.add_argument("--log", type=str, help="File to write upgrade results to")
        parser.add_argument(
            "--conn-timeout", type=int, default=10000, help="Timeout to wait for a connection to the device (ms)"
        )
        explicit = parser.add_mutually_exclusive_group()
        explicit.add_argument("--id", type=InfuseDeviceId, help="Single device to upgrade")
        explicit.add_argument("--list", type=ValidFile, help="File containing a list of IDs to upgrade")

        add_server_port_parser(parser, multi_port=True)

    @property
    def _actioning(self) -> set[int]:
        return self._state_connecting | self._state_copying | self._state_uploading

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
        if self._state_connecting:
            meta.add_row(Status(f"Connecting to: {', '.join(f'{i:016X}' for i in self._state_connecting)}"))
        processing = self._state_copying | self._state_uploading
        if processing:
            meta.add_row(Status(f"Writing patch file: {', '.join(f'{i:016X}' for i in processing)}"))

        if not (self._state_connecting or self._state_copying or self._state_uploading):
            meta.add_row(Status(self.state))
        meta.add_row(self.progress)

        return meta

    def state_update(self, live: Live, state: str):
        self.state = state
        live.update(self.progress_table())

    def data_progress_cb(self, offset, client: LocalClient):
        task = self._tasks.get(client)
        if task is None:
            task = self.progress.add_task("", total=len(self.patch_file))
            self._tasks[client] = task
        self.progress.update(task, completed=offset)

    def gateway_diff_load(self, client: LocalClient):
        assert self._single_diff is not None
        with self._single_diff.open("rb") as f:
            patch_file = f.read()

        with client.connection(InfuseID.GATEWAY, GatewayRequestConnectionRequest.DataType.COMMAND, 10) as _mtu:
            rpc_client = RpcClient(client, _mtu, InfuseID.GATEWAY)
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
            return_code = hdr.return_code if hdr else -1
            if return_code != 0:
                raise RuntimeError(f"Failed to save diff file to gateway (({errno.strerror(-return_code)}))")
            print(f"'{self._single_diff}' written to gateway")

    def run_file_upload(self, live: Live, mtu: int, source: HopReceived, client: LocalClient):
        try:
            self._state_uploading.add(source.infuse_id)
            live.update(self.progress_table())
            # self.state_update(live, f"Uploading patch file to {source.infuse_id:016X}")
            rpc_client = RpcClient(client, mtu, source.infuse_id)

            params = file_write_basic.request(rpc_enum_file_action.APP_CPATCH, binascii.crc32(self.patch_file))

            hdr, _rsp = rpc_client.run_data_send_cmd(
                file_write_basic.COMMAND_ID,
                Auth.DEVICE,
                bytes(params),
                self.patch_file,
                lambda offset: self.data_progress_cb(offset, client),
                file_write_basic.response.from_buffer_copy,
            )

            if hdr is None:
                self._failed += 1
            elif hdr.return_code == 0:
                self._pending[source.infuse_id] = time.time() + 60
        finally:
            self._state_uploading.remove(source.infuse_id)
            live.update(self.progress_table())

    def run_file_copy(self, live: Live, mtu: int, source: HopReceived, client: LocalClient):
        try:
            self._state_uploading.add(source.infuse_id)
            live.update(self.progress_table())
            rpc_client = RpcClient(client, mtu, InfuseID.GATEWAY)

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
            if hdr is None:
                self._failed += 1
            elif hdr.return_code == 0:
                self._pending[source.infuse_id] = time.time() + 60
            elif hdr.return_code < 0:
                sock_name = client._input_sock.getsockname()
                err = errno.strerror(-hdr.return_code)
                print(f"{sock_name} Failed to copy patch file to {source.infuse_id:016X} ({err})")
        finally:
            self._state_uploading.remove(source.infuse_id)
            live.update(self.progress_table())

    def run_thread(self, live: Live, client: LocalClient):
        for source, announce in client.observe_announce():
            if self.end:
                return

            live.update(self.progress_table())
            if len(self._explicit_ids):
                if source.infuse_id not in self._explicit_ids:
                    continue
                if len(self._handled) == len(self._explicit_ids):
                    # We've handled all devices
                    self.state_update(live, "All devices updated")
                    return
            else:
                if announce.application != self._app_id and announce.application not in self._supported_apps:
                    continue
            if source.infuse_id in self._handled:
                continue
            if isinstance(announce, readings.announce_v2) and announce.board_crc != self._board_crc:
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
            if v_str == self._new_ver and announce.application == self._app_id:
                self._handled.append(source.infuse_id)
                self._already += 1
                live.update(self.progress_table())
                if self._log:
                    self._log.write(
                        f"{time.time()},0x{source.infuse_id:016x},0x{self._app_id:08x},{v_str},already\n"
                    )
                    self._log.flush()
                continue

            # Do we have a valid diff?
            diff_file = self._release.dir / "diffs" / f"{v_str}.bin"

            if not diff_file.exists() and announce.application in self._supported_apps:
                # Is this a single diff from a different application we know about?
                diff_file = self._release.dir / "diffs" / f"0x{announce.application:08x}" / f"{v_str}.bin"
                if not diff_file.exists():
                    self._missing_diffs.add(v_str)
                    self._handled.append(source.infuse_id)
                    self._no_diff += 1
                    live.update(self.progress_table())
                    continue

            if self._single_diff and self._single_diff != diff_file:
                # Not the file we've copied to the gateway flash
                self._missing_diffs.add(v_str)
                self._handled.append(source.infuse_id)
                self._no_diff += 1
                live.update(self.progress_table())
                continue

            # Is signal strong enough to connect?
            if self._min_rssi and source.rssi < self._min_rssi:
                continue

            # Load patch file
            with open(diff_file, "rb") as f:
                self.patch_file = f.read()

            if source.infuse_id in self._actioning:
                continue

            # Attempt to upload
            self._state_connecting.add(source.infuse_id)
            live.update(self.progress_table())
            try:
                with client.connection(
                    source.infuse_id, GatewayRequestConnectionRequest.DataType.COMMAND, self._conn_timeout
                ) as mtu:
                    self._state_connecting.remove(source.infuse_id)
                    if self._single_diff:
                        self.run_file_copy(live, mtu, source, client)
                    else:
                        self.run_file_upload(live, mtu, source, client)

            except ConnectionRefusedError:
                self._state_connecting.remove(source.infuse_id)
            except ConnectionAbortedError:
                if source.infuse_id in self._state_connecting:
                    self._state_connecting.remove(source.infuse_id)

            if client in self._tasks:
                self.progress.remove_task(self._tasks[client])
                del self._tasks[client]
            live.update(self.progress_table())

    def run(self):
        # Check Gateways are available
        unavailable: list[LocalClient] = []
        for client in self._clients:
            if not client.comms_check():
                unavailable.append(client)
        if len(unavailable) != 0:
            print(
                f"Warning: Could not use {len(unavailable)} gateways on port(s)"
                f" {[x._input_sock.getsockname() for x in unavailable]}."
            )

        # If requested, load single diff onto gateways.
        if self._single_diff:
            for client in unavailable:
                self._clients.remove(client)
            for client in self._clients:
                try:
                    self.gateway_diff_load(client)
                except RuntimeError as e:
                    unavailable.append(client)
                    port_name = client._input_sock.getsockname()
                    print(f"Skipping Gateway on port {port_name}: {''.join(e.args)}.")

        # Ensure there is at least one operational gateway available
        if len(unavailable) == len(self._clients):
            sys.exit("No communications gateway detected (infuse gateway/bt_native)")
        for client in unavailable:
            self._clients.remove(client)

        if len(self._clients) > 1:
            print(
                f"running on {len(self._clients)} gateways "
                f"{[x._input_sock.getsockname() for x in self._clients]}"
            )

        threads: list[threading.Thread] = []
        with Live(self.progress_table(), refresh_per_second=4) as live:
            for client in self._clients:
                socket = client._input_sock.getsockname()
                t = threading.Thread(
                    target=self.run_thread,
                    args=(live, client),
                    name=f"OTA Upgrade {socket}",
                )
                threads.append(t)
            if len(threads) > 1:
                try:
                    for t in threads:
                        t.start()
                    for t in threads:
                        t.join()
                except KeyboardInterrupt:
                    self.end = True
                    self.state_update(live, "Shutting down...")
                    for t in threads:
                        t.join()
            else:
                threads[0].run()
