#!/usr/bin/env python3

import socket
import struct
import json

from infuse_iot.epacket import data_types

def default_multicast_address():
    return ('224.1.1.1', 8751)

class LocalServer:
    def __init__(self, multicast_address):
        # Multicast output socket
        self._output_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._output_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        self._output_addr = multicast_address
        # Single input socket
        unicast_address = ('localhost', multicast_address[1] + 1)
        self._input_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._input_sock.bind(unicast_address)
        self._input_sock.settimeout(0.2)

    def broadcast(self, packet: dict):
        self._output_sock.sendto(json.dumps(packet).encode('utf-8'), self._output_addr)

    def receive(self):
        try:
            data, _ = self._input_sock.recvfrom(8192)
        except TimeoutError:
            return None
        return json.loads(data.decode('utf-8'))

    def close(self):
        self._input_sock.close()
        self._output_addr.close()

class LocalClient:
    def __init__(self, multicast_address, rx_timeout=0.2):
        # Multicast input socket
        self._input_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._input_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._input_sock.bind(multicast_address)
        mreq = struct.pack("4sl", socket.inet_aton(multicast_address[0]), socket.INADDR_ANY)
        self._input_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self._input_sock.settimeout(rx_timeout)
        # Unicast output socket
        self._output_addr = ('localhost', multicast_address[1] + 1)
        self._output_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

    def set_rx_timeout(self, timeout):
        self._input_sock.settimeout(timeout)

    def send(self, packet: dict):
        self._output_sock.sendto(json.dumps(packet).encode('utf-8'), self._output_addr)

    def receive(self):
        try:
            data, _ = self._input_sock.recvfrom(8192)
        except TimeoutError:
            return None
        pkt = json.loads(data.decode('utf-8'))
        pkt['pkt_type'] = data_types(pkt['pkt_type'])
        return pkt

    def close(self):
        self._input_sock.close()
