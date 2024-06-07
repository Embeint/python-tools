#!/usr/bin/env python3

"""Display received TDFs in a list"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import tabulate

from infuse_iot.epacket import ePacket
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
            if msg.ptype != ePacket.types.TDF:
                continue
            decoded = self._decoder.decode(msg.payload)

            table = []

            for tdf in decoded:
                t = tdf["data"][-1]
                num = len(tdf["data"])
                if num > 1:
                    name = f"{t.name}[{num-1}]"
                else:
                    name = t.name

                for idx, (n, f, p) in enumerate(t.iter_fields()):
                    if idx == 0:
                        t = tdf["time"] if tdf["time"] is not None else 0
                        table.append([InfuseTime.utc_time_string(t), name, n, f, p])
                    else:
                        table.append([None, None, n, f, p])

            print(tabulate.tabulate(table, tablefmt="simple"))
