#!/usr/bin/env python3

"""Serial to Bluetooth gateway control tool"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import time
import threading
import queue
import ctypes
import datetime
import random
import cryptography
import cryptography.exceptions

import colorama

from infuse_iot.util.argparse import ValidFile
from infuse_iot.util.console import Console
from infuse_iot.commands import InfuseCommand
from infuse_iot.serial_comms import SerialPort, SerialFrame
from infuse_iot.socket_comms import LocalServer, default_multicast_address
from infuse_iot.epacket import ePacketIn, ePacketOut, ePacketHop, ePacketHopOut
from infuse_iot.database import DeviceDatabase

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
        cmd_pkt = ePacketOut(
            [ePacketHopOut.serial(ePacketHopOut.auths.NETWORK)],
            ePacketOut.types.RPC_CMD,
            cmd_bytes,
        )
        cmd_pkt.route[0].address = self._ddb.gateway
        self._queued[self._cnt] = cb
        self._cnt += 1
        return cmd_pkt

    def handle(self, pkt: ePacketIn):
        """Handle received packets"""
        # Only care about RPC responses
        if pkt.ptype != ePacketIn.types.RPC_RSP:
            return

        # Determine if the response is to a command we initiated
        header = RpcSubCommand.rpc_response_header.from_buffer_copy(pkt.payload)
        if header.request_id not in self._queued:
            return

        # Run the callback
        cb = self._queued.pop(header.request_id)
        if cb is not None:
            cb(pkt, header.return_code, pkt.payload[ctypes.sizeof(header) :])


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
        server: LocalServer,
        port: SerialPort,
        ddb: DeviceDatabase,
        rpc: LocalRpcServer,
    ):
        self._server = server
        self._port = port
        self._ddb = ddb
        self._rpc = rpc
        self._reconstructor = SerialFrame.reconstructor()
        self._reconstructor.send(None)
        self._line = ""
        super().__init__(self._iter)

    def _iter(self):
        # Read bytes from serial port
        rx = self._port.read_bytes(1024)
        if len(rx) == 0:
            return
        for b in rx:
            frame_byte, frame = self._reconstructor.send(b)
            if frame:
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
                decoded = ePacketIn.from_serial(self._ddb, frame)
            except (KeyError, cryptography.exceptions.InvalidTag) as e:
                Console.log_error(f"Failed to decode {len(frame)} byte packet {e}")
                return
            Console.log_rx(decoded.ptype, len(frame))
            # Handle any local RPC responses
            self._rpc.handle(decoded)
            # Forward to clients
            self._server.broadcast(decoded)
        except (ValueError, KeyError) as e:
            print(f"Decode failed ({e})")


class SerialTxThread(SignaledThread):
    """Send serial frames down the serial port"""

    def __init__(
        self,
        server: LocalServer,
        port: SerialPort,
        ddb: DeviceDatabase,
        rpc: LocalRpcServer,
    ):
        self._server = server
        self._port = port
        self._ddb = ddb
        self._rpc = rpc
        self._queue = queue.Queue()
        super().__init__(self._iter)

    def send(self, pkt):
        """Queue packet for transmission"""
        self._queue.put(pkt)

    def _iter(self):
        # Loop while there are packets to send
        while pkt := self._server.receive():
            if self._ddb.gateway is None:
                Console.log_error("Gateway address unknown")
                continue

            # Set gateway address
            if pkt.route[-1].interface == ePacketHop.interfaces.SERIAL:
                pkt.route[-1].address = self._ddb.gateway

            # Do we have the final public key if required?
            final = pkt.route[0]
            if final.auth == ePacketHop.auths.DEVICE and not self._ddb.has_public_key(
                final.address
            ):
                cb_event = threading.Event()

                def security_state_done(pkt: ePacketIn, _: int, response: bytes):
                    cloud_key = response[:32]
                    device_key = response[32:64]
                    network_id = int.from_bytes(response[64:68], "little")

                    self._ddb.observe_security_state(
                        pkt.route[0].address, cloud_key, device_key, network_id
                    )
                    cb_event.set()

                # Generate security_state RPC
                cmd_pkt = self._rpc.generate(
                    30000, random.randbytes(16), security_state_done
                )
                encrypted = cmd_pkt.to_serial(self._ddb)
                # Write to serial port
                Console.log_tx(cmd_pkt.ptype, len(encrypted))
                self._port.write(encrypted)
                # Wait for the response
                cb_event.wait(1.0)

            # Encode and encrypt payload
            encrypted = pkt.to_serial(self._ddb)

            # Write to serial port
            Console.log_tx(pkt.ptype, len(encrypted))
            self._port.write(encrypted)


class SubCommand(InfuseCommand):
    NAME = "gateway"
    HELP = "Connect to a local gateway device"
    DESCRIPTION = "Connect to a gateway device over serial and route commands to Bluetooth devices"

    @classmethod
    def add_parser(cls, parser):
        parser.add_argument(
            "--serial", type=ValidFile, required=True, help="Gateway serial port"
        )

    def __init__(self, args):
        self.port = SerialPort(args.serial)
        self.server = LocalServer(default_multicast_address())
        self.ddb = DeviceDatabase()
        self.rpc_server = LocalRpcServer(self.ddb)
        Console.init()

    def run(self):
        # Open the serial port
        self.port.open()
        # Ping the port to get the local device ID
        self.port.ping()

        # Start threads
        rx_thread = SerialRxThread(self.server, self.port, self.ddb, self.rpc_server)
        tx_thread = SerialTxThread(self.server, self.port, self.ddb, self.rpc_server)
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
