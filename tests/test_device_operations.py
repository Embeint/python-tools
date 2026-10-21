import struct
import threading
import time
from unittest.mock import Mock

import pytest

import infuse_iot.definitions.rpc as defs
from infuse_iot.common import InfuseID
from infuse_iot.services.device_operations import DeviceError, DeviceOperations, device_id, kv_values
from infuse_iot.services.jobs import JobCancelled
from infuse_iot.socket_comms import (
    GatewayControlError,
    GatewayRequestConnectionRequest,
    GatewayRequestEpacketSend,
    LocalClient,
    default_multicast_address,
)

DEVICE = 0xCE7E42571A000099
DEVICE_ID = f"0x{DEVICE:016x}"


def kv(key_id: int, data: bytes = b"", error: int | None = None) -> bytes:
    return struct.pack("<Hh", key_id, len(data) if error is None else error) + data


def application_info() -> bytes:
    version = defs.rpc_struct_mcuboot_img_sem_ver(1, 3, 1, 0x7BEE09D5)
    return bytes(defs.application_info.response(0xCE710003, version, 0xCE7E50, 100, 3, 0xABC, 1, 2))


def failure(function, *args, **kwargs) -> DeviceError:
    with pytest.raises(DeviceError) as error:
        function(*args, **kwargs)
    return error.value


@pytest.mark.parametrize(
    "command,parameters",
    [
        ("reboot", {}),
        ("application_info", {"extra": 1}),
        ("kv_read", {"keys": ["SECURE_STORAGE_RESERVED"]}),
        ("kv_read", {"keys": []}),
        ("kv_read", {"keys": "REBOOTS"}),
        ("data_logger_state", {"logger": "unknown"}),
    ],
)
def test_invalid_reads_do_not_open_a_connection(monkeypatch, command, parameters):
    factory = Mock()
    monkeypatch.setattr("infuse_iot.services.device_operations.LocalClient", factory)
    with pytest.raises(ValueError):
        DeviceOperations(("224.1.1.1", 19851)).read("0x123", command, parameters)
    factory.assert_not_called()


def test_supported_kv_names_resolve_before_connecting(monkeypatch):
    class Opened(Exception):
        pass

    monkeypatch.setattr("infuse_iot.services.device_operations.LocalClient", Mock(side_effect=Opened))
    with pytest.raises(Opened):
        DeviceOperations(("224.1.1.1", 19851)).read("0x123", "kv_read", {"keys": ["REBOOTS", "DEVICE_NAME"]})


def test_full_device_id_is_preserved():
    assert device_id("0xce7e42571a000099") == 0xCE7E42571A000099
    assert device_id("CE7E42571A000099") == 0xCE7E42571A000099


@pytest.mark.parametrize("value", ["-1", " 12_34 ", "12_34", "١٢", "0x", "", "0X12", "0x" + "1" * 17, "12\n"])
def test_device_ids_are_strict(value):
    with pytest.raises(ValueError):
        device_id(value)


def test_gateway_alias_is_not_a_device_id():
    with pytest.raises(ValueError, match="own device ID"):
        device_id(InfuseID.GATEWAY)  # type: ignore[arg-type]


def test_kv_values_report_unset_keys_and_decode_known_values():
    name = b"sensor-1\x00"
    payload = (
        kv(0, struct.pack("<I", 7))
        + kv(4, error=-2)
        + kv(1, bytes([1, 0x61, 0x61, 0x00, 0xF1, 0xFC, 0x60]))
        + kv(4, bytes([len(name)]) + name)
        + kv(0, error=-5)
        + kv(0, b"\x01\x02")
    )
    values = kv_values(defs.kv_read.response.vla_from_buffer_copy(payload))
    assert values[0] == {"id": 0, "key": "REBOOTS", "status": "ok", "raw": "07000000", "value": {"count": 7}}
    assert values[1]["status"] == "not_set" and values[1]["error_code"] == -2 and "value" not in values[1]
    assert values[2]["value"] == {"type": 1, "address": "60:FC:F1:00:61:61"}
    assert values[3]["value"] == {"name": "sensor-1"}
    assert values[4]["status"] == "error" and values[4]["error_code"] == -5
    assert values[5]["status"] == "invalid" and values[5]["raw"] == "0102"


def test_kv_read_keeps_values_read_alongside_unset_keys(device_gateway):
    gateway = device_gateway(28881)
    gateway.respond = lambda device, command, request: (0, kv(0, struct.pack("<I", 7)) + kv(4, error=-2))
    result = DeviceOperations(gateway.address).read(DEVICE_ID, "kv_read", {"keys": ["REBOOTS", "DEVICE_NAME"]})
    assert result["device_id"] == DEVICE_ID
    assert [(v["key"], v["status"]) for v in result["response"]["values"]] == [
        ("REBOOTS", "ok"),
        ("DEVICE_NAME", "not_set"),
    ]


def test_read_decodes_typed_fields(device_gateway):
    gateway = device_gateway(28883)
    gateway.respond = lambda device, command, request: (0, application_info())
    response = DeviceOperations(gateway.address).read(DEVICE_ID, "application_info")["response"]
    assert response["version"] == "1.3.1+7bee09d5"
    thread = b"main\x00\x00\x00\x00"
    reboot = defs.last_reboot.response(1, 0, 2**60, 0, 5, 0, 0, thread)
    gateway.respond = lambda device, command, request: (0, bytes(reboot))
    response = DeviceOperations(gateway.address).read(DEVICE_ID, "last_reboot")["response"]
    # Text fields are strings, and integers beyond JSON's exact range are decimal strings
    assert response["thread"] == "main"
    assert response["epoch_time"] == str(2**60)


def test_read_without_gateway_is_unavailable():
    start = time.monotonic()
    error = failure(DeviceOperations(default_multicast_address(28885)).read, DEVICE_ID, "application_info")
    assert (error.code, error.retryable) == ("gateway_unavailable", True)
    assert time.monotonic() - start < 3


@pytest.mark.parametrize(
    "command,parameters,payload",
    [
        ("kv_read", {"keys": ["REBOOTS"]}, b"\x00\x00\x04"),
        ("application_info", {}, b"\x01"),
        # An unaligned variable length array fails to decode with `TypeError`
        ("last_reboot", {}, bytes(defs.last_reboot.response()) + b"\x00\x00"),
    ],
)
def test_malformed_response_is_invalid(device_gateway, command, parameters, payload):
    gateway = device_gateway(28887)
    gateway.respond = lambda device, command, request: (0, payload)
    error = failure(DeviceOperations(gateway.address).read, DEVICE_ID, command, parameters)
    assert (error.code, error.retryable) == ("device_response_invalid", False)


def test_rejected_and_unanswered_rpcs(device_gateway):
    gateway = device_gateway(28889)
    operations = DeviceOperations(gateway.address)
    gateway.respond = lambda device, command, request: (-1002, b"")
    assert failure(operations.read, DEVICE_ID, "application_info").code == "rpc_rejected"
    gateway.respond = lambda device, command, request: None
    error = failure(operations.read, DEVICE_ID, "application_info", timeout_seconds=0.3)
    assert (error.code, error.retryable) == ("rpc_timeout", True)


def test_connection_failures_are_distinct_from_gateway_failures(device_gateway, monkeypatch):
    gateway = device_gateway(28891)
    gateway.connect = False
    operations = DeviceOperations(gateway.address)
    operations.connect_timeout_seconds = 0.2
    monkeypatch.setattr(LocalClient, "CONNECTION_RESPONSE_MARGIN_S", 0.1)
    error = failure(operations.read, DEVICE_ID, "application_info")
    assert (error.code, error.retryable) == ("connection_timeout", True)


def test_busy_server_fails_within_the_wait(device_gateway):
    gateway = device_gateway(28893)
    operations = DeviceOperations(gateway.address)
    operations.busy_wait_seconds = 0.3
    with operations.exclusive():
        start = time.monotonic()
        error = failure(operations.read, DEVICE_ID, "application_info")
    assert (error.code, error.retryable) == ("device_busy", True)
    assert time.monotonic() - start < 1.5
    assert not gateway.requests
    # The lock is released after a failure
    gateway.respond = lambda device, command, request: (0, application_info())
    assert operations.read(DEVICE_ID, "application_info")["device_id"] == DEVICE_ID


def test_only_a_few_callers_wait_for_the_lock():
    operations = DeviceOperations(("224.1.1.1", 19851))
    operations.busy_wait_seconds = 1.0
    outcomes: list[float] = []

    def wait():
        start = time.monotonic()
        with pytest.raises(DeviceError, match="still running"), operations.exclusive():
            pass
        outcomes.append(time.monotonic() - start)

    with operations.exclusive():
        threads = [threading.Thread(target=wait) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    # Two callers waited for the lock, and the others failed without blocking a thread
    assert sorted(round(elapsed) for elapsed in outcomes) == [0, 0, 0, 0, 1, 1]


def test_device_owned_by_another_client_is_busy(device_gateway):
    gateway = device_gateway(28895)
    gateway.respond = lambda device, command, request: (0, application_info())
    operations = DeviceOperations(gateway.address)
    operations.busy_wait_seconds = 0.6
    other = LocalClient(gateway.address)
    try:
        with other.operation(DEVICE):
            error = failure(operations.read, DEVICE_ID, "application_info")
            assert (error.code, error.retryable) == ("device_busy", True)
    finally:
        other.close()
    assert operations.read(DEVICE_ID, "application_info")["command"] == "application_info"


def test_reads_wait_for_a_released_link_to_close(device_gateway):
    gateway = device_gateway(28897)
    gateway.respond = lambda device, command, request: (0, application_info())
    gateway.drop_delay = 1.0
    operations = DeviceOperations(gateway.address)
    operations.read(DEVICE_ID, "application_info")
    # The gateway rejects a new operation until the previous link reports its teardown
    assert operations.read(DEVICE_ID, "application_info")["command"] == "application_info"


def test_read_lease_is_short(device_gateway):
    gateway = device_gateway(28899)
    leases = []

    def respond(device, command, request):
        leases.append(gateway.server.control._operation.duration)
        return 0, application_info()

    gateway.respond = respond
    operations = DeviceOperations(gateway.address)
    operations.read(DEVICE_ID, "application_info", timeout_seconds=30)
    operations.read(DEVICE_ID, "application_info", timeout_seconds=1)
    # Long enough for the longest silent phase, and well below the default 60 s lease
    assert leases == [40.0, 30.0]


def test_reading_the_serial_gateway_does_not_block_later_reads(device_gateway):
    local = 0xABCD0001
    gateway = device_gateway(28901, local_device=local)
    gateway.respond = lambda device, command, request: (0, application_info())
    operations = DeviceOperations(gateway.address)
    operations.busy_wait_seconds = 0.5
    for target in (local, local, DEVICE):
        assert operations.read(f"0x{target:x}", "application_info")["device_id"] == f"0x{target:016x}"
    assert not gateway.server.control._closing


def test_cancelled_read_stops_and_releases_the_device(device_gateway):
    gateway = device_gateway(28903)
    operations = DeviceOperations(gateway.address)

    class CancelledAfterOwning(threading.Event):
        checks = 0

        def is_set(self):
            # Cancelled once the read owns the device, before it connects
            self.checks += 1
            return self.checks > 1 and gateway.server.control._operation is not None

    cancelled = CancelledAfterOwning()
    assert failure(operations.read, DEVICE_ID, "application_info", cancelled=cancelled).code == "cancelled"
    assert cancelled.checks == 2
    assert not any(isinstance(request, GatewayRequestConnectionRequest) for request in gateway.requests)
    assert gateway.server.control._operation is None


class Context:
    """Record job checkpoints, optionally cancelling while waiting."""

    def __init__(self, cancel_waits=False):
        self.events: list[str] = []
        self.cancel_waits = cancel_waits

    def check_cancelled(self):
        pass

    def progress(self, phase, **values):
        self.events.append(phase)

    def sending(self):
        self.events.append("sending")

    def wait(self, seconds):
        self.events.append("wait")
        if self.cancel_waits:
            raise JobCancelled
        time.sleep(seconds)


@pytest.fixture
def scripted_gateway(monkeypatch):
    """Drive the real `LocalClient` ownership and connection logic over a scripted gateway."""

    class Gateway(LocalClient):
        features = ["operation_ownership"]
        busy = 0
        log: list[str] = []
        rpc = Mock()

        def __init__(self, address):
            self._operation_id = None
            self._connection_id = None

        def capabilities(self, timeout=1.0):
            return {"protocol_version": 2, "features": list(self.features)}

        def control_request(self, method, parameters, timeout=2.0):
            self.log.append(method)
            if method == "acquire_operation" and Gateway.busy:
                Gateway.busy -= 1
                raise GatewayControlError("device_busy", "Another operation is active")
            return {}

        def connection_create(self, infuse_id, data_types, timeout_ms):
            self._connection_id = infuse_id
            self.log.append("connect")
            return 205

        def send(self, request):
            self.log.append(type(request).__name__)

        def close(self):
            self.log.append("close")

    Gateway.rpc.run_standard_cmd.return_value = (None, None)
    monkeypatch.setattr("infuse_iot.services.device_operations.LocalClient", Gateway)
    monkeypatch.setattr("infuse_iot.services.device_operations.RpcClient", lambda *args: Gateway.rpc)
    return Gateway


def reboot(context, action_wait_seconds=60.0, operations=None):
    """Reboot through the gateway, returning the `DeviceError` it raises."""
    operations = operations or DeviceOperations(("224.1.1.1", 19851))
    operations.action_wait_seconds = action_wait_seconds
    return failure(operations.mutate, "0x123", "reboot", {"delay_ms": 0}, context)


@pytest.mark.parametrize(
    "action,parameters",
    [
        ("reboot", {"delay_ms": 60001}),
        ("reboot", {"delay_ms": True}),
        ("reboot", {"delay_ms": 0, "force": True}),
        ("kv_write", {"key": "API_KEY", "value": "secret"}),
        ("kv_write", {"key": "DEVICE_NAME", "value": "a\x00b"}),
        ("kv_write", {"key": "DEVICE_NAME", "value": "x" * 129}),
        ("kv_write", {"key": "DEVICE_NAME"}),
        ("erase", {}),
    ],
)
def test_invalid_actions_do_not_open_a_connection(monkeypatch, action, parameters):
    factory = Mock()
    monkeypatch.setattr("infuse_iot.services.device_operations.LocalClient", factory)
    with pytest.raises(ValueError):
        DeviceOperations(("224.1.1.1", 19851)).mutate("0x123", action, parameters, Context())
    factory.assert_not_called()


def test_actions_never_downgrade_to_a_gateway_without_ownership(scripted_gateway):
    scripted_gateway.features = []
    context = Context()
    error = reboot(context)
    assert (error.code, error.retryable) == ("unsupported_capability", False)
    assert "connect" not in scripted_gateway.log and "sending" not in context.events
    scripted_gateway.rpc.run_standard_cmd.assert_not_called()


def test_missing_action_acknowledgement_is_not_reported_as_success(scripted_gateway):
    context = Context()
    assert reboot(context).code == "outcome_unknown"
    assert context.events[-1] == "sending"
    assert scripted_gateway.log[:2] == ["acquire_operation", "connect"]
    assert "release_operation" in scripted_gateway.log
    scripted_gateway.rpc.run_standard_cmd.assert_called_once()


def test_transport_failure_after_sending_is_unknown(scripted_gateway):
    scripted_gateway.rpc.run_standard_cmd.side_effect = TimeoutError("receive timed out")
    error = reboot(Context())
    assert (error.code, error.retryable) == ("outcome_unknown", False)


def test_busy_gateway_is_awaited_before_anything_is_sent(scripted_gateway):
    scripted_gateway.busy = 2
    context = Context()
    assert reboot(context).code == "outcome_unknown"
    assert context.events.count("wait") == 2
    assert scripted_gateway.log.count("acquire_operation") == 3
    scripted_gateway.rpc.run_standard_cmd.assert_called_once()


def test_busy_gateway_wait_is_bounded_and_retryable(scripted_gateway):
    scripted_gateway.busy = 1000
    context = Context()
    start = time.monotonic()
    error = reboot(context, action_wait_seconds=0.3)
    assert (error.code, error.retryable) == ("device_busy", True)
    assert time.monotonic() - start < 1.5
    assert "sending" not in context.events and "connect" not in scripted_gateway.log
    scripted_gateway.rpc.run_standard_cmd.assert_not_called()


def test_busy_gateway_wait_is_cancellable(scripted_gateway):
    scripted_gateway.busy = 1000
    with pytest.raises(JobCancelled):
        reboot(Context(cancel_waits=True))
    scripted_gateway.rpc.run_standard_cmd.assert_not_called()


def test_actions_wait_for_this_servers_reads_in_cancellable_steps(scripted_gateway):
    operations = DeviceOperations(("224.1.1.1", 19851))
    with operations.exclusive():
        start = time.monotonic()
        error = reboot(Context(), action_wait_seconds=1.0, operations=operations)
        assert (error.code, error.retryable) == ("device_busy", True)
        # The whole wait is bounded by the action's own deadline, not stacked lock waits.
        assert time.monotonic() - start < 2
        start = time.monotonic()
        with pytest.raises(JobCancelled):
            reboot(Context(cancel_waits=True), operations=operations)
        assert time.monotonic() - start < 1.5
    assert "acquire_operation" not in scripted_gateway.log
    # Once the lock is free the action proceeds
    assert reboot(Context(), operations=operations).code == "outcome_unknown"


def test_action_through_a_gateway(device_gateway):
    gateway = device_gateway(28905)
    leases = []

    def respond(device, command, request):
        leases.append(gateway.server.control._operation.duration)
        return 0, bytes(defs.reboot.response(250))

    gateway.respond = respond
    context = Context()
    result = DeviceOperations(gateway.address).mutate(DEVICE_ID, "reboot", {"delay_ms": 250}, context)
    assert (result["device_id"], result["status"], result["response"]) == (DEVICE_ID, "acknowledged", {"delay_ms": 250})
    assert context.events == ["connecting", "executing", "sending"]
    # The same short lease as reads, renewed by traffic
    assert leases == [30.0]
    assert sum(isinstance(request, GatewayRequestEpacketSend) for request in gateway.requests) == 1
    assert gateway.server.control._operation is None
