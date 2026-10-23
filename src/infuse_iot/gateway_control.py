"""Capability negotiation and control requests for gateway clients."""

import logging
import threading
from collections.abc import Callable
from typing import Any

from infuse_iot.socket_comms import (
    ClientNotification,
    ClientNotificationCommsCheck,
    ClientNotificationControl,
    GatewayControlError,
    GatewayRequest,
    GatewayRequestCommsCheck,
    GatewayRequestControl,
)


class GatewayControl:
    """Answer capability queries and control requests at the gateway, across all attached clients."""

    def __init__(self, broadcast: Callable[[ClientNotification], None], kind: str = "serial"):
        self.kind = kind
        self._broadcast = broadcast
        self._lock = threading.RLock()
        self.handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {}

    def capabilities(self) -> dict[str, Any]:
        return {
            "protocol_version": 2,
            "gateway_kind": self.kind,
            "features": sorted(self.handlers),
        }

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
        if request.method in self.handlers:
            return self.handlers[request.method](request.parameters)
        raise GatewayControlError("unsupported_capability", f"Unsupported control method {request.method}")

    def accept(self, request: GatewayRequest) -> bool:
        """Answer control requests and capability queries, passing other requests through."""
        with self._lock:
            if isinstance(request, GatewayRequestControl):
                self._control(request)
                return False
            if isinstance(request, GatewayRequestCommsCheck):
                if request.request_id is None:
                    return True
                self._broadcast(ClientNotificationCommsCheck(self.capabilities(), request.request_id))
                return False
            return True
