#!/usr/bin/env python3

"""Display received TDFs in a list"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import tabulate

from infuse_iot.epacket import data_types
from infuse_iot.commands import InfuseCommand
from infuse_iot.socket_comms import LocalClient, default_multicast_address
from infuse_iot.tdf import TDF
from infuse_iot.time import InfuseTime

class tdf_list(InfuseCommand):
    HELP = "Display received TDFs in a list"
    DESCRIPTION = "Display received TDFs in a list"

    def add_parser(cls, parser):
        return

    def __init__(self, args):
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._decoder = TDF()

    def run(self):
        while True:
            msg = self._client.receive()
            if msg == None:
                continue
            if msg['pkt_type'] != data_types.TDF:
                continue
            decoded = self._decoder.decode(bytes.fromhex(msg['raw']))

            table = []

            for tdf in decoded:
                t = tdf['data'][-1]
                num = len(tdf['data'])
                if num > 1:
                    name = f'{t.name}[{num-1}]'
                else:
                    name = t.name

                for idx, (n, f, p) in enumerate(t.iter_fields()):
                    if idx == 0:
                        t = tdf['time'] if tdf['time'] is not None else 0
                        table.append([InfuseTime.utc_time_string(t), name, n, f, p])
                    else:
                        table.append([None, None, n, f, p])

            print(tabulate.tabulate(table, tablefmt='simple'))
