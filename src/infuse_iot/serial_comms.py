#!/usr/bin/env python3

import time

import pylink
import serial


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


class SerialPort:
    """Serial Port handling"""

    def __init__(self, serial_port):
        self._ser = serial.Serial()
        self._ser.port = str(serial_port)
        self._ser.baudrate = 115200
        self._ser.timeout = 0.05

    def open(self):
        """Open serial port"""
        self._ser.open()

    def read_bytes(self, num):
        """Read arbitrary number of bytes from serial port"""
        return self._ser.read(num)

    def ping(self):
        """Magic 1 byte frame to request a response"""
        self._ser.write(SerialFrame.SYNC + b"\x01\x00" + b"\x4d")
        self._ser.flush()

    def write(self, packet: bytes):
        """Write a serial frame to the port"""
        # Add header
        pkt = SerialFrame.SYNC + len(packet).to_bytes(2, "little") + packet
        # Write packet to serial port
        self._ser.write(pkt)
        self._ser.flush()

    def close(self):
        """Close the serial port"""
        self._ser.close()


class RttPort:
    """Segger RTT handling"""

    def __init__(self, rtt_device):
        self._jlink = pylink.JLink()
        self._name = rtt_device
        self._modem_trace = None
        self._modem_trace_buf = 0

    def open(self):
        """Open RTT port"""
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
                self._modem_trace = open(f, mode="wb")
                self._modem_trace_buf = desc.BufferIndex

    def read_bytes(self, num):
        """Read arbitrary number of bytes from RTT"""
        if self._modem_trace is not None:
            trace_data = bytes(self._jlink.rtt_read(self._modem_trace_buf, 1024))
            if len(trace_data) > 0:
                self._modem_trace.write(trace_data)

        return bytes(self._jlink.rtt_read(0, num))

    def ping(self):
        """Magic 1 byte frame to request a response"""
        self._jlink.rtt_write(0, SerialFrame.SYNC + b"\x01\x00" + b"\x4d")

    def write(self, packet: bytes):
        """Write a serial frame to the port"""
        # Add header
        pkt = SerialFrame.SYNC + len(packet).to_bytes(2, "little") + packet
        while True:
            res = self._jlink.rtt_write(0, pkt)
            if res == len(pkt):
                break
            pkt = pkt[res:]
            time.sleep(0.1)

    def close(self):
        """Close the RTT port"""
        self._jlink.rtt_stop()
        self._jlink.close()
        if self._modem_trace is not None:
            self._modem_trace.flush()
            self._modem_trace.close()
