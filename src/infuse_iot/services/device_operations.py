"""Structured device RPC operations without CLI formatting or MCP types."""

import ctypes
import errno
import math
import re
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

import infuse_iot.definitions.kv as kv
import infuse_iot.definitions.rpc as defs
from infuse_iot.commands import rpc_return_code_str
from infuse_iot.epacket.packet import Auth
from infuse_iot.rpc_client import RpcClient
from infuse_iot.socket_comms import GatewayControlError, GatewayRequestConnectionRequest, LocalClient

READ_KEYS = ("REBOOTS", "DEVICE_NAME", "BLUETOOTH_ADDR")
READ_COMMANDS = ("application_info", "last_reboot", "data_logger_state", "kv_read")
DEVICE_ID_PATTERN = r"^(0x)?[0-9a-fA-F]{1,16}$"
# Larger integers lose precision as JSON numbers in JavaScript.
MAX_SAFE_INTEGER = 2**53 - 1
# Waiting for this server's other operations, or a gateway link that is still closing, fails as `device_busy`.
BUSY_WAIT_S = 5.0
# Callers beyond this many waiting for the lock fail immediately, so waits cannot exhaust worker threads.
MAX_WAITERS = 2
CONNECT_TIMEOUT_S = 15.0
# The gateway releases an abandoned operation this long after the owner's last traffic.
LEASE_MARGIN_S = 10.0


class DeviceError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        self.code, self.message, self.retryable = code, message, retryable
        super().__init__(message)


def device_id(value: str) -> int:
    """Parse a full hexadecimal device ID, rejecting whitespace, separators and non-ASCII digits."""
    if not isinstance(value, str) or not re.fullmatch(DEVICE_ID_PATTERN, value):
        raise ValueError(
            "Device IDs are 1 to 16 hexadecimal digits with an optional 0x prefix; "
            "address a serial gateway by its own device ID"
        )
    return int(value, 16)


def struct_data(value: Any) -> Any:
    if isinstance(value, ctypes.Array | list | tuple):
        return [struct_data(item) for item in value]
    if isinstance(value, bytes):
        # Fields declared as `c_char` arrays are read back as text
        return value.rstrip(b"\x00").decode("utf-8", errors="replace")
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > MAX_SAFE_INTEGER:
        return str(value)
    if isinstance(value, ctypes.Structure):
        if all(hasattr(value, field) for field in ("major", "minor", "revision", "build_num")):
            return f"{value.major}.{value.minor}.{value.revision}+{value.build_num:08x}"
        result = {field[0]: struct_data(getattr(value, field[0])) for field in value._fields_}
        vla = getattr(value, "vla_field", None)
        if vla:
            result[vla[0]] = struct_data(getattr(value, vla[0]))
        return result
    return value


def _kv_value(name: str, data: bytes) -> dict[str, Any]:
    slot = getattr(kv.slots, name.lower())
    value = slot.vla_from_buffer_copy(data)
    if name == "DEVICE_NAME":
        return {"name": bytes(value.name.value).rstrip(b"\x00").decode("utf-8", errors="replace")}
    if name == "BLUETOOTH_ADDR":
        address = value.address
        # Zephyr stores the address least significant byte first
        return {"type": address.type, "address": bytes(address.val)[::-1].hex(":").upper()}
    return {"count": value.count}


def kv_values(response: Any) -> list[dict[str, Any]]:
    """Each value of a KV read, with keys that could not be read reported by status rather than as data."""
    names = {getattr(kv.slots, name.lower()).BASE_ID: name for name in READ_KEYS}
    values = []
    for item in response.values:
        name = names.get(item.id)
        entry: dict[str, Any] = {"id": item.id, "key": name}
        if item.len < 0:
            # The firmware reports a key it could not read with a negative errno as its length.
            entry.update(
                status="not_set" if -item.len == errno.ENOENT else "error",
                error_code=item.len,
                error=rpc_return_code_str(item.len),
            )
        else:
            raw = bytes(item.data)
            entry.update(status="ok", raw=raw.hex(), value=None)
            if name is not None:
                try:
                    entry["value"] = _kv_value(name, raw)
                except (TypeError, ValueError, UnicodeDecodeError):
                    entry["status"] = "invalid"
        values.append(entry)
    return values


class DeviceOperations:
    """Run bounded device operations, one at a time per server process.

    Every operation, including later write and update jobs, runs within `exclusive()`. It waits at
    most `busy_wait_seconds` for another operation, so callers report `device_busy` rather than
    queueing indefinitely behind a long operation.
    """

    def __init__(self, address: tuple[str, int]):
        self.address = address
        self.lock = threading.Lock()
        self.busy_wait_seconds = BUSY_WAIT_S
        self.connect_timeout_seconds = CONNECT_TIMEOUT_S
        self._waiters = threading.Semaphore(MAX_WAITERS)

    @contextmanager
    def exclusive(self, timeout: float | None = None) -> Iterator[None]:
        busy = DeviceError("device_busy", "Another device operation in this server is still running", True)
        if not self.lock.acquire(blocking=False):
            if not self._waiters.acquire(blocking=False):
                raise busy
            try:
                if not self.lock.acquire(timeout=self.busy_wait_seconds if timeout is None else timeout):
                    raise busy
            finally:
                self._waiters.release()
        try:
            yield
        finally:
            self.lock.release()

    def read(
        self,
        identifier: str,
        command: str,
        parameters: dict | None = None,
        timeout_seconds: float = 10,
        cancelled: threading.Event | None = None,
    ) -> dict:
        """Run an allowlisted read RPC.

        Every phase is bounded: waiting for the device to be free, gateway queries, connection setup
        and `timeout_seconds` for the response. `cancelled` stops the read before its next phase.
        """
        target = device_id(identifier)
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int | float)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 30
        ):
            raise ValueError("timeout_seconds must be greater than 0 and at most 30")
        definition, request = self._request(command, parameters or {})
        decode = getattr(definition.response, "vla_from_buffer_copy", definition.response.from_buffer_copy)

        def decoder(payload: bytes) -> Any:
            try:
                return decode(payload)
            except (TypeError, ValueError, IndexError) as error:
                # Reported as an undecodable response, rather than a malformed request
                raise ValueError("Malformed response") from error

        start = time.monotonic()
        with self.exclusive():
            self._check(cancelled)
            client = self._client()
            try:
                with ExitStack() as stack:
                    self._own(stack, client, target, timeout_seconds, start, cancelled)
                    self._check(cancelled)
                    try:
                        mtu = stack.enter_context(
                            client.connection(
                                target,
                                GatewayRequestConnectionRequest.DataType.COMMAND,
                                int(self.connect_timeout_seconds * 1000),
                            )
                        )
                    except ConnectionRefusedError as error:
                        raise DeviceError("connection_failed", f"Gateway could not connect: {error}", True) from None
                    except TimeoutError:
                        raise DeviceError("connection_timeout", "Timed out connecting to the device", True) from None
                    self._check(cancelled)
                    rpc = RpcClient(client, mtu, target)
                    rpc.set_timeout(timeout_seconds)
                    try:
                        header, response = rpc.run_standard_cmd(definition.COMMAND_ID, Auth.DEVICE, request, decoder)
                    except ValueError:
                        # A response too short for its header, rather than a malformed request
                        raise DeviceError("device_response_invalid", "Device response could not be decoded") from None
                    if header is None:
                        raise DeviceError("rpc_timeout", "Device did not return an RPC response", True)
                    if header.return_code:
                        raise DeviceError("rpc_rejected", rpc_return_code_str(header.return_code))
                    if response is None:
                        raise DeviceError("device_response_invalid", "Device response could not be decoded")
                    return {
                        "device_id": f"0x{target:016x}",
                        "command": command,
                        "observed_at": time.time(),
                        "response": {"values": kv_values(response)} if command == "kv_read" else struct_data(response),
                    }
            except ConnectionAbortedError:
                raise DeviceError("connection_dropped", "Device disconnected", True) from None
            except GatewayControlError as error:
                raise DeviceError(
                    error.code, error.message or error.code, error.code in ("device_busy", "operation_expired")
                ) from None
            except (TimeoutError, ConnectionError, socket.gaierror):
                raise DeviceError("gateway_unavailable", "Gateway stopped answering", True) from None
            finally:
                client.close()

    def _client(self) -> LocalClient:
        try:
            return LocalClient(self.address)
        except OSError as error:
            # Binding the socket and joining the multicast group fail as `infuse_status` reports them.
            name = errno.errorcode.get(error.errno or 0, type(error).__name__)
            raise DeviceError("gateway_unavailable", f"Gateway socket failed ({name})", True) from None

    @staticmethod
    def _check(cancelled: threading.Event | None) -> None:
        if cancelled is not None and cancelled.is_set():
            raise DeviceError("cancelled", "The read was cancelled")

    def _own(
        self,
        stack: ExitStack,
        client: LocalClient,
        target: int,
        timeout_seconds: float,
        start: float,
        cancelled: threading.Event | None,
    ) -> None:
        """Own the device at the gateway, retrying briefly while a released link closes."""
        try:
            capabilities = client.capabilities()
        except (TimeoutError, OSError):
            raise DeviceError(
                "gateway_unavailable", "No gateway answered; start infuse native_bt or infuse gateway", True
            ) from None
        if "operation_ownership" not in capabilities.get("features", []):
            # Older gateways cannot coordinate clients, but are still readable.
            return
        # Traffic renews the lease, so it covers the longest silent phase rather than the whole read.
        silent = max(self.connect_timeout_seconds + LocalClient.CONNECTION_RESPONSE_MARGIN_S, timeout_seconds)
        lease = silent + LEASE_MARGIN_S
        while True:
            try:
                stack.enter_context(client.operation(target, lease))
                return
            except GatewayControlError as error:
                if error.code != "device_busy" or time.monotonic() - start + 0.5 > self.busy_wait_seconds:
                    raise
            self._check(cancelled)
            time.sleep(0.5)

    @staticmethod
    def _request(command: str, parameters: dict) -> tuple[Any, bytes]:
        if not isinstance(parameters, dict):
            raise ValueError("parameters must be an object")
        if command in ("application_info", "last_reboot"):
            if parameters:
                raise ValueError(f"{command} takes no parameters")
            definition = getattr(defs, command)
            return definition, bytes(definition.request())
        if command == "data_logger_state":
            loggers = {
                "onboard": defs.rpc_enum_data_logger.FLASH_ONBOARD,
                "removable": defs.rpc_enum_data_logger.FLASH_REMOVABLE,
            }
            logger = parameters.get("logger", "onboard")
            if set(parameters) - {"logger"} or logger not in loggers:
                raise ValueError("data_logger_state takes an optional logger: onboard or removable")
            return defs.data_logger_state, bytes(defs.data_logger_state.request(loggers[logger]))
        if command == "kv_read":
            keys = parameters.get("keys")
            if (
                set(parameters) != {"keys"}
                or not isinstance(keys, list)
                or not 1 <= len(keys) <= len(READ_KEYS)
                or any(name not in READ_KEYS for name in keys)
            ):
                raise ValueError(f"kv_read takes keys: a list of 1 to 3 of {', '.join(READ_KEYS)}")
            key_ids = [getattr(kv.slots, name.lower()).BASE_ID for name in keys]
            request = bytes(defs.kv_read.request(len(keys))) + bytes((ctypes.c_uint16 * len(keys))(*key_ids))
            return defs.kv_read, request
        raise ValueError(f"Supported read commands: {', '.join(READ_COMMANDS)}")
