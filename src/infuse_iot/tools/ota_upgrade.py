#!/usr/bin/env python3

"""Automatically OTA upgrade observed devices"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import argparse
import binascii
import ctypes
import sys
import time
from contextlib import ExitStack
from pathlib import Path

import platformdirs
from rich.live import Live
from rich.progress import (
    DownloadColumn,
    Progress,
    TransferSpeedColumn,
)
from rich.status import Status
from rich.table import Table

from infuse_iot.commands import InfuseCommand, rpc_return_code_str
from infuse_iot.common import InfuseID, InfuseType
from infuse_iot.definitions.rpc import bt_file_copy_basic, file_write_basic, rpc_enum_file_action, time_set
from infuse_iot.epacket.packet import Auth, HopReceived, PacketReceived
from infuse_iot.generated.tdf_definitions import readings
from infuse_iot.rpc_client import RpcClient
from infuse_iot.services.device_operations import DeviceError
from infuse_iot.services.device_state import DeviceState
from infuse_iot.services.firmware import FirmwareService
from infuse_iot.socket_comms import (
    GatewayRequestConnectionRequest,
    LocalClient,
)
from infuse_iot.tdf import TDF
from infuse_iot.time import InfuseTime
from infuse_iot.util.argparse import InfuseDeviceId, ValidFile, ValidRelease, add_server_port_parser
from infuse_iot.util.crc import crc16_ccitt


class SubCommand(InfuseCommand):
    def __init__(self, args):
        self._args = args
        self._client = LocalClient(args.server_sock, 1.0)
        self._conn_timeout = args.conn_timeout
        self._min_rssi: int | None = args.rssi
        self._explicit_ids: list[int] = []
        if args.release:
            self._release: ValidRelease = args.release
            self._single_diff = None
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
        else:
            raise NotImplementedError("Unknow upgrade type")
        app_meta = self._release.metadata["application"]
        self._app_name = app_meta["primary"]
        self._app_id = app_meta["id"]
        self._new_ver = app_meta["version"]
        self._board_crc = crc16_ccitt(app_meta["board"].encode("utf-8"))
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
        self._log_path = args.log
        self._log = None

        if args.id is not None:
            self._explicit_ids.append(args.id)
        elif args.list is not None:
            with args.list.open("r") as f:
                for line in f.readlines():
                    self._explicit_ids.append(int(line.strip(), 0))
        if args.release and args.board is not None and not self._explicit_ids:
            raise argparse.ArgumentTypeError("--board asserts the board of explicit devices, use --id or --list")
        if args.release and not 5 <= args.verification_seconds <= 600:
            raise argparse.ArgumentTypeError("--verification-seconds must be between 5 and 600")
        self._skipped: set[str] = set()
        self._failures: dict[str, str] = {}

    @classmethod
    def add_parser(cls, parser):
        upgrade_type = parser.add_mutually_exclusive_group(required=True)
        upgrade_type.add_argument(
            "--release",
            "-r",
            type=ValidRelease,
            help="Application release to upgrade to; without --id/--list, keep scanning until interrupted",
        )
        upgrade_type.add_argument("--single", type=ValidFile, help="Single diff")
        parser.add_argument(
            "--full-image",
            action="store_true",
            help="Write the full signed image to devices without a matching diff (requires board evidence)",
        )
        parser.add_argument(
            "--board",
            help="Assert the board of the --id/--list devices, for full images to devices without board telemetry",
        )
        parser.add_argument(
            "--allow-downgrade", action="store_true", help="Allow releases older than the running version"
        )
        parser.add_argument("--trusted-public-key", help="MCUboot RSA public key PEM for host signature verification")
        parser.add_argument(
            "--verification-seconds",
            type=float,
            default=60,
            help="Time for a device to announce the new version after its transfer (5..600 seconds)",
        )
        parser.add_argument("--rssi", type=int, help="Minimum RSSI to attempt upgrade process")
        parser.add_argument("--log", type=str, help="File to write upgrade results to")
        parser.add_argument(
            "--conn-timeout", type=int, default=10000, help="Timeout to wait for a connection to the device (ms)"
        )
        explicit = parser.add_mutually_exclusive_group()
        explicit.add_argument("--id", type=InfuseDeviceId, help="Single device to upgrade")
        explicit.add_argument("--list", type=ValidFile, help="File containing a list of IDs to upgrade")

        add_server_port_parser(parser)

    def progress_table(self):
        table = Table()
        table.add_column(f"{self._app_name}\n{self._new_ver}")
        table.add_column("Count")
        table.add_row("Updated", str(self._updated))
        table.add_row("Pending", str(len(self._pending)))
        table.add_row("Already", str(self._already))
        table.add_row("Failed", str(self._failed))
        table.add_row("No Diff", str(self._no_diff))
        if self._skipped:
            table.add_row("Skipped", str(len(self._skipped)))

        if len(self._missing_diffs) > 0:
            table.add_section()
            table.add_row("Missing diffs", "\n".join(self._missing_diffs))
        if self._skipped:
            table.add_section()
            table.add_row("Skipped", "\n".join(sorted(self._skipped)))
        if self._failures:
            table.add_section()
            table.add_row("Failure reasons", "\n".join(f"{k}: {v}" for k, v in sorted(self._failures.items())))

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
            return_code = hdr.return_code if hdr else -1
            if return_code != 0:
                sys.exit(f"Failed to save diff file to gateway ({rpc_return_code_str(return_code)})")
            print(f"'{self._single_diff}' written to gateway")

    def set_device_time(self, mtu: int, infuse_id: int) -> bool:
        rpc_client = RpcClient(self._client, mtu, infuse_id)
        rpc_client.set_timeout(2.0)

        params = time_set.request(InfuseTime.epoch_time_from_unix(time.time()))
        hdr, _rsp = rpc_client.run_standard_cmd(
            time_set.COMMAND_ID,
            Auth.DEVICE,
            bytes(params),
            time_set.response.from_buffer_copy,
        )
        # Command completed and succeeded
        return hdr is not None and hdr.return_code == 0

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

        if hdr is None:
            self._failed += 1
        elif hdr.return_code == 0:
            self._pending[source.infuse_id] = time.time() + 60

    def run_file_copy(self, live: Live, mtu: int, source: HopReceived):
        self.state_update(live, f"Copying patch file to {source.infuse_id:016X}")
        rpc_client = RpcClient(self._client, mtu, InfuseID.GATEWAY)
        rpc_client.set_timeout(60.0)

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

    def run(self):
        with ExitStack() as stack:
            if self._log_path is not None:
                self._log = stack.enter_context(
                    open(self._log_path, "+a", encoding="utf-8")  # noqa: SIM115
                )
            if self._single_diff:
                self._run()
            else:
                self._run_release()

    def _log_result(self, infuse_id: int, version: str, result: str, reason: str | None = None):
        if reason is not None:
            # The CSV keeps its five columns, so the reason is shown in the summary instead.
            self._failures[f"0x{infuse_id:016x}"] = reason
        if self._log:
            self._log.write(f"{time.time()},0x{infuse_id:016x},0x{self._app_id:08x},{version},{result}\n")
            self._log.flush()

    def _run_release(self):
        """Plan and transfer with the inspected release service used by MCP"""
        state = DeviceState()
        service = FirmwareService(
            self._args.server_sock,
            state,
            Path(platformdirs.user_cache_dir("infuse-iot", "Embeint")) / "firmware",
            require_ownership=False,
            connection_timeout_ms=self._conn_timeout,
        )
        # Inspected once: transfers recheck the staged bytes they send.
        try:
            package = service.inspect(str(self._release.dir), self._args.trusted_public_key)
        except (DeviceError, ValueError) as error:
            sys.exit(f"Release rejected: {error}")
        # Versions that transferred devices last announced, for devices still awaiting verification
        transferred_from: dict[int, str] = {}
        try:
            capabilities = self._client.capabilities()
        except TimeoutError:
            sys.exit("No communications gateway detected (infuse gateway/bt_native)")
        # Protocol v1 gateways do not report their kind; only serial gateways have a time to set.
        if capabilities.get("gateway_kind", "serial") == "serial":
            with self._client.connection(InfuseID.GATEWAY, GatewayRequestConnectionRequest.DataType.COMMAND) as mtu:
                if not self.set_device_time(mtu, InfuseID.GATEWAY):
                    sys.exit("Failed to set time on local gateway")
        boards = {f"0x{i:016x}": self._args.board for i in self._explicit_ids} if self._args.board else {}

        command = self

        class Context:
            def check_cancelled(self):
                pass  # KeyboardInterrupt unwinds the owned connection.

            def checkpoint(self, result):
                pass

            def sending(self):
                pass

            def wait(self, seconds):
                time.sleep(seconds)

            def progress(self, phase, **values):
                command.state_update(live, f"{phase}: {values.get('device_id', '')}")
                if "bytes_sent" in values:
                    if command.task is None:
                        command.task = command.progress.add_task("", total=values["total_bytes"])
                    command.progress.update(command.task, completed=values["bytes_sent"])

        def handle(source: HopReceived, announce) -> bool:
            """Process one announcement, returning whether the device now awaits verification"""
            v = announce.version
            v_str = f"{v.major}.{v.minor}.{v.revision}+{v.build_num:08x}"
            identifier = f"0x{source.infuse_id:016x}"
            # Check against pending upgrades
            if source.infuse_id in self._pending:
                current = v_str == self._new_ver and announce.application == self._app_id
                if not current and time.time() < self._pending[source.infuse_id]:
                    # Device could still be applying the upgrade
                    return False
                self._pending.pop(source.infuse_id)
                transferred_from.pop(source.infuse_id, None)
                self._handled.append(source.infuse_id)
                if current:
                    self._updated += 1
                    self._log_result(source.infuse_id, v_str, "upgraded")
                else:
                    self._failed += 1
                    self._log_result(source.infuse_id, v_str, "failed", "verification_timeout")
                return False
            payload = bytes(TDF.CoreHeader(announce.ID, ctypes.sizeof(announce))) + bytes(announce)
            state.observe(PacketReceived([source], InfuseType.TDF, payload))
            try:
                plan = service.plan(
                    str(self._release.dir),
                    [identifier],
                    device_boards={identifier: boards[identifier]} if identifier in boards else None,
                    trusted_public_key=self._args.trusted_public_key,
                    verification_seconds=self._args.verification_seconds,
                    allow_downgrade=self._args.allow_downgrade,
                    full_image_fallback=self._args.full_image,
                    allow_application_change=bool(self._explicit_ids),
                    store=False,
                    package=package,
                )
            except (DeviceError, ValueError) as error:
                # Only this device's evidence was rejected; keep scanning for others.
                self._handled.append(source.infuse_id)
                self._skipped.add(f"{identifier}: {getattr(error, 'code', 'invalid_request')}")
                return False
            entry = plan["devices"][0]
            if entry["status"] == "already_current":
                self._handled.append(source.infuse_id)
                self._already += 1
                self._log_result(source.infuse_id, v_str, "already")
                return False
            if entry["status"] == "blocked":
                self._handled.append(source.infuse_id)
                if entry["reason"] == "no_matching_patch":
                    self._no_diff += 1
                    self._missing_diffs.add(v_str)
                else:
                    self._skipped.add(f"{identifier}: {entry['reason'].split(';')[0]}")
                return False
            # Is signal strong enough to connect?
            if self._min_rssi and source.rssi < self._min_rssi:
                return False
            try:
                outcome = service.transfer(entry, plan["package"], Context(), verification_seconds=None)
            except DeviceError as error:
                if error.retryable:
                    # Nothing was written, retry on a later announcement
                    return False
                if error.code == "release_changed":
                    # Staged bytes were pruned or damaged: stage them again, unless the release itself changed.
                    try:
                        unchanged = service.inspect(str(self._release.dir), self._args.trusted_public_key) == package
                    except (DeviceError, ValueError):
                        unchanged = False
                    if unchanged:
                        return False
                    sys.exit("Release changed during the scan; restart to inspect it again")
                if error.code != "outcome_unknown":
                    self._handled.append(source.infuse_id)
                    self._failed += 1
                    self._log_result(source.infuse_id, v_str, "failed", error.code)
                    return False
                # The device may still apply the image, so verify it like a completed transfer
                outcome = {"status": "unknown"}
            finally:
                if self.task is not None:
                    self.progress.remove_task(self.task)
                    self.task = None
            if outcome["status"] == "already_current":
                self._handled.append(source.infuse_id)
                self._already += 1
                self._log_result(source.infuse_id, outcome["version"], "already")
                return False
            # Verified from later announcements, while other devices are upgraded
            self._pending[source.infuse_id] = time.time() + self._args.verification_seconds
            transferred_from[source.infuse_id] = v_str
            return True

        try:
            with Live(self.progress_table(), refresh_per_second=4) as live:
                while True:
                    for source, announce in self._client.observe_announce():
                        self.state_update(live, "Scanning")
                        if self._explicit_ids:
                            if source.infuse_id not in self._explicit_ids:
                                continue
                        elif announce.application != self._app_id:
                            continue
                        if source.infuse_id in self._handled:
                            continue
                        awaiting = handle(source, announce)
                        self.state_update(live, "Scanning")
                        if self._explicit_ids and set(self._explicit_ids) <= set(self._handled):
                            self.state_update(live, "All devices updated")
                            return
                        if awaiting:
                            break
                    else:
                        return
                    # Announcements queued during a transfer predate it; observe from a new subscription.
                    self._client.close()
                    self._client = LocalClient(self._args.server_sock, 1.0)
        finally:
            # For example after Ctrl+C: these devices may still apply their image.
            for infuse_id, version in transferred_from.items():
                self._log_result(infuse_id, version, "unverified")

    def _run(self):
        if not self._client.comms_check():
            sys.exit("No communications gateway detected (infuse gateway/bt_native)")

        if self._single_diff:
            self.gateway_diff_load()

        # Set the gateways time at script startup
        try:
            with self._client.connection(InfuseID.GATEWAY, GatewayRequestConnectionRequest.DataType.COMMAND, 10) as mtu:
                if not self.set_device_time(mtu, InfuseID.GATEWAY):
                    sys.exit("Failed to set time on local gateway")
        except ConnectionRefusedError:
            # native_bt has no gateway device to connect to, and runs on the local clock
            print("Gateway does not accept connections, skipping gateway time sync")

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

                if not diff_file.exists():
                    # Is this a single diff from a different application we know about?
                    diff_file = self._release.dir / "diffs" / f"0x{announce.application:08x}" / f"{v_str}.bin"
                    if not diff_file.exists():
                        self._missing_diffs.add(v_str)
                        self._handled.append(source.infuse_id)
                        self._no_diff += 1
                        self.state_update(live, "Scanning")
                        continue

                if self._single_diff and self._single_diff != diff_file:
                    # Not the file we've copied to the gateway flash
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
                        # Set time on the remote device to keep keys in sync
                        if self.set_device_time(mtu, source.infuse_id):
                            # Upload the patch file
                            if self._single_diff:
                                self.run_file_copy(live, mtu, source)
                            else:
                                self.run_file_upload(live, mtu, source)

                except (ConnectionRefusedError, ConnectionAbortedError, TimeoutError):
                    self.state_update(live, "Scanning")

                if self.task is not None:
                    self.progress.remove_task(self.task)
                    self.task = None

                self.state_update(live, "Scanning")

    def close(self):
        try:
            if self._log is not None:
                self._log.close()
        finally:
            self._client.close()
