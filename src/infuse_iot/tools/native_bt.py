#!/usr/bin/env python3

"""Native Bluetooth gateway tool"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import asyncio

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from infuse_iot.util.argparse import BtLeAddress
from infuse_iot.util.console import Console
from infuse_iot.epacket.packet import (
    CtypeBtAdvFrame,
    PacketReceived,
    HopReceived,
    Auth,
    Flags,
)
from infuse_iot.commands import InfuseCommand
from infuse_iot.socket_comms import LocalServer, default_multicast_address
from infuse_iot.database import DeviceDatabase

import infuse_iot.epacket.interface as interface


class SubCommand(InfuseCommand):
    NAME = "native_bt"
    HELP = "Native Bluetooth gateway"
    DESCRIPTION = "Use the local Bluetooth adapater for Bluetooth interaction"

    @classmethod
    def add_parser(cls, parser):
        pass

    def __init__(self, args):
        self.infuse_manu = 0x0DE4
        self.infuse_service = "0000fc74-0000-1000-8000-00805f9b34fb"
        self.database = DeviceDatabase()
        Console.init()

    def simple_callback(self, device: BLEDevice, data: AdvertisementData):
        addr = interface.Address.BluetoothLeAddr(0, BtLeAddress(device.address))
        rssi = data.rssi
        payload = data.manufacturer_data[self.infuse_manu]

        hdr, decr = CtypeBtAdvFrame.decrypt(self.database, payload)

        hop = HopReceived(
            hdr.device_id,
            interface.ID.BT_ADV,
            addr,
            (Auth.DEVICE if hdr.flags & Flags.ENCR_DEVICE else Auth.NETWORK),
            hdr.key_metadata,
            hdr.gps_time,
            hdr.sequence,
            rssi,
        )

        Console.log_rx(hdr.type, len(payload))
        pkt = PacketReceived([hop], hdr.type, decr)
        self.server.broadcast(pkt)

    async def async_run(self):
        self.server = LocalServer(default_multicast_address())

        scanner = BleakScanner(
            self.simple_callback, [self.infuse_service], cb=dict(use_bdaddr=True)
        )

        while True:
            Console.log_info("Starting scanner")
            async with scanner:
                # Run the scanner forever
                await asyncio.Future()

    def run(self):
        asyncio.run(self.async_run())
