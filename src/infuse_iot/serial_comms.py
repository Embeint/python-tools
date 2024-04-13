#!/usr/bin/env python3

import serial

class SerialFrame:
    SYNC = b"\xD5\xCA"

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
                length = int.from_bytes(buffered[2:], 'little')
            # Complete packet received
            elif len(buffered) == 4 + length:
                packet = buffered[4:]
                buffered = bytearray()

class SerialPort:
    def __init__(self, serial_port):
        self._ser = serial.Serial()
        self._ser.port = str(serial_port)
        self._ser.baudrate = 115200
        self._ser.timeout = 0.05

    def open(self):
        self._ser.open()

    def read_bytes(self, num):
        return self._ser.read(num)

    def ping(self):
        "0 length data frame to request a response"
        self._ser.write(SerialFrame.SYNC + b"\x00\x00")
        self._ser.flush()

    def write(self, packet):
        # Add header
        pkt = SerialFrame.SYNC + len(packet).to_bytes(2, 'little') + packet
        # Write packet to serial port
        self._ser.write(pkt)
        self._ser.flush()

    def close(self):
        self._ser.close()
