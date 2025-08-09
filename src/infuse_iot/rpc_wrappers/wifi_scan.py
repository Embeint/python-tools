#!/usr/bin/env python3

import ctypes

import tabulate

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr import wifi as z_wifi
from infuse_iot.zephyr.errno import errno


class wifi_scan(InfuseRpcCommand, defs.wifi_scan):
    class response(ctypes.LittleEndianStructure):
        @classmethod
        def from_buffer_copy(cls, source, offset=0):
            values = []
            source = source[1:]
            while len(source) > 0:

                class scan_rsp_header(ctypes.LittleEndianStructure):
                    _fields_ = [
                        ("band", ctypes.c_uint8),
                        ("channel", ctypes.c_uint8),
                        ("security", ctypes.c_uint8),
                        ("rssi", ctypes.c_int8),
                        ("bssid", 6 * ctypes.c_char),
                        ("ssid_length", ctypes.c_uint8),
                    ]
                    _pack_ = 1

                header = scan_rsp_header.from_buffer_copy(source)

                class scan_result(ctypes.LittleEndianStructure):
                    _fields_ = [
                        ("band", ctypes.c_uint8),
                        ("channel", ctypes.c_uint8),
                        ("security", ctypes.c_uint8),
                        ("rssi", ctypes.c_int8),
                        ("bssid", 6 * ctypes.c_char),
                        ("ssid_length", ctypes.c_uint8),
                        ("ssid", header.ssid_length * ctypes.c_char),
                    ]
                    _pack_ = 1

                struct = scan_result.from_buffer_copy(source)
                values.append(struct)
                source = source[ctypes.sizeof(struct) :]
            return values

    @classmethod
    def add_parser(cls, parser):
        return

    def __init__(self, args):
        self.args = args

    def request_struct(self):
        return self.request()

    def handle_response(self, return_code, response):
        if return_code != 0:
            print(f"Failed to query current time ({errno.strerror(-return_code)})")
            return

        table = []
        for network in response:
            bssid = ":".join([f"{b:02x}" for b in network.bssid])

            table.append(
                [
                    network.ssid.decode("utf-8"),
                    bssid,
                    str(z_wifi.FrequencyBand(network.band)),
                    network.channel,
                    str(z_wifi.SecurityType(network.security)),
                    f"{network.rssi} dBm",
                ]
            )

        headers = ["SSID", "BSSID", "Band", "Channel", "Security", "RSSI"]
        print(tabulate.tabulate(table, headers=headers))
