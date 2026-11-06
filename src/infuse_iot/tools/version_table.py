#!/usr/bin/env python3

"""Display the applications and versions of observed devices"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2026, Embeint Holdings Pty Ltd"

import sys
import time
from dataclasses import dataclass

from rich.live import Live
from rich.table import Table

from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseType
from infuse_iot.generated.tdf_definitions import readings
from infuse_iot.socket_comms import (
    ClientNotification,
    ClientNotificationEpacketReceived,
    ClientNotificationObservedDevices,
    GatewayRequestObservedDevices,
    LocalClient,
)
from infuse_iot.tdf import TDF
from infuse_iot.util.argparse import add_server_port_parser


@dataclass
class DeviceVersion:
    application_id: int
    application_version: str
    last_heard: float | None = None


def announce_version(announce: readings.announce | readings.announce_v2) -> str:
    v = announce.version
    return f"{v.major}.{v.minor}.{v.revision}+{v.build_num:08x}"


def version_sort_key(version: str) -> tuple:
    """Order `major.minor.revision+build` versions numerically"""
    try:
        release, build = version.split("+")
        major, minor, revision = (int(v) for v in release.split("."))
        return (0, major, minor, revision, int(build, 16))
    except ValueError:
        # Unexpected formats are ordered after valid versions
        return (1, version)


def format_age(last_heard: float | None, now: float) -> str:
    if last_heard is None:
        return "Unknown"
    age = max(int(now - last_heard), 0)
    if age < 60:
        return f"{age}s ago"
    if age < 3600:
        return f"{age // 60}m {age % 60:02d}s ago"
    return f"{age // 3600}h {(age % 3600) // 60:02d}m ago"


class VersionTable:
    """Application versions of observed devices"""

    def __init__(self, app_ids: list[int] | None = None):
        self._app_ids = set(app_ids) if app_ids else None
        self._decoder = TDF()
        self.devices: dict[int, DeviceVersion] = {}

    def _app_allowed(self, application_id: int) -> bool:
        return self._app_ids is None or application_id in self._app_ids

    def _update(self, infuse_id: int, application_id: int, version: str, last_heard: float | None):
        if not self._app_allowed(application_id):
            # Device may have changed to an application that is not displayed
            self.devices.pop(infuse_id, None)
            return
        dev = self.devices.get(infuse_id)
        if dev is None:
            self.devices[infuse_id] = DeviceVersion(application_id, version, last_heard)
            return
        dev.application_id = application_id
        dev.application_version = version
        if last_heard is not None and (dev.last_heard is None or last_heard > dev.last_heard):
            dev.last_heard = last_heard

    def known_devices(self, notification: ClientNotificationObservedDevices) -> None:
        """Merge the gateway's knowledge of devices into the table"""
        for infuse_id, info in notification.devices.items():
            if "application_id" not in info or "application_version" not in info:
                continue
            self._update(infuse_id, info["application_id"], info["application_version"], info.get("last_heard"))

    def epacket(self, notification: ClientNotificationEpacketReceived, now: float) -> None:
        """Update the table from a received packet"""
        source = notification.epacket.route[0].infuse_id
        if notification.epacket.ptype == InfuseType.TDF:
            for reading in self._decoder.decode(notification.epacket.payload):
                announce = reading.data[-1]
                if isinstance(announce, (readings.announce, readings.announce_v2)):
                    self._update(source, announce.application, announce_version(announce), now)
        if source in self.devices:
            self.devices[source].last_heard = now

    def handle(self, notification: ClientNotification | None, now: float) -> None:
        if isinstance(notification, ClientNotificationObservedDevices):
            self.known_devices(notification)
        elif isinstance(notification, ClientNotificationEpacketReceived):
            self.epacket(notification, now)

    def render(self, now: float) -> Table:
        table = Table(title=f"Observed Devices ({len(self.devices)})")
        table.add_column("Application")
        table.add_column("Version")
        table.add_column("Devices", justify="right")
        table.add_column("Last Heard", justify="right")

        # Number of devices and most recent activity for each application version
        groups: dict[tuple[int, str], tuple[int, float | None]] = {}
        for dev in self.devices.values():
            key = (dev.application_id, dev.application_version)
            count, last_heard = groups.get(key, (0, None))
            if dev.last_heard is not None and (last_heard is None or dev.last_heard > last_heard):
                last_heard = dev.last_heard
            groups[key] = (count + 1, last_heard)

        for (application_id, version), (count, last_heard) in sorted(
            groups.items(), key=lambda item: (item[0][0], version_sort_key(item[0][1]))
        ):
            table.add_row(f"0x{application_id:08x}", version, str(count), format_age(last_heard, now))
        return table


class SubCommand(InfuseCommand):
    KNOWN_DEVICES_TIMEOUT = 2.0

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--app", type=lambda x: int(x, 0), action="append", help="Limit displayed devices by application ID"
        )
        add_server_port_parser(parser)

    def __init__(self, args):
        self._client = LocalClient(args.server_sock, 1.0)
        self._table = VersionTable(args.app)

    def _request_known_devices(self) -> None:
        """Populate the table with the devices already known to the gateway"""
        self._client.send(GatewayRequestObservedDevices())
        expiry = time.monotonic() + self.KNOWN_DEVICES_TIMEOUT
        while (remaining := expiry - time.monotonic()) > 0:
            rsp = self._client.receive(timeout=remaining)
            self._table.handle(rsp, time.time())
            if isinstance(rsp, ClientNotificationObservedDevices):
                if not any("application_id" in info for info in rsp.devices.values()):
                    # Gateways running older versions of this package do not report applications
                    print("Gateway reported no application versions, waiting for device announcements", file=sys.stderr)
                return
        print("Gateway did not report known devices, waiting for device announcements", file=sys.stderr)

    def run(self) -> None:
        if not self._client.comms_check():
            sys.exit("No communications gateway detected (infuse gateway/bt_native)")
        self._request_known_devices()

        with Live(self._table.render(time.time()), refresh_per_second=4) as live:
            while True:
                # Receive times out every second, refreshing the last heard times
                msg = self._client.receive()
                now = time.time()
                self._table.handle(msg, now)
                live.update(self._table.render(now))

    def close(self):
        self._client.close()
