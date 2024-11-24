#!/usr/bin/env python3

"""Display received TDFs in a list"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import tabulate

from infuse_iot.common import InfuseType
from infuse_iot.commands import InfuseCommand
from infuse_iot.socket_comms import LocalClient, default_multicast_address
from infuse_iot.tdf import TDF
from infuse_iot.time import InfuseTime


class SubCommand(InfuseCommand):
    NAME = "tdf_list"
    HELP = "Display received TDFs in a list"
    DESCRIPTION = "Display received TDFs in a list"

    def __init__(self, _):
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._decoder = TDF()

    def run(self):
        while True:
            msg = self._client.receive()
            if msg is None:
                continue
            if msg.ptype != InfuseType.TDF:
                continue
            source = msg.route[0]

            table = []

            for tdf in self._decoder.decode(msg.payload):
                t = tdf.data[-1]
                num = len(tdf.data)
                if num > 1:
                    name = f"{t.name}[{num-1}]"
                else:
                    name = t.name

                for idx, (n, f, p, d) in enumerate(t.iter_fields()):
                    f = d.format(f)
                    if idx == 0:
                        if tdf.time is not None:
                            if tdf.period is None:
                                t = ""
                            else:
                                offset = (len(tdf.data) - 1) * tdf.period
                                t = InfuseTime.utc_time_string(tdf.time + offset)
                        else:
                            t = "N/A"
                        table.append([t, name, n, f, p])
                    else:
                        table.append([None, None, n, f, p])

            print(f"Infuse ID: {source.infuse_id:016x}")
            print(f"Interface: {source.interface.name}")
            print(f"  Address: {source.interface_address}")
            print(f"     RSSI: {source.rssi} dBm")
            print(tabulate.tabulate(table, tablefmt="simple"))
