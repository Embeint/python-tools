#!/usr/bin/env python3

import enum
import json
import logging
import random
import select
import socket
import struct
import sys
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast
from uuid import uuid4

from typing_extensions import Self

from infuse_iot.common import InfuseType
from infuse_iot.epacket.packet import HopReceived, PacketOutput, PacketReceived
from infuse_iot.generated.tdf_definitions import readings
from infuse_iot.tdf import TDF


def default_multicast_address(port: int = 8751) -> tuple[str, int]:
    return ("224.1.1.1", port)


class GatewayControlError(RuntimeError):
    """A gateway control request failed with a stable error code."""

    def __init__(self, code: str, message: str | None = None):
        super().__init__(code)
        self.code = code
        self.message = message


class ClientNotification:
    class Type(enum.IntEnum):
        EPACKET_RECV = 0
        CONNECTION_FAILED = 1
        CONNECTION_CREATED = 2
        CONNECTION_DROPPED = 3
        KNOWN_DEVICES = 4
        COMMS_CHECK = 5

    def to_json(self) -> dict:
        """Convert class to json dictionary"""
        raise NotImplementedError

    @classmethod
    def from_json(cls, values: dict) -> Self:
        """Reconstruct class from json dictionary"""

        if values["type"] == cls.Type.COMMS_CHECK and values.get("control") is True:
            return cast(Self, ClientNotificationControl.from_json(values))
        if values["type"] == cls.Type.EPACKET_RECV:
            return cast(Self, ClientNotificationEpacketReceived.from_json(values))
        elif values["type"] == cls.Type.CONNECTION_FAILED:
            return cast(Self, ClientNotificationConnectionFailed.from_json(values))
        elif values["type"] == cls.Type.CONNECTION_CREATED:
            return cast(Self, ClientNotificationConnectionCreated.from_json(values))
        elif values["type"] == cls.Type.CONNECTION_DROPPED:
            return cast(Self, ClientNotificationConnectionDropped.from_json(values))
        elif values["type"] == cls.Type.KNOWN_DEVICES:
            return cast(Self, ClientNotificationObservedDevices.from_json(values))
        elif values["type"] == cls.Type.COMMS_CHECK:
            return cast(Self, ClientNotificationCommsCheck.from_json(values))
        raise NotImplementedError(f"Unknown notification: {values}")


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


class ClientNotificationObservedDevices(ClientNotification):
    TYPE = ClientNotification.Type.KNOWN_DEVICES

    def __init__(self, devices: dict[int, dict]):
        self.devices = devices

    def to_json(self) -> dict:
        """Convert class to json dictionary"""
        return {"type": int(self.TYPE), "devices": json.dumps(self.devices)}

    @classmethod
    def from_json(cls, values: dict) -> Self:
        raw = json.loads(values["devices"])
        decoded = {int(k): v for k, v in raw.items()}
        return cls(decoded)


class ClientNotificationControl(ClientNotification):
    # Older clients safely ignore the additional fields on a comms-check notification.
    TYPE = ClientNotification.Type.COMMS_CHECK

    def __init__(self, request_id: str, ok: bool, result: dict | None = None, code: str | None = None):
        self.request_id = request_id
        self.ok = ok
        self.result = result or {}
        self.code = code

    def to_json(self) -> dict:
        return {
            "type": int(self.TYPE),
            "request_id": self.request_id,
            "control": True,
            "ok": self.ok,
            "result": self.result,
            "code": self.code,
        }

    @classmethod
    def from_json(cls, values: dict) -> Self:
        return cls(values["request_id"], values["ok"], values.get("result"), values.get("code"))


class ClientNotificationCommsCheck(ClientNotification):
    TYPE = ClientNotification.Type.COMMS_CHECK

    def __init__(self, capabilities: dict | None = None, request_id: str | None = None):
        self.capabilities = capabilities
        self.request_id = request_id

    def to_json(self) -> dict:
        values: dict[str, Any] = {"type": int(self.TYPE)}
        if self.capabilities is not None:
            values.update(capabilities=self.capabilities, request_id=self.request_id)
        return values

    @classmethod
    def from_json(cls, values: dict) -> Self:
        return cls(values.get("capabilities"), values.get("request_id"))


class ClientNotificationConnection(ClientNotification):
    TYPE = 0

    def __init__(self, infuse_id: int):
        self.infuse_id = infuse_id

    def to_json(self) -> dict:
        return {"type": int(self.TYPE), "infuse_id": self.infuse_id}

    @classmethod
    def from_json(cls, values: dict) -> Self:
        return cls(values["infuse_id"])


class ClientNotificationConnectionResult(ClientNotificationConnection):
    """Result of a connection request.

    `request_id` identifies the request the result applies to. Results without one apply to every pending request
    for the device.
    """

    def __init__(self, infuse_id: int, request_id: int | None):
        super().__init__(infuse_id)
        self.request_id = request_id

    def answers(self, infuse_id: int, request_id: int) -> bool:
        """Whether this result applies to a connection request"""
        return self.infuse_id == infuse_id and self.request_id in (None, request_id)


class ClientNotificationConnectionFailed(ClientNotificationConnectionResult):
    """Connection to device failed"""

    TYPE = ClientNotificationConnection.Type.CONNECTION_FAILED

    def __init__(self, infuse_id: int, reason: str, request_id: int | None = None):
        super().__init__(infuse_id, request_id)
        self.reason = reason

    def to_json(self) -> dict:
        return {
            "type": int(self.TYPE),
            "infuse_id": self.infuse_id,
            "reason": self.reason,
            "request_id": self.request_id,
        }

    @classmethod
    def from_json(cls, values: dict) -> Self:
        return cls(values["infuse_id"], values["reason"], values.get("request_id"))


class ClientNotificationConnectionCreated(ClientNotificationConnectionResult):
    """Connection to device has been created"""

    TYPE = ClientNotificationConnection.Type.CONNECTION_CREATED

    def __init__(self, infuse_id: int, max_payload: int, request_id: int | None = None):
        super().__init__(infuse_id, request_id)
        self.max_payload = max_payload

    def to_json(self) -> dict:
        return {
            "type": int(self.TYPE),
            "infuse_id": self.infuse_id,
            "max_payload": self.max_payload,
            "request_id": self.request_id,
        }

    @classmethod
    def from_json(cls, values: dict) -> Self:
        return cls(values["infuse_id"], values["max_payload"], values.get("request_id"))


class ClientNotificationConnectionDropped(ClientNotificationConnection):
    """Connection to device has been lost"""

    TYPE = ClientNotificationConnection.Type.CONNECTION_DROPPED


class GatewayRequest:
    class Type(enum.IntEnum):
        EPACKET_SEND = 0
        CONNECTION_REQUEST = 1
        CONNECTION_RELEASE = 2
        KNOWN_DEVICES = 3
        COMMS_CHECK = 4
        CONTROL = 5

    def to_json(self) -> dict:
        """Convert class to json dictionary"""
        raise NotImplementedError

    @classmethod
    def from_json(cls, values: dict) -> Self:
        """Reconstruct class from json dictionary"""
        classes: dict[int, type[GatewayRequest]] = {
            cls.Type.EPACKET_SEND: GatewayRequestEpacketSend,
            cls.Type.CONNECTION_REQUEST: GatewayRequestConnectionRequest,
            cls.Type.CONNECTION_RELEASE: GatewayRequestConnectionRelease,
            cls.Type.KNOWN_DEVICES: GatewayRequestObservedDevices,
            cls.Type.COMMS_CHECK: GatewayRequestCommsCheck,
            cls.Type.CONTROL: GatewayRequestControl,
        }
        return cast(Self, classes[values["type"]].from_json(values))


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


class GatewayRequestObservedDevices(GatewayRequest):
    """Request list of known devices"""

    TYPE = GatewayRequest.Type.KNOWN_DEVICES

    def __init__(self):
        pass

    def to_json(self) -> dict:
        return {"type": int(self.TYPE)}

    @classmethod
    def from_json(cls, values: dict) -> Self:
        return cls()


class GatewayRequestControl(GatewayRequest):
    TYPE = GatewayRequest.Type.CONTROL

    def __init__(self, method: str, parameters: dict, request_id: str | None = None):
        self.method = method
        self.parameters = parameters
        self.request_id = request_id or uuid4().hex

    def to_json(self) -> dict:
        return {
            "type": int(self.TYPE),
            "method": self.method,
            "parameters": self.parameters,
            "request_id": self.request_id,
        }

    @classmethod
    def from_json(cls, values: dict) -> Self:
        if not isinstance(values["method"], str) or not isinstance(values["parameters"], dict):
            raise ValueError("Invalid control request")
        return cls(values["method"], values["parameters"], values["request_id"])


class GatewayRequestCommsCheck(GatewayRequest):
    TYPE = GatewayRequest.Type.COMMS_CHECK

    def __init__(self, request_id: str | None = None):
        self.request_id = request_id

    def to_json(self) -> dict:
        return {"type": int(self.TYPE), "request_id": self.request_id}

    @classmethod
    def from_json(cls, values: dict) -> Self:
        return cls(values.get("request_id"))


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

    class DataType(enum.IntFlag):
        COMMAND = 1
        DATA = 2
        LOGGING = 4

    def __init__(self, infuse_id: int, data_types: DataType, timeout_ms: int, request_id: int | None = None):
        super().__init__(infuse_id)
        self.data_types = data_types
        self.timeout_ms = timeout_ms
        # Identifies the requesting client to the gateway. Requests without one are interchangeable.
        self.request_id = request_id

    def to_json(self) -> dict:
        return {
            "type": int(self.TYPE),
            "infuse_id": self.infuse_id,
            "data_types": self.data_types,
            "timeout": self.timeout_ms,
            "request_id": self.request_id,
        }

    @classmethod
    def from_json(cls, values: dict) -> Self:
        return cls(values["infuse_id"], values["data_types"], values["timeout"], values.get("request_id"))


class GatewayRequestConnectionRelease(GatewayRequestConnection):
    """Release connection context to device"""

    TYPE = GatewayRequestConnection.Type.CONNECTION_RELEASE

    def __init__(self, infuse_id: int, request_id: int | None = None):
        super().__init__(infuse_id)
        # The `request_id` of the connection request being released
        self.request_id = request_id

    def to_json(self) -> dict:
        return {"type": int(self.TYPE), "infuse_id": self.infuse_id, "request_id": self.request_id}

    @classmethod
    def from_json(cls, values: dict) -> Self:
        return cls(values["infuse_id"], values.get("request_id"))


class LocalServer:
    def __init__(self, multicast_address):
        from infuse_iot.gateway_control import GatewayControl

        self.control = GatewayControl(self.broadcast)
        # Multicast output socket
        self._output_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._output_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        self._output_sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton("127.0.0.1"))
        self._output_addr = multicast_address
        if sys.platform == "win32":
            # On Windows, trying to send to a multicast socket that has no receivers in the group will result in an
            # error. To avoid this, we add the output socket to the group, even though we don't expect to receive
            # anything on it.
            mreq = struct.pack("4s4s", socket.inet_aton(multicast_address[0]), socket.inet_aton("127.0.0.1"))
            self._output_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
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
        try:
            request = GatewayRequest.from_json(json.loads(data.decode("utf-8")))
            return request if self.control.accept(request) else None
        except (ValueError, TypeError, KeyError, AttributeError, NotImplementedError):
            logging.getLogger(__name__).warning("Ignoring malformed gateway request")
            return None

    def close(self):
        self._input_sock.close()
        self._output_sock.close()


class LocalClient:
    # Gateways finish security setup after the Bluetooth connection timeout expires.
    CONNECTION_RESPONSE_MARGIN_S = 5.0

    def __init__(self, multicast_address, rx_timeout=0.2):
        # Multicast input socket
        self._input_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._input_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sys.platform == "win32":
            self._input_sock.bind(("127.0.0.1", multicast_address[1]))
        else:
            self._input_sock.bind(multicast_address)
        mreq = struct.pack("4s4s", socket.inet_aton(multicast_address[0]), socket.inet_aton("127.0.0.1"))
        self._input_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self._input_sock.settimeout(rx_timeout)
        # Unicast output socket
        self._output_addr = ("localhost", multicast_address[1] + 1)
        self._output_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._rx_lock = threading.Lock()
        self.ignored_notifications = 0
        # Connection context
        self._connection_id = None
        self._request_id = 0

    def set_rx_timeout(self, timeout):
        self._input_sock.settimeout(timeout)

    def send(self, request: GatewayRequest):
        self._output_sock.sendto(json.dumps(request.to_json()).encode("utf-8"), self._output_addr)

    def receive(self, timeout: float | None = None) -> ClientNotification | None:
        """Receive a notification, optionally limiting the configured socket timeout.

        Gateway notifications are additive, so datagrams this client cannot decode are skipped
        and the wait continues until it would otherwise end.
        """
        deadline = None
        if timeout is not None:
            timeout = max(timeout, 0)
            deadline = time.monotonic() + timeout
        # Another thread could read the datagram between select and recvfrom, so readers are serialised.
        if not self._rx_lock.acquire(timeout=-1 if timeout is None else timeout):
            return None
        try:
            configured = self._input_sock.gettimeout()
            limit = timeout
            if configured is not None:
                limit = configured if timeout is None else min(timeout, configured)
                socket_deadline = time.monotonic() + configured
                deadline = socket_deadline if deadline is None else min(deadline, socket_deadline)
            while True:
                # Wait with select rather than changing the timeout shared by threads using this socket.
                # Clamp to the limit, as coarse clocks can round the remaining time above it.
                wait = None if deadline is None or limit is None else min(limit, max(deadline - time.monotonic(), 0))
                readable, _, _ = select.select([self._input_sock], [], [], wait)
                if not readable:
                    return None
                notification = self._recv()
                if notification is not None:
                    return notification
        finally:
            self._rx_lock.release()

    def _recv(self) -> ClientNotification | None:
        try:
            data, _ = self._input_sock.recvfrom(8192)
        except TimeoutError:
            return None
        try:
            return ClientNotification.from_json(json.loads(data.decode("utf-8")))
        except (ValueError, TypeError, LookupError, AttributeError, NotImplementedError):
            # Newer gateways may send notification types or fields this client does not know.
            self.ignored_notifications += 1
            logging.getLogger(__name__).debug("Ignoring undecodable gateway notification")
            return None

    def comms_check(self, timeout: float = 0.5) -> bool:
        expiry = time.monotonic() + timeout
        self.send(GatewayRequestCommsCheck())
        while (remaining := expiry - time.monotonic()) > 0:
            rsp = self.receive(timeout=remaining)
            if rsp is None:
                continue
            if not isinstance(rsp, ClientNotificationCommsCheck):
                continue
            return True
        return False

    def connection_create(
        self, infuse_id: int, data_types: GatewayRequestConnectionRequest.DataType, timeout_ms: int
    ) -> int:
        if self._connection_id is not None:
            raise RuntimeError("Client already has a connection context")
        self._connection_id = infuse_id
        # Other clients may be requesting the same device, so the gateway reports results per request.
        self._request_id = random.getrandbits(48)

        # Send the request for the connection
        req = GatewayRequestConnectionRequest(infuse_id, data_types, timeout_ms, self._request_id)
        try:
            self.send(req)
            expiry = time.monotonic() + timeout_ms / 1000 + self.CONNECTION_RESPONSE_MARGIN_S
            # Notifications are broadcast to every client, including results of other clients' requests.
            while (remaining := expiry - time.monotonic()) > 0:
                rsp = self.receive(timeout=remaining)
                if not isinstance(rsp, (ClientNotificationConnectionCreated, ClientNotificationConnectionFailed)):
                    continue
                if not rsp.answers(infuse_id, self._request_id):
                    continue
                if isinstance(rsp, ClientNotificationConnectionCreated):
                    return rsp.max_payload
                self._connection_id = None
                raise ConnectionRefusedError(rsp.reason)
            raise TimeoutError(f"Timed out connecting to {infuse_id:016x}")
        except BaseException:
            # Cancel requests that may still be pending on the gateway. A rejected request has no context to release.
            try:
                self.connection_release()
            except OSError:
                pass
            raise

    def capabilities(self, timeout: float = 1.0) -> dict:
        # Discard stale notifications, which may fill the socket buffer and drop the reply.
        drain_expiry = time.monotonic() + 0.1
        while time.monotonic() < drain_expiry and self.receive(timeout=0) is not None:
            pass
        request_id = uuid4().hex
        self.send(GatewayRequestCommsCheck(request_id))
        deadline = time.monotonic() + timeout
        legacy = False
        while (remaining := deadline - time.monotonic()) > 0:
            notification = self.receive(timeout=remaining)
            if isinstance(notification, ClientNotificationCommsCheck):
                # Capabilities in a reply to another client's query are equally valid.
                if notification.capabilities is not None:
                    return notification.capabilities
                # A plain reply may answer another client's comms check, so only an unanswered query is legacy.
                legacy = True
        if legacy:
            return {"protocol_version": 1, "features": []}
        raise TimeoutError("Gateway did not answer capability query")

    def control_request(self, method: str, parameters: dict, timeout: float = 2.0) -> dict:
        request = GatewayRequestControl(method, parameters)
        self.send(request)
        deadline = time.monotonic() + timeout
        while (remaining := deadline - time.monotonic()) > 0:
            notification = self.receive(timeout=remaining)
            if isinstance(notification, ClientNotificationControl) and notification.request_id == request.request_id:
                if not notification.ok:
                    result = notification.result if isinstance(notification.result, dict) else {}
                    message = result.get("message")
                    raise GatewayControlError(
                        notification.code or "gateway_error", None if message is None else str(message)
                    )
                return notification.result
        raise TimeoutError(f"Gateway did not answer {method}")

    def connection_dropped(self, notification: ClientNotification | None) -> bool:
        """Whether a notification reports the loss of this client's connection."""
        return (
            isinstance(notification, ClientNotificationConnectionDropped)
            and self._connection_id is not None
            and notification.infuse_id == self._connection_id
        )

    def connection_release(self):
        if self._connection_id is None:
            return
        req = GatewayRequestConnectionRelease(self._connection_id, self._request_id)
        self.send(req)
        self._connection_id = None

    @contextmanager
    def connection(self, infuse_id: int, data_types: GatewayRequestConnectionRequest.DataType, timeout_ms: int = 10000):
        max_payload = self.connection_create(infuse_id, data_types, timeout_ms)
        try:
            yield max_payload
        finally:
            self.connection_release()

    def close(self):
        try:
            # Cleanup any lingering connection context
            if self._connection_id is not None:
                self.connection_release()
        finally:
            self._input_sock.close()
            self._output_sock.close()

    def receive_tdf(self) -> ClientNotificationEpacketReceived | None:
        msg = self.receive()
        if msg is None:
            return None
        if not isinstance(msg, ClientNotificationEpacketReceived):
            return None
        if msg.epacket.ptype != InfuseType.TDF:
            return None
        return msg

    def observe_announce(self) -> Generator[tuple[HopReceived, readings.announce | readings.announce_v2], None, None]:
        decoder = TDF()
        while True:
            msg = self.receive()
            if msg is None:
                continue
            if not isinstance(msg, ClientNotificationEpacketReceived):
                continue
            if msg.epacket.ptype != InfuseType.TDF:
                continue
            source = msg.epacket.route[0]

            for tdf in decoder.decode(msg.epacket.payload):
                if isinstance(tdf.data[0], readings.announce):
                    yield (source, tdf.data[0])
                if isinstance(tdf.data[0], readings.announce_v2):
                    yield (source, tdf.data[0])
