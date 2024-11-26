#!/usr/bin/env python3

import socket
import struct
import json
import enum

from typing import Dict
from typing_extensions import Self

from infuse_iot.epacket.packet import PacketReceived, PacketOutput


def default_multicast_address():
    return ("224.1.1.1", 8751)


class ClientNotification:
    class Type(enum.IntEnum):
        EPACKET_RECV = 0

    def __init__(self, notification_type: Type, epacket: PacketReceived | None = None):
        self.type = notification_type
        self.epacket = epacket

    def to_json(self) -> Dict:
        """Convert class to json dictionary"""
        out = {"type": int(self.type)}
        if self.epacket:
            out["epacket"] = self.epacket.to_json()
        return out

    @classmethod
    def from_json(cls, values: Dict) -> Self:
        """Reconstruct class from json dictionary"""
        if j := values.get("epacket", None):
            epacket = PacketReceived.from_json(j)
        else:
            epacket = None

        return cls(
            notification_type=cls.Type(values["type"]),
            epacket=epacket,
        )


class GatewayRequest:
    class Type(enum.IntEnum):
        EPACKET_SEND = 0

    def __init__(
        self,
        notification_type: Type,
        epacket: PacketOutput | None = None,
    ):
        self.type = notification_type
        self.epacket = epacket

    def to_json(self) -> Dict:
        """Convert class to json dictionary"""
        out = {"type": int(self.type)}
        if self.epacket:
            out["epacket"] = self.epacket.to_json()
        return out

    @classmethod
    def from_json(cls, values: Dict) -> Self:
        """Reconstruct class from json dictionary"""
        if j := values.get("epacket", None):
            epacket = PacketOutput.from_json(j)
        else:
            epacket = None

        return cls(
            notification_type=cls.Type(values["type"]),
            epacket=epacket,
        )


class LocalServer:
    def __init__(self, multicast_address):
        # Multicast output socket
        self._output_sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
        )
        self._output_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        self._output_addr = multicast_address
        # Single input socket
        unicast_address = ("localhost", multicast_address[1] + 1)
        self._input_sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
        )
        self._input_sock.bind(unicast_address)
        self._input_sock.settimeout(0.2)

    def broadcast(self, notification: ClientNotification):
        self._output_sock.sendto(
            json.dumps(notification.to_json()).encode("utf-8"), self._output_addr
        )

    def receive(self) -> GatewayRequest | None:
        try:
            data, _ = self._input_sock.recvfrom(8192)
        except TimeoutError:
            return None
        return GatewayRequest.from_json(json.loads(data.decode("utf-8")))

    def close(self):
        self._input_sock.close()
        self._output_addr.close()


class LocalClient:
    def __init__(self, multicast_address, rx_timeout=0.2):
        # Multicast input socket
        self._input_sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
        )
        self._input_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._input_sock.bind(multicast_address)
        mreq = struct.pack(
            "4sl", socket.inet_aton(multicast_address[0]), socket.INADDR_ANY
        )
        self._input_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self._input_sock.settimeout(rx_timeout)
        # Unicast output socket
        self._output_addr = ("localhost", multicast_address[1] + 1)
        self._output_sock = socket.socket(
            socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
        )

    def set_rx_timeout(self, timeout):
        self._input_sock.settimeout(timeout)

    def send(self, request: GatewayRequest):
        self._output_sock.sendto(
            json.dumps(request.to_json()).encode("utf-8"), self._output_addr
        )

    def receive(self) -> ClientNotification | None:
        try:
            data, _ = self._input_sock.recvfrom(8192)
        except TimeoutError:
            return None
        return ClientNotification.from_json(json.loads(data.decode("utf-8")))

    def close(self):
        self._input_sock.close()
