#!/usr/bin/env python3

"""Synchronise data logger state from remote devices"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2025, Embeint Holdings Pty Ltd"

import binascii
import glob
import os
import pathlib

from rich.live import Live
from rich.progress import (
    DownloadColumn,
    Progress,
    TransferSpeedColumn,
)
from rich.status import Status
from rich.table import Table

from infuse_iot.commands import InfuseCommand
from infuse_iot.definitions.rpc import data_logger_read, rpc_enum_data_logger
from infuse_iot.epacket.packet import Auth
from infuse_iot.generated.tdf_definitions import readings
from infuse_iot.rpc_client import RpcClient
from infuse_iot.socket_comms import (
    GatewayRequestConnectionRequest,
    LocalClient,
    default_multicast_address,
)
from infuse_iot.util.argparse import ValidDir


class DeviceState:
    BLOCK_SIZE = 512

    def __init__(self, path: pathlib.Path):
        self.path = path
        self.on_disk: int = 0
        self.on_device: int | None = None
        self.downloaded: int = 0
        if not self.path.exists():
            self.path.touch()
        else:
            self.on_disk = os.path.getsize(self.path) // self.BLOCK_SIZE

    def observe(self, announce: readings.announce):
        self.on_device = announce.blocks

    def append_data(self, data: bytes):
        assert len(data) % self.BLOCK_SIZE == 0
        new_blocks = len(data) // self.BLOCK_SIZE

        with self.path.open("+ba") as f:
            f.write(data)
            self.on_disk += new_blocks
            self.downloaded += new_blocks


class SubCommand(InfuseCommand):
    NAME = "data_logger_sync"
    HELP = "Synchronise data logger state from remote devices"
    DESCRIPTION = "Synchronise data logger state from remote devices"

    def __init__(self, args):
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._min_rssi: int | None = args.rssi
        self._app = args.app
        self._out = args.out
        self._blocks_max = args.blocks
        self._logger = args.logger
        self._device_state: dict[int, DeviceState] = {}

        self.bytes_to_read = 0
        self.pending_bytes = b""
        self.task = None
        self.state = "Scanning"
        self.progress = Progress(
            *Progress.get_default_columns(),
            DownloadColumn(),
            TransferSpeedColumn(),
        )

        for file in glob.glob(f"{self._out}/*_{self._logger}.bin"):
            file_path = pathlib.Path(file)
            name_parts = file_path.name.split("_")
            device_id = int(name_parts[0], 16)

            self._device_state[device_id] = DeviceState(file_path)

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--out", "-o", type=ValidDir, required=True, help="Output folder for synced data")
        parser.add_argument("--blocks", "-b", type=int, default=500, help="Number of blocks to download per connection")
        parser.add_argument("--app", "-a", type=lambda x: int(x, 0), help="Application ID to limit sync to")
        parser.add_argument("--rssi", "-r", type=int, help="Minimum RSSI to attempt downloading data")
        logger_group = parser.add_mutually_exclusive_group(required=True)
        logger_group.add_argument(
            "--onboard",
            dest="logger",
            action="store_const",
            const=rpc_enum_data_logger.FLASH_ONBOARD,
            help="Synchronise onboard loggers",
        )
        logger_group.add_argument(
            "--removable",
            dest="logger",
            action="store_const",
            const=rpc_enum_data_logger.FLASH_REMOVABLE,
            help="Synchronise removable loggers",
        )

    def progress_table(self):
        table = Table()
        table.add_column("Device ID")
        table.add_column("On Disk", justify="right")
        table.add_column("On Device", justify="right")
        table.add_column("Downloaded", justify="right")
        for device, state in self._device_state.items():
            on_device = str(state.on_device) if state.on_device is not None else "?"
            percent = f"{100 * state.on_disk / state.on_device:.0f}" if state.on_device is not None else "?"
            table.add_row(f"{device:016x}", f"{state.on_disk} ({percent:>3s}%)", on_device, str(state.downloaded))

        meta = Table(box=None)
        meta.add_column()
        meta.add_row(table)
        meta.add_row(Status(self.state))
        meta.add_row(self.progress)

        return meta

    def state_update(self, live: Live, state: str):
        self.state = state
        live.update(self.progress_table())

    def data_progress_cb(self, offset: int, payload: bytes):
        if self.task is None:
            self.state = "Reading data logger"
            self.task = self.progress.add_task("", total=self.bytes_to_read)
        self.pending_bytes += payload
        self.progress.update(self.task, completed=offset)

    def handle_sync(self, live: Live, device_id: int, state: DeviceState):
        self.state_update(live, f"Connecting to {device_id:016X}")
        assert state.on_device is not None
        try:
            with self._client.connection(device_id, GatewayRequestConnectionRequest.DataType.COMMAND) as mtu:
                self.state_update(live, f"Downloading blocks from {device_id:016X}")
                rpc_client = RpcClient(self._client, mtu, device_id)
                blocks_pending = state.on_device - state.on_disk
                blocks_to_read = min(blocks_pending, self._blocks_max)
                last_block = state.on_disk + blocks_to_read - 1
                self.bytes_to_read = 512 * blocks_to_read
                params = data_logger_read.request(self._logger, state.on_disk, last_block)
                self.pending_bytes = b""
                hdr, rsp = rpc_client.run_data_recv_cmd(
                    data_logger_read.COMMAND_ID,
                    Auth.DEVICE,
                    bytes(params),
                    self.bytes_to_read,
                    self.data_progress_cb,
                    data_logger_read.response.from_buffer_copy,
                )
                if hdr.return_code == 0:
                    assert isinstance(rsp, data_logger_read.response)
                    if rsp.sent_len == len(self.pending_bytes) and rsp.sent_crc == binascii.crc32(self.pending_bytes):
                        state.append_data(self.pending_bytes)
                if self.task is not None:
                    self.progress.remove_task(self.task)
                    self.task = None

        except ConnectionRefusedError:
            self.state_update(live, "Scanning")
        except ConnectionAbortedError:
            self.state_update(live, "Scanning")

    def run(self):
        with Live(self.progress_table(), refresh_per_second=4) as live:
            for source, announce in self._client.observe_announce():
                self.state_update(live, "Scanning")
                if self._app and announce.application != self._app:
                    continue
                # Don't consider announce packets that don't contain information about the requested logger
                req_removable = self._logger == rpc_enum_data_logger.FLASH_REMOVABLE
                announce_is_removable = announce.flags & 0x01
                if req_removable != announce_is_removable:
                    continue

                if source.infuse_id not in self._device_state:
                    output_file = self._out / f"{source.infuse_id:016x}_{self._logger}.bin"
                    self._device_state[source.infuse_id] = DeviceState(output_file)
                state = self._device_state[source.infuse_id]
                state.observe(announce)

                # Is signal strong enough to connect?
                if self._min_rssi and source.rssi < self._min_rssi:
                    continue

                assert state.on_device is not None
                if state.on_disk < state.on_device:
                    self.handle_sync(live, source.infuse_id, state)
