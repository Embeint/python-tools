#!/usr/bin/env python3

"""Save received TDFs in CSV files"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2026, Embeint Holdings Pty Ltd"

import sys
from pathlib import Path

from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseType
from infuse_iot.exporter import Exporter
from infuse_iot.socket_comms import (
    ClientNotificationEpacketReceived,
    LocalClient,
)
from infuse_iot.tdf import TDF
from infuse_iot.time import InfuseTime
from infuse_iot.util.argparse import ValidDir, add_server_port_parser


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--dir", '-d', type=ValidDir, default=Path("."), help="Directory to save CSV files to")
        parser.add_argument("--unix", action="store_true", help="Save timestamps as unix")
        add_server_port_parser(parser)

    def __init__(self, args):
        self._client = LocalClient(args.server_sock, 1.0)
        self._decoder = TDF()
        print(f"Exporting to {Path(args.dir)}")
        self._exporter = Exporter(Path(args.dir))
        self._time_format = str if args.unix else InfuseTime.utc_time_string_log
        self.args = args

    def run(self):
        if not self._client.comms_check():
            sys.exit("No communications gateway detected (infuse gateway/bt_native)")

        while True:
            msg = self._client.receive()
            if msg is None:
                continue
            if not isinstance(msg, ClientNotificationEpacketReceived):
                continue
            if msg.epacket.ptype != InfuseType.TDF:
                continue
            source = msg.epacket.route[0]

            for tdf in self._decoder.decode(msg.epacket.payload):
                filename = Path(f"{source.infuse_id:016x}_{tdf.name}.csv")
                lines = tdf.csv_lines(time_fmt=self._time_format)
                self._exporter.write_lines(filename, lines, header=tdf.csv_header)
