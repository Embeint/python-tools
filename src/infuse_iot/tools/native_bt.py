#!/usr/bin/env python3

"""Native Bluetooth gateway tool"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import argparse
import asyncio
import ctypes
import json
from typing import Any

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseBluetoothUUID, InfuseType
from infuse_iot.database import DeviceDatabase, UnknownNetworkError
from infuse_iot.epacket import interface
from infuse_iot.epacket.packet import (
    Auth,
    CtypeBtAdvFrame,
    CtypeBtGattFrame,
    Flags,
    HopReceived,
    PacketOutput,
    PacketReceived,
)
from infuse_iot.socket_comms import (
    ClientNotificationConnectionCreated,
    ClientNotificationConnectionFailed,
    ClientNotificationEpacketReceived,
    GatewayRequest,
    GatewayRequestConnection,
    GatewayRequestConnectionRelease,
    GatewayRequestConnectionRequest,
    GatewayRequestEpacketSend,
    LocalServer,
    default_multicast_address,
)
from infuse_iot.util.argparse import BtLeAddress
from infuse_iot.util.console import Console


class InfuseGattReadResponse(ctypes.LittleEndianStructure):
    """Response to any read request on Infuse-IoT characteristics"""

    _fields_ = [
        ("cloud_public_key", 32 * ctypes.c_uint8),
        ("device_public_key", 32 * ctypes.c_uint8),
        ("network_id", ctypes.c_uint32),
    ]
    _pack_ = 1


class MulticastHandler(asyncio.DatagramProtocol):
    def __init__(self, database: DeviceDatabase, server: LocalServer, bleak_mapping: dict[int, BLEDevice]):
        self._db = database
        self._server = server
        self._mapping = bleak_mapping
        self._queues: dict[int, asyncio.Queue] = {}
        self._tasks: dict[int, asyncio.Task] = {}

    def notification_handler(self, _characteristic: BleakGATTCharacteristic, data: bytearray):
        try:
            hdr, decr = CtypeBtGattFrame.decrypt(self._db, None, bytes(data))
        except UnknownNetworkError:
            return
        # Correct values are annoying to get here
        if_addr = interface.Address(interface.Address.BluetoothLeAddr(0, 0))
        rssi = 0

        bt_hop = HopReceived(
            hdr.device_id,
            interface.ID.BT_CENTRAL,
            if_addr,
            (Auth.DEVICE if hdr.flags & Flags.ENCR_DEVICE else Auth.NETWORK),
            hdr.key_metadata,
            hdr.gps_time,
            hdr.sequence,
            rssi,
        )
        pkt = PacketReceived(
            [bt_hop],
            hdr.type,
            bytes(decr),
        )
        Console.log_rx(pkt.ptype, len(data))
        self._server.broadcast(ClientNotificationEpacketReceived(pkt))

    async def create_connection(self, request: GatewayRequestConnectionRequest, dev: BLEDevice, queue: asyncio.Queue):
        Console.log_info(f"{dev}: Initiating connection")
        async with BleakClient(dev, timeout=request.timeout_ms / 1000) as client:
            # Modified from bleak example code
            if client._backend.__class__.__name__ == "BleakClientBlueZDBus":
                await client._backend._acquire_mtu()  # type: ignore

            security_info = await client.read_gatt_char(InfuseBluetoothUUID.COMMAND_CHAR)
            resp = InfuseGattReadResponse.from_buffer_copy(security_info)
            self._db.observe_security_state(
                request.infuse_id,
                bytes(resp.cloud_public_key),
                bytes(resp.device_public_key),
                resp.network_id,
            )

            if request.data_types & request.DataType.COMMAND:
                await client.start_notify(InfuseBluetoothUUID.COMMAND_CHAR, self.notification_handler)
            if request.data_types & request.DataType.DATA:
                await client.start_notify(InfuseBluetoothUUID.DATA_CHAR, self.notification_handler)
            if request.data_types & request.DataType.LOGGING:
                await client.start_notify(InfuseBluetoothUUID.LOGGING_CHAR, self.notification_handler)

            Console.log_info(f"{dev}: Connected (MTU {client.mtu_size})")

            self._server.broadcast(
                ClientNotificationConnectionCreated(
                    request.infuse_id,
                    # ATT header uses 3 bytes of the MTU
                    client.mtu_size - 3 - ctypes.sizeof(CtypeBtGattFrame) - 16,
                )
            )

            req: GatewayRequest
            while req := await queue.get():
                if isinstance(req, GatewayRequestConnectionRelease):
                    break
                assert isinstance(req, GatewayRequestEpacketSend)
                pkt: PacketOutput = req.epacket

                # Encrypt payload
                encr = CtypeBtGattFrame.encrypt(self._db, request.infuse_id, pkt.ptype, pkt.auth, pkt.payload)

                if pkt.ptype in [InfuseType.RPC_CMD, InfuseType.RPC_DATA]:
                    uuid = InfuseBluetoothUUID.COMMAND_CHAR
                else:
                    uuid = InfuseBluetoothUUID.DATA_CHAR

                Console.log_tx(pkt.ptype, len(encr))
                await client.write_gatt_char(uuid, encr, response=False)

        # Queue no longer being handled
        self._queues.pop(request.infuse_id)
        self._tasks.pop(request.infuse_id)
        Console.log_info(f"{dev}: Terminating connection")

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]):
        loop = asyncio.get_event_loop()
        request = GatewayRequest.from_json(json.loads(data.decode("utf-8")))

        # If not a connection request, attempt to forward to connection context
        if not isinstance(request, GatewayRequestConnectionRequest):
            if isinstance(request, GatewayRequestEpacketSend):
                queue_id = request.epacket.infuse_id
            elif isinstance(request, GatewayRequestConnection):
                queue_id = request.infuse_id
            else:
                raise RuntimeError
            q: asyncio.Queue | None = self._queues.get(queue_id, None)
            if q is not None:
                loop.call_soon(lambda: q.put_nowait(request))  # type: ignore
            return

        ble_dev = self._mapping.get(request.infuse_id, None)
        if ble_dev is None:
            self._server.broadcast(ClientNotificationConnectionFailed(request.infuse_id))
            return

        # Create queue for further data transfer
        q = asyncio.Queue()
        self._queues[request.infuse_id] = q
        # Create task to handle the connection
        self._tasks[request.infuse_id] = loop.create_task(self.create_connection(request, ble_dev, q))

    def error_received(self, exc):
        Console.log_error(f"Error received: {exc}")

    def connection_lost(self, exc):
        Console.log_error("Connection closed")


class SubCommand(InfuseCommand):
    NAME = "native_bt"
    HELP = "Native Bluetooth gateway"
    DESCRIPTION = "Use the local Bluetooth adapter for Bluetooth interaction"

    @classmethod
    def add_parser(cls, parser):
        pass

    def __init__(self, args: argparse.Namespace):
        self.infuse_manu = 0x0DE4
        self.database = DeviceDatabase()
        self.server = LocalServer(default_multicast_address())
        self.bleak_mapping: dict[int, BLEDevice] = {}
        self.unknown_networks: set[int] = set()
        Console.init()

    async def server_handler(self):
        sock = self.server._input_sock
        sock.setblocking(False)
        # Wrap the socket with an asyncio Datagram protocol
        loop = asyncio.get_running_loop()
        transport, _protocol = await loop.create_datagram_endpoint(
            lambda: MulticastHandler(self.database, self.server, self.bleak_mapping),
            sock=sock,
        )
        # Keep the server running
        try:
            await asyncio.Future()  # Run forever
        finally:
            transport.close()

    def simple_callback(self, device: BLEDevice, data: AdvertisementData):
        addr = interface.Address(interface.Address.BluetoothLeAddr(0, BtLeAddress.integer_value(device.address)))
        rssi = data.rssi
        payload = data.manufacturer_data[self.infuse_manu]

        try:
            hdr, decr = CtypeBtAdvFrame.decrypt(self.database, addr.val, payload)
        except UnknownNetworkError as e:
            network_id = e.args[0]
            if network_id not in self.unknown_networks:
                self.unknown_networks.add(network_id)
                Console.log_info(f"Unknown network 0x{network_id:06x}")
            return
        self.bleak_mapping[hdr.device_id] = device

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
        notification = ClientNotificationEpacketReceived(pkt)
        self.server.broadcast(notification)

    async def async_bt_receiver(self):
        loop = asyncio.get_event_loop()
        handler = loop.create_task(self.server_handler())

        scanner = BleakScanner(self.simple_callback, [str(InfuseBluetoothUUID.SERVICE_UUID)], cb=dict(use_bdaddr=True))

        while True:
            Console.log_info("Starting scanner")
            async with scanner:
                await handler

    def sync_request_handler(self):
        # Loop while there are packets to send
        while req := self.server.receive():
            print(req)

    def run(self):
        asyncio.run(self.async_bt_receiver())
