import errno
import struct
import threading
import time
from unittest.mock import Mock

import pytest

import infuse_iot.definitions.rpc as defs
from infuse_iot.common import InfuseID, InfuseType
from infuse_iot.epacket import interface
from infuse_iot.epacket.packet import Auth, HopReceived, PacketReceived
from infuse_iot.services.device_operations import DeviceError, DeviceOperations, device_id, kv_values
from infuse_iot.socket_comms import (
    ClientNotificationEpacketReceived,
    GatewayRequestConnectionRequest,
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


def test_gateway_socket_failure_is_unavailable(monkeypatch):
    def failing(_address):
        raise OSError(errno.EADDRINUSE, "Address already in use")

    monkeypatch.setattr("infuse_iot.services.device_operations.LocalClient", failing)
    error = failure(DeviceOperations(default_multicast_address(28885)).read, DEVICE_ID, "application_info")
    assert (error.code, error.retryable) == ("gateway_unavailable", True)
    assert error.message == "Gateway socket failed (EADDRINUSE)"


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


def test_truncated_response_header_is_invalid(device_gateway):
    gateway = device_gateway(28989)

    def respond(device, command, request):
        # A response too short to hold its header
        address = interface.Address(interface.Address.BluetoothLeAddr(0, 0))
        hop = HopReceived(device, interface.ID.BT_CENTRAL, address, Auth.DEVICE, 0, 0, 0, -60)
        gateway.server.broadcast(ClientNotificationEpacketReceived(PacketReceived([hop], InfuseType.RPC_RSP, b"\x01")))

    gateway.respond = respond
    error = failure(DeviceOperations(gateway.address).read, DEVICE_ID, "application_info")
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
