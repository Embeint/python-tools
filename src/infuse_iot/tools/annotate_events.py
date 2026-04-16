#!/usr/bin/env python3

"""Annotate events on Infuse Tags"""

__author__ = "Aeyohan Furtado"
__copyright__ = "Copyright 2026, Embeint Holdings Pty Ltd"

import enum
import json
import signal
import sys
from datetime import datetime
from pathlib import Path
from threading import Thread

from rich.live import Live
from rich.status import Status

from infuse_iot.commands import InfuseCommand
from infuse_iot.epacket.packet import Auth
from infuse_iot.generated.rpc_definitions import annotate, rpc_enum_data_logger, time_get, time_set
from infuse_iot.rpc_client import RpcClient
from infuse_iot.rpc_wrappers.annotate import annotate as annotate_wrapper
from infuse_iot.socket_comms import (
    ClientNotificationConnectionDropped,
    GatewayRequestConnectionRequest,
    LocalClient,
    default_multicast_address,
)
from infuse_iot.time import InfuseTime
from infuse_iot.util.argparse import ValidFile
from infuse_iot.util.console import choose_one
from infuse_iot.zephyr.errno import errno


class LabelType(enum.Enum):
    CUSTOM = "custom"
    MANUAL = "manual"

class TimeCheckType(enum.Enum):
    NONE = "none"
    FORCE = "force"
    AUTO = "auto"
    DEFAULT = "default"

class SubCommand(InfuseCommand):
    NAME = "annotate_events"
    HELP = "Annotate events on Infuse Tags"
    DESCRIPTION = "Save labelled event annotations live on Infuse Tags"

    _label_type: LabelType | Path
    _labels: list[str]
    _time_check: TimeCheckType
    _tag_unix_time: float | None
    _time_of_sync: datetime | None

    @classmethod
    def add_parser(cls, parser):
        # Logger Selection parameters.
        logger_parser = parser.add_mutually_exclusive_group(required=True)
        logger_parser.add_argument("--onboard", dest="logger", action="store_const",
                              const=rpc_enum_data_logger.FLASH_ONBOARD)
        logger_parser.add_argument("--external", dest="logger", action="store_const",
                              const=rpc_enum_data_logger.FLASH_REMOVABLE)
        logger_parser.add_argument("--logger", "-l", type=annotate_wrapper.parse_logger,
                              help="TDF Data Logger to write the event to")

        # Label selection parameters.
        label_group = parser.add_mutually_exclusive_group(required=True)
        label_group.add_argument(
            "--preset-labels", "-p", dest="labels", type=ValidFile,
            help="JSON file containing labels"
        )
        label_group.add_argument(
            "--custom-labels", "-c", dest="labels", action="store_const", const=LabelType.CUSTOM,
            help="Specify custom labels at runtime"
        )
        label_group.add_argument(
            "--manual-labels", "-m", dest="labels", action="store_const", const=LabelType.MANUAL,
            help="Manually enter labels for each event"
        )

        # Time sync parameters.
        time_group = parser.add_mutually_exclusive_group()
        time_group.add_argument(
            "--force-time", "-f", dest="time", action="store_const", const=TimeCheckType.FORCE,
            help="Forcibly update the tag's time before writing annotations"
        )
        time_group.add_argument(
            "--auto-time", "-a", dest="time", action="store_const", const=TimeCheckType.AUTO,
            help="Automatically update the tag's time if it is not current"
        )
        time_group.add_argument(
            "--skip-time", "-s", dest="time", action="store_const", const=TimeCheckType.NONE,
            help="Do not update the tag's time before writing annotations"
        )

        parser.add_argument("--id", type=lambda x: int(x, 0), help="Device to log events to")

    def __init__(self, args):
        self._label_type = args.labels
        self._time_check = args.time or TimeCheckType.DEFAULT

        if isinstance(self._label_type, Path):
            with self._label_type.open() as f:
                try:
                    # Use a dict to remove duplicates while preserving order (set does not).
                    self._labels = list({v: v for v in json.load(f)}.values())
                    for label in self._labels:
                        # Ensure each label is a string.
                        if not isinstance(label, str):
                            sys.exit(f"Labels must be strings. '{label}' in config file is not.")
                except json.JSONDecodeError as e:
                    sys.exit(f"Failed to parse labels from '{self._label_type}': {e}")
        elif self._label_type == LabelType.CUSTOM:
            # Prompt user for labels.
            print("Enter events label, one per line (or leave empty to finish):")
            self._labels = []
            while True:
                label = input("> ").strip()
                if not label:
                    if not self._labels:
                        print("At least one label must be entered")
                        continue
                    break
                self._labels.append(label)
        else:
            # Manual label entry mode, no pre-defined labels.
            self._labels = []

        self._logger: rpc_enum_data_logger = args.logger
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._device_id = args.id
        self.rpc_client: RpcClient | None = None
        self.connected = False
        self.complete = False

    def get_tags_current_gps_time(self) -> float:
        now = datetime.now()
        assert self._time_of_sync is not None
        assert self._tag_unix_time is not None
        elapsed = now - self._time_of_sync
        return InfuseTime.gps_seconds_from_unix(int(self._tag_unix_time + elapsed.total_seconds()))

    def load_tag_time(self):
        params = time_get.request()
        sync_request_sent = datetime.now()
        assert self.rpc_client is not None
        hdr, rsp = self.rpc_client.run_standard_cmd(
            time_get.COMMAND_ID,
            Auth.DEVICE,
            bytes(params),
            time_get.response.from_buffer_copy
        )
        sync_response_received = datetime.now()

        if hdr is None:
            raise RuntimeError("Failed to get time from tag")
        if hdr.return_code != 0:
            raise RuntimeError(f"Error getting time from tag ({hdr.return_code}): "
                               f"{errno.strerror(-hdr.return_code)}")

        assert isinstance(rsp, time_get.response)
        time_response: time_get.response = rsp
        self._tag_unix_time = InfuseTime.unix_time_from_epoch(time_response.epoch_time)
        self._time_of_sync = sync_request_sent + (sync_response_received - sync_request_sent) / 2

    def check_tag_needs_sync(self) -> bool:
        assert self._tag_unix_time is not None
        assert self._time_of_sync is not None
        if self._time_check in [TimeCheckType.AUTO, TimeCheckType.DEFAULT]:
            # Update the tag time if it exceeds 1 minute of the current time.
            tag_datetime_now = datetime.fromtimestamp(self._tag_unix_time)
            update = (self._time_of_sync - tag_datetime_now).total_seconds() > 60
            if update and self._time_check == TimeCheckType.DEFAULT:
                # Tag is out of sync with current time. Check if it needs to be updated.
                try:
                    selection, _ = choose_one(
                        f"Tag's clock is out of sync. Update the tag's time?\n"
                        f"Tag:    {tag_datetime_now}\n"
                        f"System: {self._time_of_sync}",
                        ["Yes", "No"]
                    )
                    update = not bool(selection)
                except IndexError:
                    update = False
            return update
        return self._time_check == TimeCheckType.FORCE

    def sync_tag_time(self):
        # Update the tag's time to the current time.
        now = datetime.now().timestamp()
        params = time_set.request(
            InfuseTime.epoch_time_from_unix(now)
        )

        sync_request_sent = datetime.now()
        assert self.rpc_client is not None
        hdr, _ = self.rpc_client.run_standard_cmd(
            time_set.COMMAND_ID,
            Auth.DEVICE,
            bytes(params),
            time_set.response.from_buffer_copy
        )

        sync_response_received = datetime.now()
        if hdr is None:
            raise RuntimeError("Failed to set time on tag")
        if hdr.return_code != 0:
            raise RuntimeError(f"Error setting time on tag ({hdr.return_code}): "
                               f"{errno.strerror(-hdr.return_code)}")

        # Update sync point to reflect new time on tag, assuming the tag's time doesn't change for
        # the duration of the connection.
        self._time_of_sync = sync_request_sent + (sync_response_received - sync_request_sent) / 2
        self._tag_unix_time = now

    def draw_connecting(self):
        return Status(f"Connecting to {self._device_id:016x}...\n")

    def query_label(self):
        if self._label_type == LabelType.MANUAL:
            # Prompt user for label for each event
            try:
                label = input("Enter event label (or leave empty to exit): ").strip()
            except KeyboardInterrupt as e:
                # End current line and exit gracefully on Ctrl+C
                print()
                raise e
            if not label:
                return None
        else:
            # Let the user select from their predefined labels
            try:
                idx, label = choose_one("Select an event:", [*self._labels, "Exit"])
            except IndexError:
                return None
            if idx == len(self._labels):
                # User selected "Exit"
                return None
        return label

    def connection_listener(self):
        # Listen for incoming events in case the connection is dropped
        while not self.complete:
            # Wait till connection is established. This prevents dropping the connected event.
            if not self.connected:
                continue
            evt = self._client.receive()
            if evt is None:
                continue
            if isinstance(evt, ClientNotificationConnectionDropped) and \
                    evt.infuse_id == self._device_id and not self.complete:
                # Ensure the connection wasn't caused by the script existing.
                print("\n" * (len(self._labels)))  # Clear any pending input lines
                print(f"Lost connection to {self._device_id:016x}")
                self.complete = True
                # Need to use SIGTERM to interrupt the main thread's input() call
                # Couldn't get KeyboardInterrupt to trigger on main thread.
                signal.raise_signal(signal.SIGTERM)

    def run(self):
        if not self._client.comms_check():
            sys.exit("No communications gateway detected (infuse gateway/bt_native)")

        cl = Thread(target=self.connection_listener, daemon=True)
        cl.start()

        while not self.complete:
            with Live(self.draw_connecting(), refresh_per_second=4) as live, \
                self._client.connection(
                    self._device_id, GatewayRequestConnectionRequest.DataType.COMMAND
                ) as mtu:
                self.connected = True
                live.transient = True
                live.stop()
                print(f"Connected to {self._device_id:016x}")
                self.rpc_client = RpcClient(self._client, mtu, self._device_id)

                # On connection, check the tag's current time & sync if required.
                self.load_tag_time()
                if self.check_tag_needs_sync():
                    self.sync_tag_time()

                while True:
                    label = self.query_label()
                    if label is None:
                        self.complete = True
                        break

                    timestamp = self.get_tags_current_gps_time()
                    now = datetime.now()
                    params = annotate_wrapper.annotate_factory(self._logger, timestamp, label)

                    hdr, _ = self.rpc_client.run_standard_cmd(
                        annotate.COMMAND_ID,
                        Auth.DEVICE,
                        bytes(params),
                        annotate.response.from_buffer_copy
                    )

                    if hdr is None:
                        print("Failed to send annotation event to tag")
                        continue
                    annotate_wrapper.handle_response_generic(
                        hdr.return_code, self._logger, now, label
                    )
