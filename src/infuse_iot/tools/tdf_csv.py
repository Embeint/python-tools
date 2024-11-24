#!/usr/bin/env python3

"""Save received TDFs in CSV files"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import os
import time

from infuse_iot.common import InfuseType
from infuse_iot.commands import InfuseCommand
from infuse_iot.socket_comms import LocalClient, default_multicast_address
from infuse_iot.tdf import TDF
from infuse_iot.time import InfuseTime


class SubCommand(InfuseCommand):
    NAME = "tdf_csv"
    HELP = "Save received TDFs in CSV files"
    DESCRIPTION = "Save received TDFs in CSV files"

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--unix", action="store_true", help="Save timestamps as unix"
        )

    def __init__(self, args):
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._decoder = TDF()
        self.args = args

    def run(self):
        files = {}

        while True:
            msg = self._client.receive()
            if msg is None:
                continue
            if msg.ptype != InfuseType.TDF:
                continue
            source = msg.route[0]

            for tdf in self._decoder.decode(msg.payload):
                # Construct reading strings
                lines = []
                reading_time = tdf.time
                for reading in tdf.data:
                    if self.args.unix:
                        time_func = str
                    else:
                        time_func = InfuseTime.utc_time_string_log

                    if reading_time is None:
                        # Log with local time
                        time_str = time_func(time.time())
                    else:
                        time_str = time_func(reading_time)
                    line = (
                        time_str
                        + ","
                        + ",".join([str(r[1]) for r in reading.iter_fields()])
                    )
                    lines.append(line)
                    if tdf.period is not None:
                        reading_time += tdf.period

                # Handle file creation/opening
                first = tdf.data[0]
                filename = f"{source.infuse_id:016x}_{first.name}.csv"
                if filename not in files:
                    if os.path.exists(filename):
                        print(f"Appending to existing {filename}")
                        files[filename] = open(filename, "a", encoding="utf-8")
                    else:
                        print(f"Opening new {filename}")
                        files[filename] = open(filename, "w", encoding="utf-8")
                        headings = "time," + ",".join(
                            [r[0] for r in first.iter_fields()]
                        )
                        files[filename].write(headings + os.linesep)

                # Write line to file then flush
                for line in lines:
                    files[filename].write(line + os.linesep)
                files[filename].flush()
