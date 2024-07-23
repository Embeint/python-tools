#!/usr/bin/env python3

"""Serial to Bluetooth gateway control tool"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import time
import threading
import queue
import ctypes
import random
import cryptography
import cryptography.exceptions

from infuse_iot.util.argparse import ValidFile
from infuse_iot.util.console import Console
from infuse_iot.commands import InfuseCommand
from infuse_iot.serial_comms import RttPort, SerialPort, SerialFrame
from infuse_iot.socket_comms import LocalServer, default_multicast_address
from infuse_iot.database import DeviceDatabase
from infuse_iot.credentials import set_api_key

from infuse_iot.epacket import (
    InfuseType,
    Auth,
    PacketReceived,
    PacketOutput,
    Interface,
    HopOutput,
)

# from infuse_iot.rpc_wrappers.security_state import security_state
from infuse_iot.tools.rpc import SubCommand as RpcSubCommand


class LocalRpcServer:
    """Basic class supporting locally generated commands"""

    def __init__(self, database: DeviceDatabase):
        self._cnt = random.randint(0, 2**31)
        self._ddb = database
        self._queued = {}

    def generate(self, command: int, args: bytes, cb):
        """Generate RPC packet from arguments"""
        cmd_bytes = bytes(RpcSubCommand.rpc_request_header(self._cnt, command)) + args
        cmd_pkt = PacketOutput(
            [HopOutput.serial(Auth.NETWORK)],
            InfuseType.RPC_CMD,
            cmd_bytes,
        )
        cmd_pkt.route[0].infuse_id = self._ddb.gateway
        self._queued[self._cnt] = cb
        self._cnt += 1
        return cmd_pkt

    def handle(self, pkt: PacketReceived):
        """Handle received packets"""
        # Only care about RPC responses
        if pkt.ptype != InfuseType.RPC_RSP:
            return

        # Determine if the response is to a command we initiated
        header = RpcSubCommand.rpc_response_header.from_buffer_copy(pkt.payload)
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
        rpc: LocalRpcServer,
    ):
        self.server = server
        self.port = port
        self.ddb = ddb
        self.rpc = rpc

    def query_device_key(self, cb_event: threading.Event = None):
        def security_state_done(pkt: PacketReceived, _: int, response: bytes):
            cloud_key = response[:32]
            device_key = response[32:64]
            network_id = int.from_bytes(response[64:68], "little")

            self.ddb.observe_security_state(
                pkt.route[0].infuse_id, cloud_key, device_key, network_id
            )
            if cb_event is not None:
                cb_event.set()

        # Generate security_state RPC
        cmd_pkt = self.rpc.generate(30000, random.randbytes(16), security_state_done)
        encrypted = cmd_pkt.to_serial(self.ddb)
        # Write to serial port
        Console.log_tx(cmd_pkt.ptype, len(encrypted))
        self.port.write(encrypted)
        if cb_event is not None:
            # Wait for the response
            cb_event.wait(1.0)


class SignaledThread(threading.Thread):
    """Thread that can be signaled to terminate"""

    def __init__(self, fn):
        self._fn = fn
        self._sig = threading.Event()
        super().__init__(target=self.run_loop)

    def stop(self):
        """Signal thread to terminate"""
        self._sig.set()

    def run_loop(self):
        """Run the thread function in a loop"""
        while not self._sig.is_set():
            self._fn()


class SerialRxThread(SignaledThread):
    """Receive serial frames from the serial port"""

    def __init__(
        self,
        common: CommonThreadState,
    ):
        self._common = common
        self._reconstructor = SerialFrame.reconstructor()
        self._reconstructor.send(None)
        self._line = ""
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
                    print(self._line)
                    self._line = ""
                else:
                    self._line += c

    def _handle_serial_frame(self, frame):
        try:
            # Decode the serial packet
            try:
                decoded = PacketReceived.from_serial(self._common.ddb, frame)
            except KeyError:
                self._common.query_device_key(None)
                Console.log_info(
                    f"Dropping {len(frame)} byte packet to query device key..."
                )
                return
            except cryptography.exceptions.InvalidTag as e:
                Console.log_error(f"Failed to decode {len(frame)} byte packet {e}")
                return

            # Iterate over all contained subpackets
            for pkt in decoded:
                Console.log_rx(pkt.ptype, len(frame))
                # Handle any local RPC responses
                self._common.rpc.handle(pkt)
                # Forward to clients
                self._common.server.broadcast(pkt)
        except (ValueError, KeyError) as e:
            print(f"Decode failed ({e})")


class SerialTxThread(SignaledThread):
    """Send serial frames down the serial port"""

    def __init__(
        self,
        common: CommonThreadState,
    ):
        self._common = common
        self._queue = queue.Queue()
        super().__init__(self._iter)

    def send(self, pkt):
        """Queue packet for transmission"""
        self._queue.put(pkt)

    def _iter(self):
        if self._common.server is None:
            time.sleep(1.0)
            return

        # Loop while there are packets to send
        while pkt := self._common.server.receive():
            if self._common.ddb.gateway is None:
                Console.log_error("Gateway address unknown")
                continue

            # Set gateway address
            assert pkt.route[0].interface == Interface.SERIAL
            pkt.route[0].infuse_id = self._common.ddb.gateway

            # Do we have the device public keys we need?
            for hop in pkt.route:
                if hop.auth == Auth.DEVICE and not self._common.ddb.has_public_key(
                    hop.infuse_id
                ):
                    cb_event = threading.Event()
                    self._common.query_device_key(cb_event)

            # Encode and encrypt payload
            encrypted = pkt.to_serial(self._common.ddb)

            # Write to serial port
            Console.log_tx(pkt.ptype, len(encrypted))
            self._common.port.write(encrypted)


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
        parser.add_argument("--api-key", type=str, help="Update saved API key")

    def __init__(self, args):
        if args.api_key is not None:
            set_api_key(args.api_key)
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
        self._common = CommonThreadState(
            self.server, self.port, self.ddb, self.rpc_server
        )
        Console.init()

    def run(self):
        # Open the serial port
        self.port.open()
        # Ping the port to get the local device ID
        self.port.ping()

        # Start threads
        rx_thread = SerialRxThread(self._common)
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
