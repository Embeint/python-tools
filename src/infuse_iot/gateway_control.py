"""Capability negotiation and expiring ownership of gateway operations."""

import logging
import threading
import time
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from infuse_iot.common import InfuseType
from infuse_iot.epacket.interface import ID as Interface
from infuse_iot.epacket.packet import PacketReceived
from infuse_iot.socket_comms import (
    DEFAULT_OPERATION_DURATION_S,
    ClientNotification,
    ClientNotificationCommsCheck,
    ClientNotificationConnection,
    ClientNotificationConnectionCreated,
    ClientNotificationConnectionDropped,
    ClientNotificationConnectionFailed,
    ClientNotificationConnectionResult,
    ClientNotificationControl,
    ClientNotificationEpacketReceived,
    GatewayControlError,
    GatewayRequest,
    GatewayRequestCommsCheck,
    GatewayRequestConnectionRelease,
    GatewayRequestConnectionRequest,
    GatewayRequestControl,
    GatewayRequestEpacketSend,
)
from infuse_iot.version import __version__

# A released link reports its teardown within this time of any pending setup completing.
TEARDOWN_TIMEOUT_S = 15.0
# Upper bound on the setup time of a pending connection request.
MAX_SETUP_S = 60.0
# Legacy connections to the gateway's own device never drop, so they expire when idle.
LOCAL_IDLE_S = 60.0


@dataclass
class _Operation:
    device_id: int
    owner: str
    expires: float
    duration: float
    # Requests not yet released by the owner or failed by the gateway, and whether any were made.
    requests: Counter[int | None] = field(default_factory=Counter)
    linked: bool = False
    last_request_id: int | None = None

    @property
    def connections(self) -> int:
        return sum(self.requests.values())

    def renew(self) -> None:
        self.expires = time.monotonic() + self.duration


class GatewayControl:
    """Coordinate operations at the gateway, across all attached clients.

    Operation IDs prevent accidental cross-client interference; they are not
    authentication credentials. The existing local UDP channel remains trusted.
    """

    def __init__(self, broadcast: Callable[[ClientNotification], None], kind: str = "serial"):
        self.kind = kind
        self.instance_id = uuid4().hex
        self._broadcast = broadcast
        self._lock = threading.RLock()
        self._operation: _Operation | None = None
        # Answered legacy connection references on each device's current link.
        self._legacy: dict[int, Counter[int | None]] = {}
        # Legacy requests awaiting their result, and their longest setup time. The gateway still answers them after
        # the device's link drops or closes, so its teardown must not clear them.
        self._awaiting: dict[int, tuple[Counter[int | None], float]] = {}
        self._legacy_seen: dict[int, float] = {}
        # Devices that may have a backend link, and when their pending setup ends.
        self._links: dict[int, float] = {}
        # Devices whose link was established, so the gateway reports its teardown.
        self._established: set[int] = set()
        # Released devices awaiting a teardown notification, and when to stop waiting.
        self._closing: dict[int, float] = {}
        self._cleanup: deque[GatewayRequest] = deque()
        self.handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}
        # Devices served by the gateway itself hold no link and never report a teardown.
        self.is_local: Callable[[int], bool] = lambda _device: False

    def capabilities(self) -> dict[str, Any]:
        return {
            "protocol_version": 2,
            "version": __version__,
            "instance_id": self.instance_id,
            "gateway_kind": self.kind,
            "features": ["operation_ownership", *sorted(self.handlers)],
        }

    def _expire(self) -> None:
        now = time.monotonic()
        if self._operation is not None and self._operation.expires <= now:
            self._release()
        for device, deadline in list(self._closing.items()):
            if deadline <= now:
                logging.getLogger(__name__).warning("No teardown reported for device %s", device)
                self._link_ended(device, dropped=True)
        for device in [device for device in {*self._legacy, *self._awaiting} if self.is_local(device)]:
            if self._legacy_seen.get(device, 0.0) + LOCAL_IDLE_S <= now:
                self._legacy.pop(device, None)
                self._awaiting.pop(device, None)

    def _release(self) -> None:
        operation, self._operation = self._operation, None
        if operation is None or self.is_local(operation.device_id):
            return
        device = operation.device_id
        requests = list(operation.requests.elements())
        if not requests and operation.linked and device in self._links and device not in self._closing:
            # A link completed after its request was failed has no reference, but the operation created it.
            requests = [operation.last_request_id]
        if requests:
            self._mark_closing(device, force=True)
            self._cleanup.extend(GatewayRequestConnectionRelease(device, request_id) for request_id in requests)

    def _mark_closing(self, device: int, force: bool = False) -> None:
        """Wait for a released link's teardown, whose results a new operation could otherwise inherit."""
        if self.is_local(device) or (device not in self._links and not force):
            return
        self._closing[device] = max(time.monotonic(), self._links.get(device, 0.0)) + TEARDOWN_TIMEOUT_S

    @staticmethod
    def _setup_time(request: GatewayRequestConnectionRequest) -> float:
        try:
            setup = float(request.timeout_ms) / 1000
        except (TypeError, ValueError, OverflowError):
            return MAX_SETUP_S
        return setup if 0 <= setup <= MAX_SETUP_S else MAX_SETUP_S

    def _track_link(self, device: int, setup: float) -> None:
        if not self.is_local(device):
            self._links[device] = max(self._links.get(device, 0.0), time.monotonic() + setup)

    def _link_ended(self, device: int, dropped: bool) -> None:
        """Forget a link that dropped or failed, keeping legacy requests still awaiting a result if it dropped."""
        self._closing.pop(device, None)
        self._links.pop(device, None)
        self._legacy.pop(device, None)
        self._established.discard(device)
        requests, setup = self._awaiting.pop(device, (Counter(), 0.0))
        # Awaiting requests get a new link after a teardown, but waiting clients take a failure as their own result.
        if dropped and requests:
            self._awaiting[device] = (requests, setup)
            self._track_link(device, setup)

    def cleanup(self) -> list[GatewayRequest]:
        with self._lock:
            self._expire()
            requests = list(self._cleanup)
            self._cleanup.clear()
            return requests

    def _control(self, request: GatewayRequestControl) -> None:
        """Answer a control request, always replying so the client does not wait for its timeout."""
        try:
            reply = ClientNotificationControl(request.request_id, True, result=self._control_result(request))
        except GatewayControlError as error:
            reply = ClientNotificationControl(request.request_id, False, {"message": error.message}, error.code)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
            reply = ClientNotificationControl(request.request_id, False, {"message": str(error)}, "invalid_request")
        except Exception as error:
            logging.getLogger(__name__).exception("Gateway control request failed")
            reply = ClientNotificationControl(request.request_id, False, {"message": str(error)}, "internal_error")
        self._broadcast(reply)

    def _control_result(self, request: GatewayRequestControl) -> dict[str, Any]:
        values = request.parameters
        if request.method == "acquire_operation":
            device = int(values["device_id"], 16)
            owner = str(values["owner"])
            duration = float(values.get("duration_seconds", DEFAULT_OPERATION_DURATION_S))
            if not 0 <= device < 2**64:
                raise ValueError("Invalid device ID, use the gateway's own ID rather than InfuseID.GATEWAY")
            if not 1 <= len(owner) <= 128 or not 5 <= duration <= 300:
                raise ValueError("Invalid owner or duration (5..300 seconds)")
            if self._operation is not None:
                if self._operation.owner != owner or self._operation.device_id != device:
                    raise GatewayControlError("device_busy", "Another operation is active")
            elif any(self._legacy.values()) or self._awaiting:
                raise GatewayControlError("device_busy", "A connection outside an operation is active")
            elif self._cleanup or self._closing:
                raise GatewayControlError("device_busy", "A released connection is closing")
            else:
                self._operation = _Operation(device, owner, time.monotonic() + duration, duration)
            return {"owner": owner, "device_id": f"0x{device:016x}", "duration_seconds": duration}
        if request.method in ("renew_operation", "release_operation"):
            if self._operation is None or self._operation.owner != values["owner"]:
                raise GatewayControlError("operation_expired", "Operation expired or was released")
            if request.method == "release_operation":
                self._release()
            else:
                self._operation.renew()
            return {}
        if request.method in self.handlers:
            return self.handlers[request.method](values)
        raise GatewayControlError("unsupported_capability", f"Unsupported control method {request.method}")

    def accept(self, request: GatewayRequest) -> bool:
        """Process control requests and authorize data/connection requests."""
        with self._lock:
            self._expire()
            if isinstance(request, GatewayRequestControl):
                self._control(request)
                return False
            if isinstance(request, GatewayRequestCommsCheck):
                if request.request_id is None:
                    return True
                self._broadcast(ClientNotificationCommsCheck(self.capabilities(), request.request_id))
                return False
            if isinstance(request, GatewayRequestEpacketSend):
                device = request.epacket.infuse_id
            elif isinstance(request, (GatewayRequestConnectionRequest, GatewayRequestConnectionRelease)):
                device = request.infuse_id
            else:
                return True
            operation = self._operation
            owner = request.operation_id
            if operation is not None:
                allowed = owner == operation.owner and device == operation.device_id
            else:
                # Legacy requests wait for an ended operation's cleanup, but their releases still free a reference.
                allowed = owner is None and (not self._cleanup or isinstance(request, GatewayRequestConnectionRelease))
            if not allowed:
                if isinstance(request, GatewayRequestConnectionRequest):
                    expired = operation is None and owner is not None
                    notification = ClientNotificationConnectionFailed(
                        device, "operation_expired" if expired else "device_busy", request.request_id
                    )
                    notification.operation_id = owner
                    self._broadcast(notification)
                return False
            if operation is None:
                self._accept_legacy(request, device)
                return True
            operation.renew()
            if isinstance(request, GatewayRequestConnectionRequest):
                operation.requests[request.request_id] += 1
                operation.last_request_id = request.request_id
                operation.linked = True
                self._track_link(device, self._setup_time(request))
            elif isinstance(request, GatewayRequestConnectionRelease):
                if not operation.requests[request.request_id]:
                    return False
                operation.requests[request.request_id] -= 1
                operation.requests += Counter()
                if operation.connections == 0:
                    self._mark_closing(device)
            return True

    @staticmethod
    def _remove_request(requests: Counter[int | None], request_id: int | None) -> bool:
        if not requests[request_id]:
            return False
        requests[request_id] -= 1
        if not requests[request_id]:
            del requests[request_id]
        return True

    def _forget_legacy_request(self, device: int, request_id: int | None, released: bool) -> None:
        """Forget a released or failed legacy request, waiting for the link's teardown once no request remains."""
        answered = self._legacy.get(device, Counter())
        awaiting, _setup = self._awaiting.get(device, (Counter(), 0.0))
        # A client releases its answered request or one it stopped waiting for, while a failure answers a request.
        candidates = (answered, awaiting) if released else (awaiting,)
        if not any(self._remove_request(requests, request_id) for requests in candidates):
            return
        if not answered:
            self._legacy.pop(device, None)
        if not awaiting:
            self._awaiting.pop(device, None)
        if device not in self._legacy and device not in self._awaiting:
            self._mark_closing(device)

    def _answer_legacy(self, device: int, request_id: int | None) -> None:
        """Move legacy requests answered by a new connection to the device's link."""
        awaiting, _setup = self._awaiting.get(device, (Counter(), 0.0))
        # A result without a request ID answers every request for the device.
        answered = +awaiting if request_id is None else Counter[int | None]({request_id: 1}) & awaiting
        if not answered:
            return
        awaiting -= answered
        if not awaiting:
            del self._awaiting[device]
        self._legacy.setdefault(device, Counter()).update(answered)

    def _accept_legacy(self, request: GatewayRequest, device: int) -> None:
        if self.is_local(device):
            self._legacy_seen[device] = time.monotonic()
        if isinstance(request, GatewayRequestConnectionRequest):
            setup = self._setup_time(request)
            requests, longest = self._awaiting.get(device, (Counter(), 0.0))
            requests[request.request_id] += 1
            self._awaiting[device] = (requests, max(longest, setup))
            self._track_link(device, setup)
        elif isinstance(request, GatewayRequestConnectionRelease):
            self._forget_legacy_request(device, request.request_id, released=True)

    @staticmethod
    def _owned_traffic(device: int, packet: PacketReceived) -> bool:
        """Whether a packet arrived over the device's connection or answers an RPC, unlike advertisements."""
        if not packet.route or packet.route[0].infuse_id != device:
            return False
        return packet.route[0].interface == Interface.BT_CENTRAL or packet.ptype in (
            InfuseType.RPC_RSP,
            InfuseType.RPC_DATA,
            InfuseType.RPC_DATA_ACK,
        )

    def observe(self, notification: ClientNotification) -> None:
        """Track backend links, renew operations on owned traffic and correlate connection results."""
        with self._lock:
            operation = self._operation
            if isinstance(notification, ClientNotificationEpacketReceived):
                if operation is not None and self._owned_traffic(operation.device_id, notification.epacket):
                    operation.renew()
                return
            if not isinstance(notification, ClientNotificationConnection):
                return
            device = notification.infuse_id
            ended = isinstance(notification, (ClientNotificationConnectionFailed, ClientNotificationConnectionDropped))
            if isinstance(notification, ClientNotificationConnectionFailed) and notification.request_id is not None:
                # One request can fail while other clients still use or await the same link.
                self._forget_legacy_request(device, notification.request_id, released=False)
                other_owned = (
                    operation is not None
                    and operation.device_id == device
                    and operation.connections > operation.requests[notification.request_id]
                )
                if device not in self._legacy and device not in self._awaiting and not other_owned:
                    if device in self._established:
                        # The gateway closes the unused link and reports its teardown.
                        self._mark_closing(device)
                    else:
                        # No link was established, so no teardown follows, even if the request was released.
                        self._link_ended(device, dropped=False)
            elif ended:
                self._link_ended(device, isinstance(notification, ClientNotificationConnectionDropped))
            elif isinstance(notification, ClientNotificationConnectionCreated):
                self._answer_legacy(device, notification.request_id)
                if not self.is_local(device):
                    self._links.setdefault(device, time.monotonic())
                    self._established.add(device)
            if operation is None or operation.device_id != device:
                return
            operation.renew()
            if isinstance(notification, ClientNotificationConnectionDropped):
                # The owner still releases a dropped connection, and native_bt reconnects requests queued behind it.
                notification.operation_id = operation.owner
            elif (
                isinstance(notification, ClientNotificationConnectionResult)
                and operation.connections
                and (notification.request_id is None or operation.requests[notification.request_id])
            ):
                # Results arriving without an outstanding request are late, and must not satisfy a later one.
                notification.operation_id = operation.owner
                if ended:
                    if notification.request_id is None:
                        # A backend-wide failure answers every pending request for the device.
                        operation.requests.clear()
                    else:
                        operation.requests[notification.request_id] -= 1
                        operation.requests += Counter()
