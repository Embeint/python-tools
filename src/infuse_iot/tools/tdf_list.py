#!/usr/bin/env python3

"""Display received TDFs in a list"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import time

import tabulate

from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseType
from infuse_iot.generated.tdf_base import TdfStructBase
from infuse_iot.socket_comms import (
    ClientNotificationEpacketReceived,
    LocalClient,
    default_multicast_address,
)
from infuse_iot.tdf import TDF
from infuse_iot.time import InfuseTime


class SubCommand(InfuseCommand):
    NAME = "tdf_list"
    HELP = "Display received TDFs in a list"
    DESCRIPTION = "Display received TDFs in a list"

    def __init__(self, _):
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._decoder = TDF()

    def run(self) -> None:
        while True:
            msg = self._client.receive()
            if msg is None:
                continue
            if not isinstance(msg, ClientNotificationEpacketReceived):
                continue
            if msg.epacket.ptype != InfuseType.TDF:
                continue
            source = msg.epacket.route[0]

            table: list[tuple[str | None, str | None, str, str, str]] = []

            for tdf in self._decoder.decode(msg.epacket.payload):
                t = tdf.data[-1]
                num = len(tdf.data)
                tdf_name: None | str = None
                time_str: None | str = None
                if num > 1:
                    tdf_name = f"{t.NAME}[{num - 1}]"
                else:
                    tdf_name = t.NAME
                if tdf.time is not None:
                    if tdf.period is None:
                        time_str = InfuseTime.utc_time_string(tdf.time)
                    else:
                        offset = (len(tdf.data) - 1) * tdf.period
                        time_str = InfuseTime.utc_time_string(tdf.time + offset)
                else:
                    if tdf.base_idx is not None:
                        time_str = f"IDX {tdf.base_idx}"
                    else:
                        time_str = InfuseTime.utc_time_string(time.time())

                for field in t.iter_fields():
                    if isinstance(field.val, list):
                        # Trailing VLA handling
                        if len(field.val) > 0 and isinstance(field.val[0], TdfStructBase):
                            for idx, val in enumerate(field.val):
                                for subfield in val.iter_fields(f"{field.name}[{idx}]"):
                                    table.append(
                                        (
                                            time_str,
                                            tdf_name,
                                            subfield.name,
                                            subfield.val_fmt(),
                                            subfield.postfix,
                                        )
                                    )
                                    tdf_name = None
                                    time_str = None
                        else:
                            table.append((time_str, tdf_name, f"{field.name}", field.val_fmt(), field.postfix))
                            tdf_name = None
                            time_str = None
                    else:
                        # Standard structs and sub-structs
                        table.append((time_str, tdf_name, field.name, field.val_fmt(), field.postfix))
                        tdf_name = None
                        time_str = None

            print(f"Infuse ID: {source.infuse_id:016x}")
            print(f"Interface: {source.interface.name}")
            print(f"  Address: {source.interface_address}")
            print(f"     RSSI: {source.rssi} dBm")
            print(tabulate.tabulate(table, tablefmt="simple"))
