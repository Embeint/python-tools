#!/usr/bin/env python3

import ctypes

import tabulate

from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.definitions import rpc as rpc_defs
from infuse_iot.definitions import tdf as tdf_defs
from infuse_iot.util.ctypes import VLACompatLittleEndianStruct
from infuse_iot.zephyr.errno import errno


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
        data = tdf_defs.readings.battery_state

    class AmbeintEnvChannel(ctypes.LittleEndianStructure):
        id = 0x43210001
        data = tdf_defs.readings.ambient_temp_pres_hum

    class ImuChannel(ctypes.LittleEndianStructure):
        id = 0x43210002
        data = None

    class AccMagChannel(ctypes.LittleEndianStructure):
        id = 0x43210003
        data = None

    class LocationChannel(ctypes.LittleEndianStructure):
        id = 0x43210004
        data = tdf_defs.readings.gcs_wgs84_llha

    class NavPvtUbxChannel(ctypes.LittleEndianStructure):
        id = 0x43210007
        data = tdf_defs.readings.ubx_nav_pvt

    class NavPvtNRFChannel(ctypes.LittleEndianStructure):
        id = 0x43210008
        data = tdf_defs.readings.nrf9x_gnss_pvt

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
            "--imu",
            dest="channel",
            action="store_const",
            const=cls.ImuChannel,
            help="IMU channel",
        )
        group.add_argument(
            "--acc-mag",
            dest="channel",
            action="store_const",
            const=cls.AccMagChannel,
            help="Accelerometer magnitude channel",
        )
        group.add_argument(
            "--location",
            dest="channel",
            action="store_const",
            const=cls.LocationChannel,
            help="Location channel",
        )
        group.add_argument(
            "--nav-pvt-ubx",
            dest="channel",
            action="store_const",
            const=cls.NavPvtUbxChannel,
            help="ublox NAV-PVT channel",
        )
        group.add_argument(
            "--nav-pvt-nrf",
            dest="channel",
            action="store_const",
            const=cls.NavPvtNRFChannel,
            help="nRF9x NAV-PVT channel",
        )

    def __init__(self, args):
        self._channel = args.channel

    def request_struct(self):
        return self.request(self._channel.id)

    def request_json(self):
        return {"channel_id": str(self._channel.id)}

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query channel ({errno.strerror(-return_code)})")
            return

        from infuse_iot.time import InfuseTime

        pub_time = InfuseTime.unix_time_from_epoch(response.pub_timestamp)
        data_bytes = bytes(response.data)

        print(f"\t  Publish time: {InfuseTime.utc_time_string(pub_time)}")
        print(f"\t Publish count: {response.pub_count}")
        print(f"\tPublish period: {response.pub_period_ms} ms")
        try:
            if self._channel.data is None:
                print(f"\t          Data: {data_bytes.hex()}")
            else:
                data = self._channel.data.from_buffer_copy(data_bytes)
                table = []
                for field in data.iter_fields():
                    table.append([field.name, field.val_fmt(), field.postfix])
                print(tabulate.tabulate(table, tablefmt="simple"))
        except Exception as _:
            print(f"\t          Data: {data_bytes.hex()}")
