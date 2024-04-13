#!/usr/bin/env python3

"""Save received TDFs in CSV files"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import os

from infuse_iot.epacket import data_types
from infuse_iot.commands import InfuseCommand
from infuse_iot.socket_comms import LocalClient, default_multicast_address
from infuse_iot.tdf import TDF
from infuse_iot.time import InfuseTime

class tdf_csv(InfuseCommand):
    HELP = "Save received TDFs in CSV files"
    DESCRIPTION = "Save received TDFs in CSV files"

    def add_parser(cls, parser):
        return

    def __init__(self, args):
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._decoder = TDF()

    def run(self):
        files = {}

        while True:
            msg = self._client.receive()
            if msg == None:
                continue
            if msg['pkt_type'] != data_types.TDF:
                continue
            decoded = self._decoder.decode(bytes.fromhex(msg['raw']))

            for tdf in decoded:

                # Construct reading strings
                lines = []
                reading_time = tdf['time']
                for reading in tdf['data']:
                    time_str = InfuseTime.utc_time_string_log(reading_time)
                    line = time_str + ',' + ','.join([str(r[1]) for r in reading.iter_fields()])
                    lines.append(line)
                    if 'period' in tdf:
                        reading_time += tdf['period']

                # Handle file creation/opening
                first = tdf['data'][0]
                filename = f"{msg['device']}_{first.name}.csv"
                if filename not in files:
                    if os.path.exists(filename):
                        print(f"Appending to existing {filename}")
                        files[filename] = open(filename, 'a')
                    else:
                        print(f"Opening new {filename}")
                        files[filename] = open(filename, 'w')
                        headings = 'time,' + ','.join([r[0] for r in first.iter_fields()])
                        files[filename].write(headings + os.linesep)

                # Write line to file then flush
                for line in lines:
                    files[filename].write(line + os.linesep)
                files[filename].flush()
