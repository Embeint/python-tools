#!/usr/bin/env python3

"""Serial to Bluetooth gateway control tool"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import argparse
import base64
import ctypes
import io
import queue
import random
import threading
import time
from typing import Callable

import cryptography
import cryptography.exceptions

import infuse_iot.epacket.interface as interface
import infuse_iot.generated.rpc_definitions as defs
from infuse_iot import rpc
from infuse_iot.commands import InfuseCommand
from infuse_iot.common import InfuseID, InfuseType
from infuse_iot.database import (
    DeviceDatabase,
    NoKeyError,
)
from infuse_iot.epacket.packet import (
    Auth,
    HopOutput,
    PacketOutputRouted,
    PacketReceived,
)
from infuse_iot.serial_comms import RttPort, SerialFrame, SerialPort
from infuse_iot.socket_comms import (
    ClientNotification,
    GatewayRequest,
    LocalServer,
    default_multicast_address,
)
from infuse_iot.util.argparse import ValidFile
from infuse_iot.util.console import Console
from infuse_iot.util.threading import SignaledThread


class LocalRpcServer:
    """Basic class supporting locally generated commands"""

    def __init__(self, database: DeviceDatabase):
        self._cnt = random.randint(0, 2**31)
        self._ddb = database
        self._queued: dict[int, Callable | None] = {}

    def generate(self, command: int, args: bytes, auth: Auth, cb: Callable | None):
        """Generate RPC packet from arguments"""
        cmd_bytes = bytes(rpc.RequestHeader(self._cnt, command)) + args
        cmd_pkt = PacketOutputRouted(
            [HopOutput.serial(auth)],
            InfuseType.RPC_CMD,
            cmd_bytes,
        )
        assert self._ddb.gateway is not None
        cmd_pkt.route[0].infuse_id = self._ddb.gateway
        self._queued[self._cnt] = cb
        self._cnt += 1
        return cmd_pkt

    def handle(self, pkt: PacketReceived):
        """Handle received packets"""
        # Only care about RPC responses
        if pkt.ptype != InfuseType.RPC_RSP:
            return

        # Inspect the response header
        header = rpc.ResponseHeader.from_buffer_copy(pkt.payload)

        # Was this a BT connect response with key information?
        if header.command_id == defs.bt_connect_infuse.COMMAND_ID:
            resp = defs.bt_connect_infuse.response.from_buffer_copy(pkt.payload[ctypes.sizeof(header) :])
            if_addr = interface.Address.BluetoothLeAddr.from_rpc_struct(resp.peer)
            infuse_id = self._ddb.infuse_id_from_bluetooth(if_addr)
            if infuse_id is None:
                Console.log_error(f"Infuse ID of {if_addr} not known")
            else:
                self._ddb.observe_security_state(
                    infuse_id,
                    bytes(resp.cloud_public_key),
                    bytes(resp.device_public_key),
                    resp.network_id,
                )

        # Determine if the response is to a command we initiated
        if header.request_id not in self._queued:
            return

        # Run the callback
        cb = self._queued.pop(header.request_id)
        if cb is not None:
            cb(pkt, header.return_code, pkt.payload[ctypes.sizeof(header) :])


class CommonThreadState:
    def __init__(
        self,
        server: LocalServer,
        port: SerialPort,
        ddb: DeviceDatabase,
        rpc_server: LocalRpcServer,
    ):
        self.server = server
        self.port = port
        self.ddb = ddb
        self.rpc = rpc_server

    def query_device_key(self, cb_event: threading.Event | None = None):
        def security_state_done(pkt: PacketReceived, _: int, response: bytes):
            cloud_key = response[:32]
            device_key = response[32:64]
            network_id = int.from_bytes(response[64:68], "little")

            self.ddb.observe_security_state(pkt.route[0].infuse_id, cloud_key, device_key, network_id)
            if cb_event is not None:
                cb_event.set()

        # Generate security_state RPC
        cmd_pkt = self.rpc.generate(30000, random.randbytes(16), Auth.NETWORK, security_state_done)
        encrypted = cmd_pkt.to_serial(self.ddb)
        # Write to serial port
        Console.log_tx(cmd_pkt.ptype, len(encrypted))
        self.port.write(encrypted)
        if cb_event is not None:
            # Wait for the response
            cb_event.wait(1.0)


class SerialRxThread(SignaledThread):
    """Receive serial frames from the serial port"""

    def __init__(self, common: CommonThreadState, log: io.TextIOWrapper):
        self._common = common
        self._reconstructor = SerialFrame.reconstructor()
        self._reconstructor.send(None)
        self._line = ""
        self._log = log
        super().__init__(self._iter)

    def _iter(self):
        # Read bytes from serial port
        rx = self._common.port.read_bytes(1024)
        if len(rx) == 0:
            return
        for b in rx:
            frame_byte, frame = self._reconstructor.send(b)
            if frame and self._common.server is not None:
                self._handle_serial_frame(frame)

            if not frame_byte:
                c = chr(b)
                if c == "\n":
                    if self._log is not None:
                        self._log.write(self._line)
                    print(self._line)
                    self._line = ""
                else:
                    self._line += c

    def _handle_memfault_pkt(self, pkt: PacketReceived):
        class memfault_chunk_header(ctypes.LittleEndianStructure):
            _fields_ = [
                ("len", ctypes.c_uint16),
                ("cnt", ctypes.c_uint8),
            ]
            _pack_ = 1

        p = pkt.payload
        while len(p) > 0:
            hdr = memfault_chunk_header.from_buffer_copy(p)
            chunk = p[3 : 3 + hdr.len]
            p = p[3 + hdr.len :]
            print(f"Memfault Chunk {hdr.cnt:3d}: {base64.b64encode(chunk).decode('utf-8')}")

    def _handle_serial_frame(self, frame: bytearray):
        try:
            # Decode the serial packet
            try:
                decoded = PacketReceived.from_serial(self._common.ddb, frame)
            except NoKeyError:
                assert self._common.ddb.gateway is not None
                if not self._common.ddb.has_network_id(self._common.ddb.gateway):
                    # Need to know network ID before we can query the device key
                    self._common.port.ping()
                    Console.log_info(f"Dropping {len(frame)} byte packet to query network ID...")
                else:
                    self._common.query_device_key(None)
                    Console.log_info(f"Dropping {len(frame)} byte packet to query device key...")
                return
            except cryptography.exceptions.InvalidTag as e:
                Console.log_error(f"Failed to decode {len(frame)} byte packet {e}")
                return

            # Iterate over all contained subpackets
            for pkt in decoded:
                Console.log_rx(pkt.ptype, len(frame))
                # Handle any local RPC responses
                self._common.rpc.handle(pkt)
                # Handle any Memfault chunks
                if pkt.ptype == InfuseType.MEMFAULT_CHUNK:
                    self._handle_memfault_pkt(pkt)
                # Proactively requery keys
                elif pkt.ptype == InfuseType.KEY_IDS:
                    self._common.query_device_key(None)

                notification = ClientNotification(ClientNotification.Type.EPACKET_RECV, epacket=pkt)
                # Forward to clients
                self._common.server.broadcast(notification)
        except (ValueError, KeyError) as e:
            print(f"Decode failed ({e})")


class SerialTxThread(SignaledThread):
    """Send serial frames down the serial port"""

    def __init__(
        self,
        common: CommonThreadState,
    ):
        self._common = common
        self._queue: queue.Queue = queue.Queue()
        super().__init__(self._iter)

    def send(self, pkt):
        """Queue packet for transmission"""
        self._queue.put(pkt)

    def _handle_epacket_send(self, req: GatewayRequest):
        if self._common.ddb.gateway is None:
            Console.log_error("Gateway address unknown")
            return

        pkt = req.epacket
        assert pkt is not None

        # Construct routed output
        if pkt.infuse_id == InfuseID.GATEWAY:
            routed = PacketOutputRouted(
                [HopOutput(self._common.ddb.gateway, interface.ID.SERIAL, pkt.auth)],
                pkt.ptype,
                pkt.payload,
            )
        else:
            gateway = self._common.ddb.gateway
            serial = HopOutput(gateway, interface.ID.SERIAL, Auth.DEVICE)
            bt = HopOutput(pkt.infuse_id, interface.ID.BT_CENTRAL, pkt.auth)
            routed = PacketOutputRouted(
                [serial, bt],
                pkt.ptype,
                pkt.payload,
            )

        # Do we have the device public keys we need?
        for hop in routed.route:
            if hop.auth == Auth.DEVICE and not self._common.ddb.has_public_key(hop.infuse_id):
                cb_event = threading.Event()
                self._common.query_device_key(cb_event)

        # Encode and encrypt payload
        encrypted = routed.to_serial(self._common.ddb)

        # Write to serial port
        Console.log_tx(routed.ptype, len(encrypted))
        self._common.port.write(encrypted)

    def _bt_connect_cb(self, pkt: PacketReceived, rc: int, response: bytes):
        resp = defs.bt_connect_infuse.response.from_buffer_copy(pkt.payload[ctypes.sizeof(rpc.ResponseHeader) :])
        if_addr = interface.Address.BluetoothLeAddr.from_rpc_struct(resp.peer)
        infuse_id = self._common.ddb.infuse_id_from_bluetooth(if_addr)

        evt = ClientNotification.Type.CONNECTION_FAILED if rc < 0 else ClientNotification.Type.CONNECTION_CREATED
        rsp = ClientNotification(
            evt,
            connection_id=infuse_id,
        )
        self._common.server.broadcast(rsp)

    def _handle_conn_request(self, req: GatewayRequest):
        assert req.connection_id is not None

        if req.connection_id == InfuseID.GATEWAY:
            # Local gateway always connected
            rsp = ClientNotification(
                ClientNotification.Type.CONNECTION_CREATED,
                connection_id=req.connection_id,
            )
            self._common.server.broadcast(rsp)
            return

        state = self._common.ddb.devices.get(req.connection_id, None)
        if state is None or state.bt_addr is None:
            rsp = ClientNotification(
                ClientNotification.Type.CONNECTION_FAILED,
                connection_id=req.connection_id,
            )
            self._common.server.broadcast(rsp)
            return

        connect_args = defs.bt_connect_infuse.request(
            state.bt_addr.to_rpc_struct(),
            10000,
            defs.rpc_enum_infuse_bt_characteristic.COMMAND,
            0,
        )
        cmd = self._common.rpc.generate(
            defs.bt_connect_infuse.COMMAND_ID,
            bytes(connect_args),
            Auth.DEVICE,
            self._bt_connect_cb,
        )
        encrypted = cmd.to_serial(self._common.ddb)
        Console.log_tx(cmd.ptype, len(encrypted))
        self._common.port.write(encrypted)

    def _handle_conn_release(self, req: GatewayRequest):
        assert req.connection_id is not None

        if req.connection_id == InfuseID.GATEWAY:
            # Local gateway always connected
            return

        state = self._common.ddb.devices.get(req.connection_id, None)
        if state is None or state.bt_addr is None:
            # Unknown device, nothing to do
            return

        disconnect_args = defs.bt_disconnect.request(state.bt_addr.to_rpc_struct())
        cmd = self._common.rpc.generate(defs.bt_disconnect.COMMAND_ID, bytes(disconnect_args), Auth.DEVICE, None)
        encrypted = cmd.to_serial(self._common.ddb)
        Console.log_tx(cmd.ptype, len(encrypted))
        self._common.port.write(encrypted)

    def _iter(self):
        if self._common.server is None:
            time.sleep(1.0)
            return

        # Loop while there are packets to send
        while req := self._common.server.receive():
            if req.type == GatewayRequest.Type.EPACKET_SEND:
                self._handle_epacket_send(req)
            elif req.type == GatewayRequest.Type.CONNECTION_REQUEST:
                self._handle_conn_request(req)
            elif req.type == GatewayRequest.Type.CONNECTION_RELEASE:
                self._handle_conn_release(req)
            else:
                Console.log_error(f"Unhandled request {req.type}")


class SubCommand(InfuseCommand):
    NAME = "gateway"
    HELP = "Connect to a local gateway device"
    DESCRIPTION = "Connect to a gateway device over serial and route commands to Bluetooth devices"

    @classmethod
    def add_parser(cls, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--serial", type=ValidFile, help="Gateway serial port")
        group.add_argument("--rtt", type=str, help="RTT serial port")
        parser.add_argument(
            "--display-only",
            "-d",
            action="store_true",
            help="No networking, only display serial",
        )
        parser.add_argument(
            "--log",
            "-l",
            metavar="filename",
            const=f"{int(time.time())}_log.txt",
            nargs="?",
            type=argparse.FileType("w"),
            help="Save serial output to file",
        )

    def __init__(self, args):
        if args.serial is not None:
            self.port = SerialPort(args.serial)
        elif args.rtt is not None:
            self.port = RttPort(args.rtt)
        self.ddb = DeviceDatabase()
        if args.display_only:
            self.server = None
            self.rpc_server = None
        else:
            self.server = LocalServer(default_multicast_address())
            self.rpc_server = LocalRpcServer(self.ddb)
        self._common = CommonThreadState(self.server, self.port, self.ddb, self.rpc_server)
        self.log = args.log
        Console.init()

    def run(self):
        # Open the serial port
        self.port.open()
        # Ping the port to get the local device ID
        self.port.ping()

        # Start threads
        rx_thread = SerialRxThread(self._common, self.log)
        tx_thread = SerialTxThread(self._common)
        rx_thread.start()
        tx_thread.start()

        # Run until 'Ctrl+C' or a thread dies
        try:
            while rx_thread.is_alive() and tx_thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            rx_thread.stop()
            tx_thread.stop()

        # Wait for threads to terminate
        rx_thread.join(1.0)
        tx_thread.join(1.0)

        # Cleanup serial port
        try:
            self.port.close()
        except Exception:
            pass

        if self.log:
            self.log.flush()
