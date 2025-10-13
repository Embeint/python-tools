#!/usr/bin/env python3

import tabulate

import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import InfuseRpcCommand
from infuse_iot.zephyr import wifi as z_wifi
from infuse_iot.zephyr.errno import errno


class wifi_scan(InfuseRpcCommand, defs.wifi_scan):
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
        for network in response.networks:
            bssid = ":".join([f"{b:02x}" for b in network.bssid])

            table.append(
                [
                    bytes(network.ssid).decode("utf-8"),
                    bssid,
                    str(z_wifi.FrequencyBand(network.band)),
                    network.channel,
                    str(z_wifi.SecurityType(network.security)),
                    f"{network.rssi} dBm",
                ]
            )

        headers = ["SSID", "BSSID", "Band", "Channel", "Security", "RSSI"]
        print(tabulate.tabulate(table, headers=headers))
