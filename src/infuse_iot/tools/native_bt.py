#!/usr/bin/env python3

"""Native Bluetooth gateway tool"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import argparse
import asyncio
import ctypes
import json
import logging
import random
import sys
from typing import Any, Literal

from bleak import BleakClient, BleakScanner
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakError
from cryptography.exceptions import InvalidTag

import infuse_iot.definitions.rpc as defs
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
from infuse_iot.gateway_control import GatewayControl
from infuse_iot.services.ble_observations import BleObservations
from infuse_iot.services.collector import gateway_identity
from infuse_iot.socket_comms import (
    ClientNotification,
    ClientNotificationCommsCheck,
    ClientNotificationConnectionCreated,
    ClientNotificationConnectionDropped,
    ClientNotificationConnectionFailed,
    ClientNotificationEpacketReceived,
    GatewayRequest,
    GatewayRequestCommsCheck,
    GatewayRequestConnection,
    GatewayRequestConnectionRelease,
    GatewayRequestConnectionRequest,
    GatewayRequestEpacketSend,
    LocalServer,
)
from infuse_iot.util.argparse import BtLeAddress, ValidFile, add_server_port_parser
from infuse_iot.util.console import Console
from infuse_iot.util.local_rpc_server import LocalRpcServer

# Raw observation pages stay well below the 8 kB datagrams that clients receive.
RAW_OBSERVATION_BYTES = 5000


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
        self._connected: set[int] = set()
        self._rpc = LocalRpcServer(database, native_bt=True)
        control = getattr(server, "control", None)
        self._control = control if isinstance(control, GatewayControl) else GatewayControl(server.broadcast)
        self._control.kind = "native_bt"
        self._expiry_timer: asyncio.TimerHandle | None = None

    def wrapped_broadcast(self, notifcation: ClientNotification):
        try:
            self._server.broadcast(notifcation)
        except OSError as e:
            Console.log_error(f"Failed to broadcast notification: {str(e)}")

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
        # Handle any local RPC responses
        self._rpc.handle(pkt)
        # Forward to clients
        self.wrapped_broadcast(ClientNotificationEpacketReceived(pkt))

    async def create_connection_internal(
        self, request: GatewayRequestConnectionRequest, dev: BLEDevice, queue: asyncio.Queue
    ):
        subscribed = request.DataType(0)
        # The whole setup, not just the Bluetooth connection, must complete within the requested timeout.
        deadline = asyncio.get_running_loop().time() + request.timeout_ms / 1000

        async def before_deadline(aw):
            return await asyncio.wait_for(aw, timeout=max(0, deadline - asyncio.get_running_loop().time()))

        async def subscribe(types):
            nonlocal subscribed
            characteristics = (
                (request.DataType.COMMAND, InfuseBluetoothUUID.COMMAND_CHAR),
                (request.DataType.DATA, InfuseBluetoothUUID.DATA_CHAR),
                (request.DataType.LOGGING, InfuseBluetoothUUID.LOGGING_CHAR),
            )
            for flag, uuid in characteristics:
                if types & flag and not subscribed & flag:
                    await client.start_notify(uuid, self.notification_handler)
                    subscribed |= flag

        Console.log_info(f"{request.infuse_id:016x}: Initiating connection")
        async with BleakClient(
            dev,
            timeout=request.timeout_ms / 1000,
            disconnected_callback=lambda _: queue.put_nowait(None),
        ) as client:
            # Modified from bleak example code
            if client._backend.__class__.__name__ == "BleakClientBlueZDBus":
                await before_deadline(client._backend._acquire_mtu())  # type: ignore

            Console.log_info(f"{request.infuse_id:016x}: Connected (MTU {client.mtu_size})")

            have_shared_key = self._db.has_shared_key(request.infuse_id)
            if have_shared_key:
                # Read the current keys back to confirm they haven't changed
                security_info = await before_deadline(client.read_gatt_char(InfuseBluetoothUUID.COMMAND_CHAR))
                resp = InfuseGattReadResponse.from_buffer_copy(security_info)
                key_id = self._db.get_device_key_id(bytes(resp.cloud_public_key), bytes(resp.device_public_key))
                if self._db.devices[request.infuse_id].device_key_id != key_id:
                    # Keys mismatch, invaidate the shared key
                    Console.log_info(f"{dev}: Key mismatch, re-running derivation")
                    have_shared_key = False

            if not have_shared_key:
                # Always need the command characteristic to get the response
                await before_deadline(subscribe(request.DataType.COMMAND))

                security_state_received = asyncio.Event()

                def security_state_done(pkt: PacketReceived, _rc: int, response: bytes, challenge):
                    decoded = defs.security_state.response.vla_from_buffer_copy(response)
                    self._db.observe_security_state(
                        request.infuse_id,
                        bytes(decoded.cloud_public_key),
                        bytes(decoded.device_public_key),
                        decoded.network_id,
                        challenge,
                        decoded.challenge_response_type,
                        bytes(decoded.challenge_response),
                    )
                    security_state_received.set()

                # Construct the Security State RPC command
                challenge = random.randbytes(16)
                ss_pkt = self._rpc.generate_addressed(
                    request.infuse_id,
                    defs.security_state.COMMAND_ID,
                    challenge,
                    Auth.NETWORK,
                    security_state_done,
                    challenge,
                )

                # Encrypt command and write to remote
                encr = CtypeBtGattFrame.encrypt(self._db, request.infuse_id, ss_pkt.ptype, Auth.NETWORK, ss_pkt.payload)
                Console.log_tx(ss_pkt.ptype, len(encr))
                await before_deadline(client.write_gatt_char(InfuseBluetoothUUID.COMMAND_CHAR, encr, response=False))

                # Wait for a response
                await before_deadline(security_state_received.wait())

                # Disable the command characteristic if not requested
                if not (request.data_types & request.DataType.COMMAND):
                    await before_deadline(client.stop_notify(InfuseBluetoothUUID.COMMAND_CHAR))
                    subscribed &= ~request.DataType.COMMAND

            await before_deadline(subscribe(request.data_types))

            # ATT header uses 3 bytes of the MTU.
            max_payload = client.mtu_size - 3 - ctypes.sizeof(CtypeBtGattFrame) - 16
            self._connected.add(request.infuse_id)
            self.wrapped_broadcast(ClientNotificationConnectionCreated(request.infuse_id, max_payload))

            req: GatewayRequest
            users = 1
            while req := await queue.get():
                if isinstance(req, GatewayRequestConnectionRequest):
                    await subscribe(req.data_types)
                    users += 1
                    self.wrapped_broadcast(ClientNotificationConnectionCreated(request.infuse_id, max_payload))
                    continue
                if isinstance(req, GatewayRequestConnectionRelease):
                    users -= 1
                    if users == 0:
                        break
                    continue
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

    async def create_connection(self, request: GatewayRequestConnectionRequest, dev: BLEDevice, queue: asyncio.Queue):
        reason = "Connection setup interrupted"
        cancelled = False
        try:
            await self.create_connection_internal(request, dev, queue)
        except BleakError as e:
            Console.log_info(f"Bleak Error: {str(e)}")
            reason = f"Bluetooth error: {e}"
        except TimeoutError as e:
            Console.log_info(f"Timeout: {str(e)}")
            reason = f"Connection timed out: {e}" if str(e) else "Connection timed out"
        except asyncio.CancelledError:
            cancelled = True
            raise
        finally:
            self._queues.pop(request.infuse_id, None)
            self._tasks.pop(request.infuse_id, None)
            established = request.infuse_id in self._connected
            if established:
                self._connected.remove(request.infuse_id)
                self.wrapped_broadcast(ClientNotificationConnectionDropped(request.infuse_id))
            else:
                self.wrapped_broadcast(ClientNotificationConnectionFailed(request.infuse_id, reason))
            Console.log_info(f"{dev}: Terminating connection")
            if established and not cancelled:
                # Failed setup was reported to queued requests; requests received as the connection closed need a new
                # one. Shutdown cancels connections and must not start new ones.
                self._redispatch(queue)

    def _redispatch(self, queue: asyncio.Queue):
        pending = []
        while not queue.empty():
            if (item := queue.get_nowait()) is not None:
                pending.append(item)
        first = next((i for i, r in enumerate(pending) if isinstance(r, GatewayRequestConnectionRequest)), None)
        if first is None:
            return
        pending = pending[first:]
        requests = sum(isinstance(r, GatewayRequestConnectionRequest) for r in pending)
        releases = sum(isinstance(r, GatewayRequestConnectionRelease) for r in pending)
        if requests <= releases:
            # Every client that requested the connection has already given up on it.
            return
        for item in pending:
            self._dispatch(item)

    def connection_made(self, transport):
        self._expire_operations()

    def _expire_operations(self):
        for request in self._control.cleanup():
            self._dispatch(request)
        self._expiry_timer = asyncio.get_running_loop().call_later(0.25, self._expire_operations)

    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]):
        try:
            request = GatewayRequest.from_json(json.loads(data.decode("utf-8")))
            for cleanup in self._control.cleanup():
                self._dispatch(cleanup)
            if self._control.accept(request):
                self._dispatch(request)
            for cleanup in self._control.cleanup():
                self._dispatch(cleanup)
        except (ValueError, TypeError, KeyError, AttributeError, NotImplementedError):
            logging.getLogger(__name__).warning("Ignoring malformed gateway request")

    def _dispatch(self, request: GatewayRequest):
        loop = asyncio.get_event_loop()

        if isinstance(request, GatewayRequestCommsCheck):
            self.wrapped_broadcast(ClientNotificationCommsCheck())
            return

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
                q.put_nowait(request)
            return

        # Share one connection and queue per device, including while connection setup is pending.
        if request.infuse_id in self._queues:
            self._queues[request.infuse_id].put_nowait(request)
            return

        ble_dev = self._mapping.get(request.infuse_id, None)
        if ble_dev is None:
            self.wrapped_broadcast(
                ClientNotificationConnectionFailed(request.infuse_id, "Device has not been observed over Bluetooth")
            )
            return

        # Create queue for further data transfer
        q = asyncio.Queue()
        self._queues[request.infuse_id] = q
        # Create task to handle the connection
        self._tasks[request.infuse_id] = loop.create_task(self.create_connection(request, ble_dev, q))

    def error_received(self, exc):
        Console.log_error(f"Error received: {exc}")

    def connection_lost(self, exc):
        if self._expiry_timer is not None:
            self._expiry_timer.cancel()
        Console.log_error("Connection closed")
        for task in self._tasks.values():
            task.cancel()

    async def shutdown(self):
        if self._expiry_timer is not None:
            self._expiry_timer.cancel()
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self._queues.clear()


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--root", type=ValidFile, help="Root identity certificate to use instead of cloud")
        parser.add_argument(
            "--report-interval",
            type=float,
            default=5.0,
            help="Interval in seconds to output Bluetooth report counts (0 disables)",
        )
        add_server_port_parser(parser)

    def __init__(self, args: argparse.Namespace):
        self.infuse_manu = 0x0DE4
        self.database = DeviceDatabase(args.root)
        self.server = LocalServer(args.server_sock)
        self.bleak_mapping: dict[int, BLEDevice] = {}
        self.observations = BleObservations()
        self.scan_statistics = {
            "infuse_advertisements": 0,
            "decrypted_packets": 0,
            "unknown_network_packets": 0,
            "invalid_tag_packets": 0,
        }
        self.server.control.kind = "native_bt"
        self.server.control.handlers["raw_observations"] = self.raw_observations
        self.server.control.handlers["diagnostics"] = self.diagnostics
        self.unknown_networks: set[int] = set()
        self.report_interval: float = args.report_interval
        self.report_count = 0
        self.infuse_report_count = 0
        Console.init()

    @staticmethod
    def _check_parameters(params: dict[str, Any], known: tuple[str, ...]) -> None:
        unknown = sorted(set(params) - set(known))
        if unknown:
            raise ValueError(f"Unknown parameters: {', '.join(unknown)}")

    def raw_observations(self, params: dict[str, Any]) -> dict[str, Any]:
        """Answer a paginated query of raw advertisement observations, whose values the service validates"""
        self._check_parameters(params, ("max_age_seconds", "cursor", "limit", "infuse_only"))
        return self.observations.snapshot(
            **params,
            max_bytes=RAW_OBSERVATION_BYTES,
            metadata={"gateway": gateway_identity(self.server.control.capabilities())},
        )

    def diagnostics(self, params: dict[str, Any]) -> dict[str, Any]:
        """Radio and decryption counters since the gateway started"""
        self._check_parameters(params, ())
        return {
            **self.scan_statistics,
            "advertisements": self.observations.advertisements,
            "gateway_kind": "native_bt",
        }

    async def server_handler(self):
        sock = self.server._input_sock
        sock.setblocking(False)
        # Wrap the socket with an asyncio Datagram protocol
        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: MulticastHandler(self.database, self.server, self.bleak_mapping),
            sock=sock,
        )
        # Keep the server running
        try:
            await asyncio.Future()  # Run forever
        finally:
            await protocol.shutdown()
            transport.close()

    def simple_callback(self, device: BLEDevice, data: AdvertisementData):
        self.report_count += 1
        self.observations.observe(
            device.address, data.local_name or device.name, data.rssi, data.manufacturer_data, data.service_uuids
        )
        if self.infuse_manu not in data.manufacturer_data:
            return
        self.infuse_report_count += 1
        self.scan_statistics["infuse_advertisements"] += 1
        addr = interface.Address(interface.Address.BluetoothLeAddr(0, BtLeAddress.integer_value(device.address)))
        rssi = data.rssi
        payload = data.manufacturer_data[self.infuse_manu]

        try:
            hdr, decr = CtypeBtAdvFrame.decrypt(self.database, addr.val, payload)
        except UnknownNetworkError as e:
            self.scan_statistics["unknown_network_packets"] += 1
            network_id = e.args[0]
            if network_id not in self.unknown_networks:
                self.unknown_networks.add(network_id)
                Console.log_info(f"Unknown network 0x{network_id:06x}")
            return
        except InvalidTag as _e:
            self.scan_statistics["invalid_tag_packets"] += 1
            Console.log_info(f"Failed to decrypt packet from {device}")
            return
        self.scan_statistics["decrypted_packets"] += 1
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
        try:
            self.server.broadcast(notification)
        except OSError as e:
            Console.log_error(f"Failed to broadcast notification: {str(e)}")

    async def report_counter(self):
        while True:
            await asyncio.sleep(self.report_interval)
            count = self.report_count
            infuse_count = self.infuse_report_count
            self.report_count = 0
            self.infuse_report_count = 0
            Console.log_info(f"Observed {count} Bluetooth packets ({infuse_count} Infuse)")

    async def async_bt_receiver(self):
        loop = asyncio.get_event_loop()
        handler = loop.create_task(self.server_handler())
        if self.report_interval > 0.0:
            loop.create_task(self.report_counter())

        # MacOS does not support passive scanning
        scanning_mode: Literal["active", "passive"] = "active" if sys.platform == "darwin" else "passive"
        scanner = BleakScanner(
            self.simple_callback,
            scanning_mode=scanning_mode,
            bluez={"filters": {"DuplicateData": True}},
            cb=dict(use_bdaddr=True),
        )

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

    def close(self):
        self.server.close()
