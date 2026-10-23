"""Control tests use the same coordinator for serial and native gateways."""

from unittest.mock import Mock

import pytest

from infuse_iot.gateway_control import GatewayControl
from infuse_iot.socket_comms import (
    ClientNotification,
    ClientNotificationCommsCheck,
    ClientNotificationControl,
    GatewayControlError,
    GatewayRequest,
    GatewayRequestCommsCheck,
    GatewayRequestControl,
)


def control(coordinator, method, **parameters):
    assert not coordinator.accept(GatewayRequestControl(method, parameters, "test-request"))
    return coordinator._broadcast.call_args.args[0]


@pytest.fixture
def coordinator():
    return GatewayControl(Mock())


def test_capability_query_preserves_legacy_comms_check(coordinator):
    assert coordinator.accept(GatewayRequestCommsCheck())
    assert not coordinator.accept(GatewayRequestCommsCheck("probe"))
    response = coordinator._broadcast.call_args.args[0]
    assert isinstance(response, ClientNotificationCommsCheck)
    assert response.request_id == "probe"
    assert response.capabilities is not None
    assert response.capabilities["protocol_version"] == 2


def test_new_messages_round_trip():
    request = GatewayRequestControl("release_operation", {"owner": "test"}, "correlation")
    restored = GatewayRequest.from_json(request.to_json())
    assert isinstance(restored, GatewayRequestControl)
    assert restored.request_id == "correlation"
    assert restored.parameters == {"owner": "test"}
    notification = ClientNotificationControl("correlation", False, code="device_busy")
    decoded = ClientNotification.from_json(notification.to_json())
    assert isinstance(decoded, ClientNotificationControl)
    assert decoded.code == "device_busy" and not decoded.ok


def test_control_replies_use_a_legacy_safe_notification_type():
    reply = ClientNotificationControl("request", True, result={"answer": 42})
    wire = reply.to_json()
    assert wire["type"] == ClientNotification.Type.COMMS_CHECK
    assert wire["control"] is True
    assert isinstance(ClientNotification.from_json(wire), ClientNotificationControl)


def test_control_handler_errors_are_reported(coordinator):
    def lookup(values):
        if values["cursor"] == "expired":
            raise GatewayControlError("cursor_expired", "Restart the query")
        if values["cursor"] == "broken":
            raise RuntimeError("Unexpected state")
        return {"next": values["cursor"].upper()}

    coordinator.handlers["lookup"] = lookup
    reply = control(coordinator, "lookup", cursor="expired")
    assert (reply.ok, reply.code, reply.result) == (False, "cursor_expired", {"message": "Restart the query"})
    assert control(coordinator, "lookup", cursor=5).code == "invalid_request"
    assert control(coordinator, "lookup", cursor="broken").code == "internal_error"
    assert control(coordinator, "lookup", cursor="a").result == {"next": "A"}
