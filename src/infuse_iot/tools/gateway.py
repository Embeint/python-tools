#!/usr/bin/env python3

"""Serial to Bluetooth gateway control tool"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import time
import threading
import queue
import datetime
import cryptography

import colorama

import cryptography.exceptions
from infuse_iot.argparse import ValidFile
from infuse_iot.commands import InfuseCommand
from infuse_iot.serial_comms import SerialPort, SerialFrame
from infuse_iot.socket_comms import LocalServer, default_multicast_address
from infuse_iot.epacket import ePacketDecoder, ePacketSerialHeader, data_types

gateway_addr = None

class Console:
    """Common terminal logging functions"""
    @staticmethod
    def log_error(message):
        Console.log(datetime.datetime.now(), colorama.Fore.RED, message)

    @staticmethod
    def log_info(message):
        Console.log(datetime.datetime.now(), colorama.Fore.MAGENTA, message)

    @staticmethod
    def log_tx(data_type, length):
        Console.log(datetime.datetime.now(), colorama.Fore.BLUE, f"TX {data_type.name} {length} bytes")

    @staticmethod
    def log_rx(data_type, length):
        Console.log(datetime.datetime.now(), colorama.Fore.GREEN, f"RX {data_type.name} {length} bytes")

    @staticmethod
    def log(timestamp: datetime.datetime, colour, string: str):
        ts = timestamp.strftime("%H:%M:%S.%f")[:-3]
        print(f"[{ts}]{colour} {string}")

class SignaledThread(threading.Thread):
    def __init__(self, fn):
        self._fn = fn
        self._sig = threading.Event()
        super().__init__(target=self.run_loop)

    def stop(self):
        self._sig.set()

    def run_loop(self):
        while not self._sig.is_set():
            self._fn()

class SerialRxThread(SignaledThread):
    def __init__(self, server: LocalServer, port: SerialPort):
        self._server = server
        self._port = port
        self._decoder = ePacketDecoder()
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
                if c == '\n':
                    print(self._line)
                    self._line = ""
                else:
                    self._line += c

    def _handle_serial_frame(self, frame):
        try:
            header, data_len = ePacketSerialHeader.parse(frame)
            global gateway_addr
            if gateway_addr is None:
                Console.log_info(f"Local gateway is {header.device_id}")
                gateway_addr = header.device_id
            # Decode the serial packet
            try:
                decoded = self._decoder.decode_serial(frame)
            except cryptography.exceptions.InvalidTag as e:
                Console.log_error(f"Failed to decode {data_len} byte packet")
                return
            Console.log_rx(decoded['pkt_type'], data_len)
            # Forward to clients
            self._server.broadcast(decoded)
        except (ValueError, KeyError) as e:
            print(f"Decode failed ({e})")

class SerialTxThread(SignaledThread):
    def __init__(self, server: LocalServer, port: SerialPort):
        self._server = server
        self._port = port
        self._queue = queue.Queue()
        self._decoder = ePacketDecoder()
        super().__init__(self._iter)

    def send(self, pkt):
        self._queue.put(pkt)

    def _iter(self):

        # Loop while there are packets to receive
        while pkt := self._server.receive():
            global gateway_addr
            if gateway_addr is None:
                Console.log_error(f"Gateway address unknown")
                continue

            # Assign destination address
            pkt['device'] = gateway_addr

            # Encode and encrypt payload
            encrypted = self._decoder.encode_serial(pkt)

            # Write to serial port
            Console.log_tx(data_types(pkt['pkt_type']), len(pkt['raw']) // 2)
            self._port.write(encrypted)


class gateway(InfuseCommand):
    HELP = "Connect to a local gateway device"
    DESCRIPTION = "Connect to a gateway device over serial and route commands to Bluetooth devices"

    def add_parser(cls, parser):
        parser.add_argument('--serial', type=ValidFile, required=True, help='Gateway serial port')

    def __init__(self, args):
        self.port = SerialPort(args.serial)
        self.server = LocalServer(default_multicast_address())
        colorama.init(autoreset=True)

    def run(self):
        # Open the serial port
        self.port.open()
        # Ping the port to get the local device ID
        self.port.ping()

        # Start threads
        rx_thread = SerialRxThread(self.server, self.port)
        tx_thread = SerialTxThread(self.server, self.port)
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
        except:
            pass
