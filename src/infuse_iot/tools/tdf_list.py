#!/usr/bin/env python3

"""Display received TDFs in a list"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import sys
import time

import tabulate

from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseType
from infuse_iot.generated.tdf_base import TdfReadingBase, TdfStructBase
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

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--array-all", action="store_true", help="Display all array values, not just the last")
        parser.add_argument(
            "--id", type=lambda x: int(x, 0), action="append", default=[], help="Limit displayed TDFs by device ID"
        )

    def __init__(self, args):
        self._client = LocalClient(default_multicast_address(), 1.0)
        self._decoder = TDF()
        self._array_all = args.array_all
        self._ids = args.id

    def append_tdf(
        self,
        table: list[tuple[str | None, str | None, str, str, str]],
        name: str | None,
        time: str | None,
        tdf: TdfReadingBase,
    ):
        for field in tdf.iter_fields():
            if isinstance(field.val, list):
                # Trailing VLA handling
                if len(field.val) > 0 and isinstance(field.val[0], TdfStructBase):
                    for idx, val in enumerate(field.val):
                        for subfield in val.iter_fields(f"{field.name}[{idx}]"):
                            table.append(
                                (
                                    time,
                                    name,
                                    subfield.name,
                                    subfield.val_fmt(),
                                    subfield.postfix,
                                )
                            )
                            name = None
                            time = None
                else:
                    table.append((time, name, f"{field.name}", field.val_fmt(), field.postfix))
                    name = None
                    time = None
            else:
                # Standard structs and sub-structs
                table.append((time, name, field.name, field.val_fmt(), field.postfix))
                name = None
                time = None

    def append_readings(self, table: list[tuple[str | None, str | None, str, str, str]], tdf: TDF.Reading):
        num = len(tdf.data)
        iter_start = 0 if self._array_all else -1

        for idx, t in enumerate(tdf.data[iter_start:]):
            tdf_name: None | str = None
            time_str: None | str = None
            tdf_offset = idx if self._array_all else num - 1

            if num > 1:
                tdf_name = f"{t.NAME}[{tdf_offset}]"
            else:
                tdf_name = t.NAME
            if tdf.time is not None:
                if tdf.period is None:
                    time_str = InfuseTime.utc_time_string(tdf.time)
                else:
                    time_offset = tdf_offset * tdf.period
                    time_str = InfuseTime.utc_time_string(tdf.time + time_offset)
            else:
                if tdf.base_idx is not None:
                    time_str = f"IDX {tdf.base_idx}"
                else:
                    time_str = InfuseTime.utc_time_string(time.time())

            self.append_tdf(table, tdf_name, time_str, t)

    def run(self) -> None:
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

            if len(self._ids) > 0 and source.infuse_id not in self._ids:
                continue

            table: list[tuple[str | None, str | None, str, str, str]] = []

            tdf: TDF.Reading
            for tdf in self._decoder.decode(msg.epacket.payload):
                self.append_readings(table, tdf)

            print(f"Infuse ID: 0x{source.infuse_id:016x}")
            print(f"Interface: {source.interface.name}")
            print(f"  Address: {source.interface_address}")
            print(f"     RSSI: {source.rssi} dBm")
            print(tabulate.tabulate(table, tablefmt="simple"))
