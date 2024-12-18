#!/usr/bin/env python3

import ctypes
import os

import tabulate

import infuse_iot.generated.rpc_definitions as rpc_defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.tdf import tdf_definitions as defs
from infuse_iot.util.ctypes import VLACompatLittleEndianStruct


class zbus_channel_state(InfuseRpcCommand, rpc_defs.zbus_channel_state):
    class response(VLACompatLittleEndianStruct):
        _fields_ = [
            ("pub_timestamp", ctypes.c_uint64),
            ("pub_count", ctypes.c_uint32),
            ("pub_period_ms", ctypes.c_uint32),
        ]
        vla_field = ("data", 0 * ctypes.c_byte)

    class BatteryChannel:
        id = 0x43210000
        data = defs.readings.battery_state

    class AmbeintEnvChannel(ctypes.LittleEndianStructure):
        id = 0x43210001
        data = defs.readings.ambient_temp_pres_hum

    class LocationChannel(ctypes.LittleEndianStructure):
        id = 0x43210004
        data = defs.readings.gcs_wgs84_llha

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
        group.add_argument(
            "--location",
            dest="channel",
            action="store_const",
            const=cls.LocationChannel,
            help="Location channel",
        )

    def __init__(self, args):
        self._channel = args.channel

    def request_struct(self):
        return self.request(self._channel.id)

    def request_json(self):
        return {"channel_id": str(self._channel.id)}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query channel ({os.strerror(-return_code)})")
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
            for field in data.iter_fields():
                table.append([field.name, field.val_fmt(), field.postfix])
            print(tabulate.tabulate(table, tablefmt="simple"))
        except Exception as _:
            print(f"\t          Data: {data_bytes.hex()}")
