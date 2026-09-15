#!/usr/bin/env python3

"""Connect to remote Bluetooth device serial logs"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2026, Embeint Holdings Pty Ltd"

import sys
from argparse import ArgumentError
from pathlib import Path

from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseType
from infuse_iot.epacket import interface
from infuse_iot.exporter import Exporter
from infuse_iot.socket_comms import (
    ClientNotificationConnectionDropped,
    ClientNotificationEpacketReceived,
    GatewayRequestConnectionRequest,
    LocalClient,
)
from infuse_iot.tdf import TDF
from infuse_iot.time import InfuseTime
from infuse_iot.util.argparse import InfuseDeviceId, ValidDir, add_server_port_parser
from infuse_iot.util.console import Console


class SubCommand(InfuseCommand):
    def __init__(self, args):
        self._client = LocalClient(args.server_sock, 1.0)
        self._decoder = TDF()
        self._id = args.id
        self._data = args.data
        self._conn_timeout = args.conn_timeout
        self._exporter = Exporter(Path(args.csv)) if args.csv else None
        self._time_format = str if args.unix else InfuseTime.utc_time_string_log
        self._files = {}

        if args.csv and not self._data:
            raise ArgumentError(None, "Cannot log CSV export without subscribing to the data characteristic"
                                "(`--data`)")

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--id", type=InfuseDeviceId, required=True, help="Infuse ID to receive logs for")
        parser.add_argument("--data", action="store_true", help="Subscribe to the data characteristic as well")
        parser.add_argument("--csv", type=ValidDir, help="Save received TDFs from the data characteristic to CSV files"
                            " in the specified folder")
        parser.add_argument("--unix", action="store_true", help="Save timestamps as unix")
        parser.add_argument(
            "--conn-timeout", type=int, default=10000, help="Timeout to wait for a connection to the device (ms)"
        )
        add_server_port_parser(parser)

    def run(self):
        if not self._client.comms_check():
            sys.exit("No communications gateway detected (infuse gateway/bt_native)")

        try:
            types = GatewayRequestConnectionRequest.DataType.LOGGING
            if self._data:
                types |= GatewayRequestConnectionRequest.DataType.DATA
            with self._client.connection(self._id, types, self._conn_timeout) as _:
                Console.log_info(f"Connected to {self._id:016x} ({types.name})")
                while True:
                    evt = self._client.receive()
                    if evt is None:
                        continue
                    if isinstance(evt, ClientNotificationConnectionDropped):
                        Console.log_error(f"Connection to {self._id:016x} lost")
                        break
                    if not isinstance(evt, ClientNotificationEpacketReceived):
                        continue
                    source = evt.epacket.route[0]
                    if source.infuse_id != self._id:
                        continue
                    if source.interface != interface.ID.BT_CENTRAL:
                        continue

                    if evt.epacket.ptype == InfuseType.SERIAL_LOG:
                        print(evt.epacket.payload.decode("utf-8"), end="")
                    if evt.epacket.ptype == InfuseType.TDF:
                        for tdf in self._decoder.decode(evt.epacket.payload):
                            if self._exporter:
                                filename = Path(f"{source.infuse_id:016x}_{tdf.name}.csv")
                                lines = tdf.csv_lines(time_fmt=self._time_format)
                                self._exporter.write_lines(filename, lines, header=tdf.csv_header)

                            t = tdf.data[-1]
                            t_str = f"{tdf.time:.3f}" if tdf.time else "N/A"
                            if len(tdf.data) > 1:
                                print(f"{t_str} TDF: {t.NAME}[{len(tdf.data)}]")
                            else:
                                print(f"{t_str} TDF: {t.NAME}")

        except KeyboardInterrupt:
            print(f"Disconnecting from {self._id:016x}")
        except ConnectionRefusedError:
            print(f"Unable to connect to {self._id:016x}")
