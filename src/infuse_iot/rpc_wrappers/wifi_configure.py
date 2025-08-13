#!/usr/bin/env python3

import ctypes

import infuse_iot.definitions.rpc as defs
import infuse_iot.zephyr.wifi as wifi
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.rpc_wrappers.kv_write import kv_write
from infuse_iot.util.ctypes import UINT8_MAX, VLACompatLittleEndianStruct
from infuse_iot.zephyr.errno import errno


class wifi_configure(InfuseRpcCommand, defs.kv_write):
    HELP = "Set the WiFi network SSID and PSK"
    DESCRIPTION = "Set the WiFi network SSID and PSK"

    class request(ctypes.LittleEndianStructure):
        _fields_ = [
            ("num", ctypes.c_uint8),
        ]
        _pack_ = 1

    class response(VLACompatLittleEndianStruct):
        vla_field = ("rc", 0 * ctypes.c_int16)

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--ssid", "-s", type=str, help="Network name")
        parser.add_argument("--psk", "-p", type=str, help="Network password")
        band_parser = parser.add_mutually_exclusive_group()
        band_parser.add_argument(
            "--band-unknown",
            action="store_const",
            dest="band",
            const=UINT8_MAX,
            default=UINT8_MAX,
            help="Unknown frequency band",
        )
        band_parser.add_argument(
            "--band-2G4",
            action="store_const",
            dest="band",
            const=wifi.FrequencyBand.BAND_2_4_GHZ,
            help="2.4GHz frequency band",
        )
        band_parser.add_argument(
            "--band-5G",
            action="store_const",
            dest="band",
            const=wifi.FrequencyBand.BAND_5_GHZ,
            help="5GHz frequency band",
        )
        band_parser.add_argument(
            "--band-6G",
            action="store_const",
            dest="band",
            const=wifi.FrequencyBand.BAND_6_GHZ,
            help="6GHz frequency band",
        )
        parser.add_argument(
            "--channel", "-c", type=int, default=wifi.FrequencyChannel.CHANNEL_ANY, help="Network channel index"
        )

    def __init__(self, args):
        self.args = args

    def request_struct(self):
        ssid_bytes = self.args.ssid.encode("utf-8") + b"\x00"
        psk_bytes = self.args.psk.encode("utf-8") + b"\x00"
        chan_bytes = self.args.band.to_bytes(1, "little") + self.args.channel.to_bytes(1, "little")

        ssid_struct = kv_write.kv_store_value_factory(20, len(ssid_bytes).to_bytes(1, "little") + ssid_bytes)
        psk_struct = kv_write.kv_store_value_factory(21, len(psk_bytes).to_bytes(1, "little") + psk_bytes)
        chan_struct = kv_write.kv_store_value_factory(22, chan_bytes)

        request_bytes = bytes(ssid_struct) + bytes(psk_struct) + bytes(chan_struct)
        return bytes(self.request(3)) + request_bytes

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Invalid data buffer ({errno.strerror(-return_code)})")
            return

        def print_status(name, rc):
            if rc < 0:
                print(f"{name} failed to write")
            elif rc == 0:
                print(f"{name} already matched")
            else:
                print(f"{name} updated")

        print_status("SSID", response.rc[0])
        print_status("PSK", response.rc[1])
        print_status("Channel", response.rc[2])
