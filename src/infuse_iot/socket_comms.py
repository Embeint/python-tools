#!/usr/bin/env python3

import enum
import json
import socket
import struct
from typing import cast

from typing_extensions import Self

from infuse_iot.epacket.packet import PacketOutput, PacketReceived


def default_multicast_address():
    return ("224.1.1.1", 8751)


class ClientNotification:
    class Type(enum.IntEnum):
        EPACKET_RECV = 0
        CONNECTION_FAILED = 1
        CONNECTION_CREATED = 2
        CONNECTION_DROPPED = 3

    def to_json(self) -> dict:
        """Convert class to json dictionary"""
        raise NotImplementedError

    @classmethod
    def from_json(cls, values: dict) -> Self:
        """Reconstruct class from json dictionary"""

        if values["type"] == cls.Type.EPACKET_RECV:
            return cast(Self, ClientNotificationEpacketReceived.from_json(values))
        elif values["type"] == cls.Type.CONNECTION_FAILED:
            return cast(Self, ClientNotificationConnectionFailed.from_json(values))
        elif values["type"] == cls.Type.CONNECTION_CREATED:
            return cast(Self, ClientNotificationConnectionCreated.from_json(values))
        elif values["type"] == cls.Type.CONNECTION_DROPPED:
            return cast(Self, ClientNotificationConnectionDropped.from_json(values))
        raise NotImplementedError


class ClientNotificationEpacketReceived(ClientNotification):
    TYPE = ClientNotification.Type.EPACKET_RECV

    def __init__(self, epacket: PacketReceived):
        self.epacket = epacket

    def to_json(self) -> dict:
        """Convert class to json dictionary"""
        return {"type": int(self.TYPE), "epacket": self.epacket.to_json()}

    @classmethod
    def from_json(cls, values: dict) -> Self:
        return cls(PacketReceived.from_json(values["epacket"]))


class ClientNotificationConnection(ClientNotification):
    TYPE = 0

    def __init__(self, infuse_id: int):
        self.infuse_id = infuse_id

    def to_json(self) -> dict:
        return {"type": int(self.TYPE), "infuse_id": self.infuse_id}

    @classmethod
    def from_json(cls, values: dict) -> Self:
        return cls(values["infuse_id"])


class ClientNotificationConnectionFailed(ClientNotificationConnection):
    """Connection to device failed"""

    TYPE = ClientNotificationConnection.Type.CONNECTION_FAILED


class ClientNotificationConnectionCreated(ClientNotificationConnection):
    """Connection to device has been created"""

    TYPE = ClientNotificationConnection.Type.CONNECTION_CREATED


class ClientNotificationConnectionDropped(ClientNotificationConnection):
    """Connection to device has been lost"""

    TYPE = ClientNotificationConnection.Type.CONNECTION_DROPPED


class GatewayRequest:
    class Type(enum.IntEnum):
        EPACKET_SEND = 0
        CONNECTION_REQUEST = 1
        CONNECTION_RELEASE = 2

    def to_json(self) -> dict:
        """Convert class to json dictionary"""
        raise NotImplementedError

    @classmethod
    def from_json(cls, values: dict) -> Self:
        """Reconstruct class from json dictionary"""
        if values["type"] == cls.Type.EPACKET_SEND:
            return cast(Self, GatewayRequestEpacketSend.from_json(values))
        elif values["type"] == cls.Type.CONNECTION_REQUEST:
            return cast(Self, GatewayRequestConnectionRequest.from_json(values))
        elif values["type"] == cls.Type.CONNECTION_RELEASE:
            return cast(Self, GatewayRequestConnectionRelease.from_json(values))
        raise NotImplementedError


class GatewayRequestEpacketSend(GatewayRequest):
    """Request packet to be forwarded to device"""

    TYPE = GatewayRequest.Type.EPACKET_SEND

    def __init__(self, epacket: PacketOutput):
        self.epacket = epacket

    def to_json(self) -> dict:
        return {"type": int(self.TYPE), "epacket": self.epacket.to_json()}

    @classmethod
    def from_json(cls, values: dict) -> Self:
        return cls(PacketOutput.from_json(values["epacket"]))


class GatewayRequestConnection(GatewayRequest):
    TYPE = 0

    def __init__(self, infuse_id: int):
        self.infuse_id = infuse_id

    def to_json(self) -> dict:
        return {"type": int(self.TYPE), "infuse_id": self.infuse_id}

    @classmethod
    def from_json(cls, values: dict) -> Self:
        return cls(values["infuse_id"])


class GatewayRequestConnectionRequest(GatewayRequestConnection):
    """Request connection context to device"""

    TYPE = GatewayRequestConnection.Type.CONNECTION_REQUEST


class GatewayRequestConnectionRelease(GatewayRequestConnection):
    """Release connection context to device"""

    TYPE = GatewayRequestConnection.Type.CONNECTION_RELEASE


class LocalServer:
    def __init__(self, multicast_address):
        # Multicast output socket
        self._output_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._output_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        self._output_addr = multicast_address
        # Single input socket
        unicast_address = ("localhost", multicast_address[1] + 1)
        self._input_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._input_sock.bind(unicast_address)
        self._input_sock.settimeout(0.2)

    def broadcast(self, notification: ClientNotification):
        self._output_sock.sendto(json.dumps(notification.to_json()).encode("utf-8"), self._output_addr)

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
        self._input_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._input_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._input_sock.bind(multicast_address)
        mreq = struct.pack("4sl", socket.inet_aton(multicast_address[0]), socket.INADDR_ANY)
        self._input_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self._input_sock.settimeout(rx_timeout)
        # Unicast output socket
        self._output_addr = ("localhost", multicast_address[1] + 1)
        self._output_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Connection context
        self._connection_id = None

    def set_rx_timeout(self, timeout):
        self._input_sock.settimeout(timeout)

    def send(self, request: GatewayRequest):
        self._output_sock.sendto(json.dumps(request.to_json()).encode("utf-8"), self._output_addr)

    def receive(self) -> ClientNotification | None:
        try:
            data, _ = self._input_sock.recvfrom(8192)
        except TimeoutError:
            return None
        return ClientNotification.from_json(json.loads(data.decode("utf-8")))

    def connection_create(self, infuse_id: int):
        self._connection_id = infuse_id

        # Send the request for the connection
        req = GatewayRequestConnectionRequest(infuse_id)
        self.send(req)
        # Wait for response from the server
        while rsp := self.receive():
            if isinstance(rsp, ClientNotificationConnectionCreated):
                break
            elif isinstance(rsp, ClientNotificationConnectionFailed):
                raise ConnectionRefusedError

    def connection_release(self):
        assert self._connection_id is not None

        req = GatewayRequestConnectionRelease(
            self._connection_id,
        )
        self.send(req)
        self._connection_id = None

    def close(self):
        # Cleanup any lingering connection context
        if self._connection_id:
            req = GatewayRequestConnectionRelease(
                self._connection_id,
            )
            self.send(req)
        # Close the socket
        self._input_sock.close()
