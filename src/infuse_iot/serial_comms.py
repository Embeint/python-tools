#!/usr/bin/env python3

import time
from abc import ABCMeta, abstractmethod

import pylink
import serial
from pyocd.core.helpers import ConnectHelper
from pyocd.debug.rtt import GenericRTTControlBlock


class SerialFrame:
    """Serial frame reconstructor"""

    SYNC = b"\xd5\xca"

    @classmethod
    def reconstructor(cls):
        length = 0
        buffered = bytearray()
        packet = None
        while True:
            # Is the current byte part of a packet?
            consumed = len(buffered) > 0 or packet is not None
            # Get next byte from port, yield current state
            val = yield consumed, packet
            packet = None
            # Append value to buffer
            buffered.append(val)
            # Wait for packet sync bytes
            if len(buffered) <= 2:
                if val != cls.SYNC[len(buffered) - 1]:
                    buffered = bytearray()
                    continue
            # Store length
            elif len(buffered) == 4:
                length = int.from_bytes(buffered[2:], "little")
            # Complete packet received
            elif len(buffered) == 4 + length:
                packet = buffered[4:]
                buffered = bytearray()


class SerialLike(metaclass=ABCMeta):
    @abstractmethod
    def open(self) -> None:
        """Open serial port"""

    @abstractmethod
    def read_bytes(self, num: int):
        """Read arbitrary number of bytes from serial port"""

    @abstractmethod
    def ping(self):
        """Magic 1 byte frame to request a response"""

    @abstractmethod
    def write(self, packet: bytes):
        """Write a serial frame to the port"""

    @abstractmethod
    def close(self):
        """Close the serial port"""


class SerialPort(SerialLike):
    """Serial Port handling"""

    def __init__(self, serial_port, baudrate=115200):
        self._ser = serial.Serial()
        self._ser.port = str(serial_port)
        self._ser.baudrate = baudrate
        self._ser.timeout = 0.05
        # Prepend leading 0's for high baudrates to give sleepy
        # receivers (STM32) time to wake up on RX before real data arrives.
        self._prefix = b"\x00\x00" if baudrate > 115200 else b""

    def open(self):
        self._ser.open()

    def read_bytes(self, num):
        return self._ser.read(num)

    def ping(self):
        self._ser.write(self._prefix + SerialFrame.SYNC + b"\x01\x00" + b"\x4d")
        self._ser.flush()

    def write(self, packet: bytes):
        # Add header
        pkt = self._prefix + SerialFrame.SYNC + len(packet).to_bytes(2, "little") + packet
        # Write packet to serial port
        self._ser.write(pkt)
        self._ser.flush()

    def close(self):
        self._ser.close()


class RttPort(SerialLike):
    """Segger RTT handling"""

    def __init__(self, rtt_device):
        self._jlink = pylink.JLink()
        self._name = rtt_device
        self._modem_trace = None
        self._modem_trace_buf = 0

    def open(self):
        self._jlink.open()
        self._jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
        self._jlink.connect(self._name, 4000)
        self._jlink.rtt_start()

        # Loop until JLink initialised properly
        while True:
            try:
                num_up = self._jlink.rtt_get_num_up_buffers()
                _num_down = self._jlink.rtt_get_num_down_buffers()
                break
            except pylink.errors.JLinkRTTException:
                time.sleep(0.05)

        # Do a search and see if we have a modem trace file
        for i in range(num_up):
            desc = self._jlink.rtt_get_buf_descriptor(i, True)
            if desc.name == "modem_trace":
                f = f"{int(time.time())}_nrf_modem_trace.bin"
                print(f"Found nRF LTE modem trace channel (opening {f:s})")
                self._modem_trace = open(f, mode="wb")  # noqa: SIM115
                self._modem_trace_buf = desc.BufferIndex

    def read_bytes(self, num):
        if self._modem_trace is not None:
            trace_data = bytes(self._jlink.rtt_read(self._modem_trace_buf, 1024))
            if len(trace_data) > 0:
                self._modem_trace.write(trace_data)

        return bytes(self._jlink.rtt_read(0, num))

    def ping(self):
        self._jlink.rtt_write(0, SerialFrame.SYNC + b"\x01\x00" + b"\x4d")

    def write(self, packet: bytes):
        # Add header
        pkt = SerialFrame.SYNC + len(packet).to_bytes(2, "little") + packet
        while True:
            res = self._jlink.rtt_write(0, pkt)
            if res == len(pkt):
                break
            pkt = pkt[res:]
            time.sleep(0.1)

    def close(self):
        self._jlink.rtt_stop()
        self._jlink.close()
        if self._modem_trace is not None:
            self._modem_trace.flush()
            self._modem_trace.close()


class PyOcdPort(SerialLike):
    """PyOcd RTT handling"""

    def __init__(self, target: str):
        self._session = ConnectHelper.session_with_chosen_probe(auto_open=False, options={"target_override": target})
        self._target = self._session.target
        self._rtt = GenericRTTControlBlock(self._target)

    def open(self):
        self._session.open()
        self._target.resume()
        self._rtt.start()
        self._up_chan = self._rtt.up_channels[0]
        self._down_chan = self._rtt.down_channels[0]

    def read_bytes(self, num):
        return self._up_chan.read()

    def ping(self):
        self._down_chan.write(SerialFrame.SYNC + b"\x01\x00" + b"\x4d")

    def write(self, packet: bytes):
        # Add header
        pkt = SerialFrame.SYNC + len(packet).to_bytes(2, "little") + packet
        while True:
            res = self._down_chan.write(pkt)
            if res == len(pkt):
                break
            pkt = pkt[res:]
            time.sleep(0.1)

    def close(self):
        self._session.close()
