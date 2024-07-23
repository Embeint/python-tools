#!/usr/bin/env python3

import ctypes
import tabulate

from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.tdf import tdf_definitions as defs


class zbus_channel_state(InfuseRpcCommand):
    HELP = "Current state of zbus channel"
    DESCRIPTION = "Current state of zbus channel"
    COMMAND_ID = 8

    class request(ctypes.LittleEndianStructure):
        _fields_ = [
            ("channel_id", ctypes.c_uint32),
        ]
        _pack_ = 1

    class response(InfuseRpcCommand.VariableSizeResponse):
        base_fields = [
            ("pub_timestamp", ctypes.c_uint64),
            ("pub_count", ctypes.c_uint32),
            ("pub_period_ms", ctypes.c_uint32),
        ]
        var_name = "data"
        var_type = ctypes.c_byte

    class BatteryChannel:
        id = 0x43210000
        data = defs.readings.battery_state

    class AmbeintEnvChannel(ctypes.LittleEndianStructure):
        id = 0x43210001
        data = defs.readings.ambient_temp_pres_hum

    @classmethod
    def add_parser(cls, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument(
            "--battery",
            dest="channel",
            action="store_const",
            const=cls.BatteryChannel,
            help="Battery channel",
        )
        group.add_argument(
            "--ambient-env",
            dest="channel",
            action="store_const",
            const=cls.AmbeintEnvChannel,
            help="Ambient environmental channel",
        )

    def __init__(self, args):
        self._channel = args.channel

    def request_struct(self):
        return self.request(self._channel.id)

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query channel ({return_code})")
            return

        from infuse_iot.time import InfuseTime

        pub_time = InfuseTime.unix_time_from_epoch(response.pub_timestamp)
        data_bytes = bytes(response.data)

        print(f"\t  Publish time: {InfuseTime.utc_time_string(pub_time)}")
        print(f"\t Publish count: {response.pub_count}")
        print(f"\tPublish period: {response.pub_period_ms} ms")
        try:
            data = self._channel.data.from_buffer_copy(data_bytes)
            table = []
            for n, f, p in data.iter_fields():
                table.append([n, f, p])
            print(tabulate.tabulate(table, tablefmt="simple"))
        except Exception as _:
            print(f"\t          Data: {data_bytes.hex()}")
