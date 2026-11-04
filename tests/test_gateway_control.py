"""Ownership tests use the same coordinator for serial and native gateways."""

from unittest.mock import Mock

import pytest

from infuse_iot.common import InfuseID, InfuseType
from infuse_iot.epacket import interface
from infuse_iot.epacket.packet import Auth, HopReceived, PacketReceived
from infuse_iot.gateway_control import LOCAL_IDLE_S, TEARDOWN_TIMEOUT_S, GatewayControl
from infuse_iot.socket_comms import (
    ClientNotification,
    ClientNotificationCommsCheck,
    ClientNotificationConnectionCreated,
    ClientNotificationConnectionDropped,
    ClientNotificationConnectionFailed,
    ClientNotificationControl,
    ClientNotificationEpacketReceived,
    GatewayControlError,
    GatewayRequest,
    GatewayRequestCommsCheck,
    GatewayRequestConnectionRelease,
    GatewayRequestConnectionRequest,
    GatewayRequestControl,
)


def connection(owner=None, device=123, request_id=None):
    request = GatewayRequestConnectionRequest(
        device, GatewayRequestConnectionRequest.DataType.COMMAND, 1000, request_id
    )
    request.operation_id = owner
    return request


def release(owner=None, device=123, request_id=None):
    request = GatewayRequestConnectionRelease(device, request_id)
    request.operation_id = owner
    return request


def observed(coordinator, notification):
    coordinator.observe(notification)
    return notification.operation_id


def control(coordinator, method, **parameters):
    assert not coordinator.accept(GatewayRequestControl(method, parameters, "test-request"))
    return coordinator._broadcast.call_args.args[0]


def acquire(coordinator, owner="first", device_id="0x000000000000007b"):
    return control(coordinator, "acquire_operation", owner=owner, device_id=device_id, duration_seconds=5)


@pytest.fixture
def coordinator():
    return GatewayControl(Mock())


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr("infuse_iot.gateway_control.time.monotonic", lambda: now[0])
    return now


def test_capability_query_preserves_legacy_comms_check(coordinator):
    assert coordinator.accept(GatewayRequestCommsCheck())
    assert not coordinator.accept(GatewayRequestCommsCheck("probe"))
    response = coordinator._broadcast.call_args.args[0]
    assert isinstance(response, ClientNotificationCommsCheck)
    assert response.request_id == "probe"
    assert response.capabilities is not None
    assert "operation_ownership" in response.capabilities["features"]


def test_ownership_rejects_other_clients_and_legacy_releases(coordinator):
    assert acquire(coordinator).ok
    assert coordinator.accept(connection("first"))
    assert not acquire(coordinator, "second").ok
    assert not coordinator.accept(connection())
    assert not coordinator.accept(GatewayRequestConnectionRelease(123))
    assert coordinator._operation.connections == 1
    release = GatewayRequestConnectionRelease(123)
    release.operation_id = "first"
    assert coordinator.accept(release)
    assert coordinator._operation.connections == 0


@pytest.mark.parametrize("ending", ["released", "expired"])
def test_operation_cleanup_preserves_connection_request_ids(coordinator, clock, ending):
    assert acquire(coordinator).ok
    for request_id in (7, 8):
        assert coordinator.accept(connection("first", request_id=request_id))
    if ending == "expired":
        clock[0] = 6
    else:
        assert control(coordinator, "release_operation", owner="first").ok
    assert [request.request_id for request in coordinator.cleanup()] == [7, 8]


def test_identified_request_failure_keeps_other_owned_connection(coordinator):
    assert acquire(coordinator).ok
    for request_id in (7, 8):
        assert coordinator.accept(connection("first", request_id=request_id))
    assert observed(coordinator, ClientNotificationConnectionCreated(123, 205, 7)) == "first"
    assert observed(coordinator, ClientNotificationConnectionFailed(123, "Failed", 8)) == "first"
    assert control(coordinator, "release_operation", owner="first").ok
    assert [request.request_id for request in coordinator.cleanup()] == [7]


def test_unknown_legacy_release_does_not_cancel_queued_request(coordinator):
    assert coordinator.accept(connection(request_id=7))
    assert coordinator.accept(release(request_id=7))
    assert coordinator.accept(connection(request_id=8))
    assert coordinator.accept(release(request_id=7))
    coordinator.observe(ClientNotificationConnectionDropped(123))
    assert acquire(coordinator).code == "device_busy"
    assert coordinator.accept(release(request_id=8))
    coordinator.observe(ClientNotificationConnectionDropped(123))
    assert acquire(coordinator).ok


def test_identified_legacy_failure_keeps_existing_user(coordinator):
    for request_id in (7, 8):
        assert coordinator.accept(connection(request_id=request_id))
    coordinator.observe(ClientNotificationConnectionCreated(123, 205, 7))
    coordinator.observe(ClientNotificationConnectionFailed(123, "Failed", 8))
    assert acquire(coordinator).code == "device_busy"
    assert coordinator.accept(release(request_id=7))
    coordinator.observe(ClientNotificationConnectionDropped(123))
    assert acquire(coordinator).ok


def test_acquire_is_idempotent_and_cannot_change_device(coordinator):
    assert acquire(coordinator).ok
    assert acquire(coordinator).ok
    assert not acquire(coordinator, device_id="0x124").ok


def test_legacy_connection_prevents_operation_acquisition(coordinator):
    assert coordinator.accept(connection())
    assert acquire(coordinator).code == "device_busy"
    assert coordinator.accept(GatewayRequestConnectionRelease(123))
    # The released link's late results would otherwise be attributed to the new owner.
    assert acquire(coordinator).result == {"message": "A released connection is closing"}
    coordinator.observe(ClientNotificationConnectionDropped(123))
    assert acquire(coordinator).ok


def test_expiry_releases_pending_connection_and_rejects_stale_owner(coordinator, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("infuse_iot.gateway_control.time.monotonic", lambda: clock[0])
    assert acquire(coordinator).ok
    assert coordinator.accept(connection("first"))
    clock[0] = 6
    cleanup = coordinator.cleanup()
    assert len(cleanup) == 1 and isinstance(cleanup[0], GatewayRequestConnectionRelease)
    assert not coordinator.accept(connection("first"))
    # No new owner may inherit an old connection's teardown notifications.
    assert acquire(coordinator, "second").code == "device_busy"
    coordinator.observe(ClientNotificationConnectionDropped(123))
    assert acquire(coordinator, "second").ok


@pytest.mark.parametrize(
    "owner,reason", [(None, "device_busy"), ("first", "operation_expired"), ("other", "operation_expired")]
)
def test_request_in_expiring_call_gets_its_reason(coordinator, clock, owner, reason):
    assert acquire(coordinator).ok
    assert coordinator.accept(connection("first", request_id=7))
    clock[0] = 6
    # The operation expires within this call, before its cleanup releases are sent.
    assert not coordinator.accept(connection(owner, request_id=8))
    failure = coordinator._broadcast.call_args.args[0]
    assert isinstance(failure, ClientNotificationConnectionFailed)
    assert (failure.reason, failure.request_id, failure.operation_id) == (reason, 8, owner)
    assert [request.request_id for request in coordinator.cleanup()] == [7]


def test_legacy_release_passes_while_expired_operation_cleans_up(coordinator, clock):
    assert acquire(coordinator).ok
    assert coordinator.accept(connection("first", request_id=7))
    clock[0] = 6
    # A dropped release would leak the legacy client's reference to the backend link.
    assert coordinator.accept(release(request_id=3))
    assert not coordinator.accept(release("first", request_id=7))
    assert [request.request_id for request in coordinator.cleanup()] == [7]


def test_active_requests_renew_the_operation(coordinator, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("infuse_iot.gateway_control.time.monotonic", lambda: clock[0])
    acquire(coordinator)
    clock[0] = 4
    assert coordinator.accept(connection("first"))
    clock[0] = 6
    assert not coordinator.cleanup()
    assert coordinator._operation is not None


def test_wrong_owner_cannot_release_and_correct_release_cleans_connection(coordinator):
    acquire(coordinator)
    coordinator.accept(connection("first"))
    assert control(coordinator, "release_operation", owner="other").code == "operation_expired"
    assert control(coordinator, "release_operation", owner="first").ok
    assert len(coordinator.cleanup()) == 1


def test_connection_notifications_preserve_operation_correlation(coordinator):
    acquire(coordinator)
    coordinator.accept(connection("first"))
    notification = ClientNotificationConnectionCreated(123, 205)
    coordinator.observe(notification)
    decoded = ClientNotification.from_json(notification.to_json())
    assert isinstance(decoded, ClientNotificationConnectionCreated)
    assert decoded.operation_id == "first"
    assert decoded.infuse_id == 123


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"owner": "x", "device_id": "-1"},
        {"owner": "x", "device_id": 5},
        {"owner": "x", "device_id": "0x123", "duration_seconds": float("nan")},
        {"owner": "x", "device_id": "0x123", "duration_seconds": 10**400},
    ],
)
def test_bad_parameters_are_reported_without_acquiring(coordinator, parameters):
    assert not coordinator.accept(GatewayRequestControl("acquire_operation", parameters))
    assert coordinator._broadcast.call_args.args[0].code == "invalid_request"
    assert coordinator._operation is None


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


def test_two_real_clients_cannot_share_an_owned_operation():
    import threading

    from infuse_iot.socket_comms import LocalClient, LocalServer, default_multicast_address

    address = default_multicast_address(18851)
    server = LocalServer(address)
    stop = threading.Event()

    def serve():
        while not stop.is_set():
            request = server.receive()
            if isinstance(request, GatewayRequestConnectionRequest):
                server.broadcast(ClientNotificationConnectionCreated(request.infuse_id, 205))
            elif isinstance(request, GatewayRequestConnectionRelease):
                server.broadcast(ClientNotificationConnectionDropped(request.infuse_id))

    thread = threading.Thread(target=serve)
    clients = [LocalClient(address), LocalClient(address)]
    thread.start()
    try:
        with (
            clients[0].operation(123),
            clients[0].connection(123, GatewayRequestConnectionRequest.DataType.COMMAND) as mtu,
        ):
            assert mtu == 205
            with pytest.raises(RuntimeError, match="device_busy"), clients[1].operation(123):
                pytest.fail("Second client acquired an owned operation")
        with (
            clients[1].operation(123),
            clients[1].connection(123, GatewayRequestConnectionRequest.DataType.COMMAND) as mtu,
        ):
            assert mtu == 205
    finally:
        for client in clients:
            client.close()
        stop.set()
        thread.join(timeout=2)
        server.close()
    assert not thread.is_alive()


def test_control_replies_use_a_legacy_safe_notification_type():
    reply = ClientNotificationControl("request", True, result={"answer": 42})
    wire = reply.to_json()
    assert wire["type"] == ClientNotification.Type.COMMS_CHECK
    assert wire["control"] is True
    assert isinstance(ClientNotification.from_json(wire), ClientNotificationControl)


def test_reconnect_queued_behind_closing_link_is_released(coordinator):
    assert acquire(coordinator).ok
    assert coordinator.accept(connection("first"))
    assert observed(coordinator, ClientNotificationConnectionCreated(123, 205)) == "first"
    assert coordinator.accept(release("first"))
    # native_bt reconnects a request received while the previous link closes.
    assert coordinator.accept(connection("first"))
    assert observed(coordinator, ClientNotificationConnectionDropped(123)) == "first"
    assert observed(coordinator, ClientNotificationConnectionCreated(123, 205)) == "first"
    # The release must reach the new link rather than being discarded.
    assert coordinator.accept(release("first"))
    assert control(coordinator, "release_operation", owner="first").ok
    assert not coordinator.cleanup()
    assert acquire(coordinator, "second", "0x0000000000000124").code == "device_busy"
    coordinator.observe(ClientNotificationConnectionDropped(123))
    assert acquire(coordinator, "second", "0x0000000000000124").ok


def test_late_result_does_not_satisfy_a_new_request(coordinator):
    assert acquire(coordinator).ok
    assert coordinator.accept(connection("first"))
    # The owner stopped waiting for its request.
    assert coordinator.accept(release("first"))
    assert observed(coordinator, ClientNotificationConnectionCreated(123, 205)) is None
    assert coordinator.accept(connection("first"))
    assert observed(coordinator, ClientNotificationConnectionCreated(123, 205)) == "first"


def test_failed_connection_is_not_released_again(coordinator):
    assert acquire(coordinator).ok
    assert coordinator.accept(connection("first"))
    assert observed(coordinator, ClientNotificationConnectionFailed(123, "Connection timed out")) == "first"
    assert control(coordinator, "release_operation", owner="first").ok
    assert not coordinator.cleanup()
    assert acquire(coordinator, "second").ok


def test_operation_closes_unreferenced_link_it_created(coordinator):
    assert acquire(coordinator).ok
    assert coordinator.accept(connection("first"))
    # A failure for an earlier pending request completes the owner's request, then the link connects.
    coordinator.observe(ClientNotificationConnectionFailed(123, "Bluetooth connection failed"))
    coordinator.observe(ClientNotificationConnectionCreated(123, 205))
    assert control(coordinator, "release_operation", owner="first").ok
    assert [type(request) for request in coordinator.cleanup()] == [GatewayRequestConnectionRelease]


def test_teardown_wait_is_bounded(coordinator, clock):
    assert coordinator.accept(connection())
    assert coordinator.accept(GatewayRequestConnectionRelease(123))
    # A lost disconnect notification must not block every later operation.
    clock[0] = 1 + TEARDOWN_TIMEOUT_S - 0.1
    assert acquire(coordinator).code == "device_busy"
    clock[0] = 1 + TEARDOWN_TIMEOUT_S
    assert acquire(coordinator).ok


def test_legacy_request_queued_behind_closing_link_survives_its_teardown(coordinator):
    assert coordinator.accept(connection())
    coordinator.observe(ClientNotificationConnectionCreated(123, 205))
    assert coordinator.accept(release())
    # The next legacy client connects while the first link closes, so the gateway gives it a new link.
    assert coordinator.accept(connection())
    coordinator.observe(ClientNotificationConnectionDropped(123))
    assert acquire(coordinator, device_id="0x000000000000007c").code == "device_busy"
    coordinator.observe(ClientNotificationConnectionCreated(123, 205))
    assert acquire(coordinator).code == "device_busy"
    assert coordinator.accept(release())
    assert acquire(coordinator).result == {"message": "A released connection is closing"}
    coordinator.observe(ClientNotificationConnectionDropped(123))
    assert acquire(coordinator).ok


@pytest.mark.parametrize("ending", ["failed", "released", "expired"])
def test_queued_legacy_request_ends(coordinator, clock, ending):
    assert coordinator.accept(connection())
    assert coordinator.accept(release())
    assert coordinator.accept(connection())
    if ending == "failed":
        # Waiting clients take the failure as their own result, and do not release.
        coordinator.observe(ClientNotificationConnectionFailed(123, "Connection timed out"))
    elif ending == "released":
        assert coordinator.accept(release())
        coordinator.observe(ClientNotificationConnectionDropped(123))
    else:
        # A lost teardown notification leaves the queued request on a new link.
        clock[0] = 1 + TEARDOWN_TIMEOUT_S
        assert acquire(coordinator).code == "device_busy"
        assert coordinator.accept(release())
        clock[0] += 1 + TEARDOWN_TIMEOUT_S
    assert acquire(coordinator).ok


def test_unanswered_legacy_request_survives_drop(coordinator):
    assert coordinator.accept(connection(request_id=7))
    coordinator.observe(ClientNotificationConnectionCreated(123, 205, 7))
    # A second client requests the device as its link drops, so the gateway answers it over a new link.
    assert coordinator.accept(connection(request_id=8))
    coordinator.observe(ClientNotificationConnectionDropped(123))
    assert coordinator.accept(release(request_id=7))
    assert acquire(coordinator, device_id="0x000000000000007c").code == "device_busy"
    coordinator.observe(ClientNotificationConnectionCreated(123, 205, 8))
    assert acquire(coordinator, device_id="0x000000000000007c").code == "device_busy"
    assert coordinator.accept(release(request_id=8))
    assert acquire(coordinator).result == {"message": "A released connection is closing"}
    coordinator.observe(ClientNotificationConnectionDropped(123))
    assert acquire(coordinator).ok


@pytest.mark.parametrize("owner", [None, "first"])
def test_failure_of_released_request_ends_closing(coordinator, owner):
    if owner is not None:
        assert acquire(coordinator).ok
    assert coordinator.accept(connection(owner, request_id=7))
    # The client stops waiting, then the setup fails, so no link is left to report a teardown.
    assert coordinator.accept(release(owner, request_id=7))
    coordinator.observe(ClientNotificationConnectionFailed(123, "Connection timed out", 7))
    if owner is not None:
        assert control(coordinator, "release_operation", owner=owner).ok
        assert not coordinator.cleanup()
    assert acquire(coordinator, "second").ok


def test_failure_after_established_link_waits_for_its_teardown(coordinator):
    assert coordinator.accept(connection(request_id=7))
    coordinator.observe(ClientNotificationConnectionCreated(123, 205, 7))
    assert coordinator.accept(release(request_id=7))
    assert coordinator.accept(connection(request_id=8))
    coordinator.observe(ClientNotificationConnectionFailed(123, "Connection timed out", 8))
    # The released link still reports its teardown.
    assert acquire(coordinator).result == {"message": "A released connection is closing"}
    coordinator.observe(ClientNotificationConnectionDropped(123))
    assert acquire(coordinator).ok


def test_local_device_needs_no_teardown(coordinator):
    coordinator.is_local = lambda device: device == 123
    assert acquire(coordinator).ok
    assert coordinator.accept(connection("first"))
    assert observed(coordinator, ClientNotificationConnectionCreated(123, 512)) == "first"
    assert coordinator.accept(release("first"))
    assert control(coordinator, "release_operation", owner="first").ok
    assert not coordinator.cleanup()
    assert acquire(coordinator, "second", "0x0000000000000124").ok


def test_idle_local_legacy_connection_expires(coordinator, clock):
    coordinator.is_local = lambda device: device == InfuseID.GATEWAY
    # A killed client never releases the gateway's own device, which is never reported dropped.
    assert coordinator.accept(connection(device=InfuseID.GATEWAY))
    clock[0] = LOCAL_IDLE_S - 1
    assert acquire(coordinator).code == "device_busy"
    clock[0] = LOCAL_IDLE_S
    assert acquire(coordinator).ok


def test_gateway_alias_is_rejected(coordinator):
    reply = control(coordinator, "acquire_operation", owner="first", device_id="-0x1")
    assert reply.code == "invalid_request"
    assert "InfuseID.GATEWAY" in reply.result["message"]


def received(device, ptype, interface_id):
    address = interface.Address(interface.Address.BluetoothLeAddr(0, 0))
    hop = HopReceived(device, interface_id, address, Auth.DEVICE, 0, 0, 0, -60)
    return ClientNotificationEpacketReceived(PacketReceived([hop], ptype, b""))


def test_owned_device_traffic_renews_the_operation(coordinator, clock):
    assert acquire(coordinator).ok
    # A long download only receives data from the device.
    clock[0] = 4
    coordinator.observe(received(123, InfuseType.RPC_DATA, interface.ID.BT_CENTRAL))
    clock[0] = 8
    coordinator.observe(received(123, InfuseType.RPC_DATA, interface.ID.BT_CENTRAL))
    clock[0] = 12
    coordinator.cleanup()
    assert coordinator._operation is not None
    # Advertisements and other devices do not renew the operation.
    coordinator.observe(received(123, InfuseType.TDF, interface.ID.BT_ADV))
    coordinator.observe(received(124, InfuseType.RPC_RSP, interface.ID.BT_CENTRAL))
    clock[0] = 13
    coordinator.cleanup()
    assert coordinator._operation is None


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
