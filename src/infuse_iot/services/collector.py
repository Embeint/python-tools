"""A managed telemetry subscription that never owns the user's gateway."""

import errno
import logging
import threading
from typing import Any

from infuse_iot.services.device_state import DeviceState
from infuse_iot.socket_comms import (
    ClientNotificationCommsCheck,
    ClientNotificationEpacketReceived,
    GatewayControlError,
    LocalClient,
)

GATEWAY_UNAVAILABLE = "No gateway answered; start infuse native_bt or infuse gateway"
# Consecutive unanswered capability probes after which an attached gateway is considered gone.
MAX_UNANSWERED_PROBES = 3


def gateway_identity(capabilities: dict[str, Any]) -> dict[str, Any]:
    """The identity a gateway reports in its capabilities, absent for older gateways."""
    return {key: capabilities.get(key) for key in ("instance_id", "version", "gateway_kind", "protocol_version")}


def unavailable(error: OSError) -> GatewayControlError:
    """The `gateway_unavailable` error for a gateway that did not answer, or a local socket that failed."""
    if isinstance(error, TimeoutError):
        return GatewayControlError("gateway_unavailable", GATEWAY_UNAVAILABLE)
    # Named by errno, as the error text can include local details
    name = errno.errorcode.get(error.errno or 0, type(error).__name__)
    return GatewayControlError("gateway_unavailable", f"Gateway socket failed ({name})")


def probe_gateway(address: tuple[str, int]) -> dict[str, Any]:
    """The gateway's capabilities, raising `GatewayControlError` with code `gateway_unavailable` if none answers."""
    client = None
    try:
        client = LocalClient(address)
        return client.capabilities()
    except OSError as error:
        raise unavailable(error) from None
    finally:
        if client is not None:
            client.close()


def gateway_counters(address: tuple[str, int], capabilities: dict[str, Any]) -> dict[str, int] | None:
    """Radio and decryption counters since the gateway started, if it reports them."""
    if "diagnostics" not in capabilities.get("features", []):
        return None
    client = None
    try:
        # A separate client, so that a running collector cannot consume the reply.
        client = LocalClient(address)
        values = client.control_request("diagnostics", {})
    except (GatewayControlError, OSError):
        return None
    finally:
        if client is not None:
            client.close()
    return {k: v for k, v in values.items() if isinstance(v, int) and not isinstance(v, bool)}


def counter_changes(
    before: dict[str, int] | None, after: dict[str, int] | None, before_instance: Any = None, after_instance: Any = None
) -> dict[str, int] | None:
    """Counter increments between two queries, or `None` unless both came from the same gateway instance.

    Counters restart with the gateway, so a decrease also shows a restart between the queries.
    """
    if before is None or after is None or before_instance != after_instance:
        return None
    changes = {k: v - before[k] for k, v in after.items() if k in before}
    return None if any(v < 0 for v in changes.values()) else changes


class TelemetryCollector:
    """Decode telemetry from a gateway into `state`, which persists when the collector is restarted.

    `start()` attaches, or reattaches after `close()` or a failure. `running` reports whether the
    worker is receiving. A socket failure stops it, reported in `error` with `error_code`. Unknown
    or malformed notifications are skipped and counted in `skipped_notifications`. The socket keeps
    receiving from a restarted or replaced gateway, so `capabilities` and the identity in
    `state.gateway` follow any capability reply received, or `refresh()` with a new probe. The
    socket cannot fail when the gateway stops, so the owner reports unanswered probes with
    `unanswered()`, which stops the worker after `MAX_UNANSWERED_PROBES` in a row.
    """

    def __init__(self, address: tuple[str, int]):
        self.address = address
        self.state = DeviceState()
        self.capabilities: dict[str, Any] = {}
        self.error: str | None = None
        self.error_code: str | None = None
        self._skipped = 0
        self._unanswered = 0
        self._lock = threading.Lock()
        self._client: LocalClient | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    @property
    def running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    @property
    def skipped_notifications(self) -> int:
        """Notifications skipped by the gateway client or while decoding their packets."""
        client = self._client
        return self._skipped + (0 if client is None else client.ignored_notifications)

    def start(self) -> None:
        """Attach to the gateway, raising `GatewayControlError` with code `gateway_unavailable` if none answers."""
        with self._lock:
            if self.running:
                return
            self._shutdown()
            client = None
            try:
                # Binding the socket and joining the multicast group can also fail
                client = LocalClient(self.address)
                capabilities = client.capabilities()
            except OSError as error:
                if client is not None:
                    client.close()
                raise unavailable(error) from None
            self.refresh(capabilities, force=True)
            self.error = self.error_code = None
            self._client = client
            self._stop = threading.Event()
            self._thread = threading.Thread(target=self._run, args=(client, self._stop), name="infuse-telemetry")
            self._thread.daemon = True
            self._thread.start()

    def refresh(self, capabilities: dict[str, Any], force: bool = False) -> None:
        """Adopt newly probed capabilities, reporting the new identity if the gateway was restarted or replaced."""
        changed = force or gateway_identity(capabilities) != gateway_identity(self.capabilities)
        self.capabilities = capabilities
        self._unanswered = 0
        if changed:
            with self.state.lock:
                self.state.gateway = gateway_identity(capabilities)

    def unanswered(self) -> None:
        """Record a capability probe that no gateway answered, detaching once the gateway is considered gone.

        The worker then stops with `error_code` `gateway_unavailable` and no gateway identity, until
        `start()` attaches to a gateway that answers.
        """
        with self._lock:
            self._unanswered += 1
            if self._unanswered < MAX_UNANSWERED_PROBES or not self.running:
                return
            self._shutdown()
            self.error_code, self.error = "gateway_unavailable", "The gateway stopped answering capability probes"
            self.capabilities = {}
            with self.state.lock:
                self.state.gateway = None

    def _run(self, client: LocalClient, stop: threading.Event) -> None:
        try:
            while not stop.is_set():
                try:
                    message = client.receive()
                    if isinstance(message, ClientNotificationEpacketReceived):
                        self.state.observe(message.epacket)
                    elif isinstance(message, ClientNotificationCommsCheck) and isinstance(message.capabilities, dict):
                        # Replies to any client's capability query identify the gateway now serving telemetry.
                        self.refresh(message.capabilities)
                except OSError as error:
                    self.error_code, self.error = "gateway_unavailable", f"Gateway socket failed: {error}"
                    return
                except Exception:
                    # A packet that fails to decode must not stop collection.
                    self._skipped += 1
                    logging.getLogger(__name__).debug("Skipped notification", exc_info=True)
        finally:
            # Wake a collection waiting on this worker.
            stop.set()

    def _shutdown(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                raise RuntimeError("Telemetry worker did not stop")
            self._thread = None
        if self._client is not None:
            self._skipped += self._client.ignored_notifications
            self._client.close()
            self._client = None

    def close(self) -> None:
        """Stop receiving and release the socket. `state` is kept for a later `start()`."""
        with self._lock:
            self._shutdown()

    def collect(self, duration_seconds: float, **query: Any) -> dict:
        """Collect telemetry for a window, returning a `DeviceState.snapshot` with the window's counters."""
        if isinstance(duration_seconds, bool) or not 0 <= duration_seconds <= 60:
            raise ValueError("duration_seconds must be between 0 and 60")
        self.start()
        try:
            instance = self.capabilities.get("instance_id")
            before = gateway_counters(self.address, self.capabilities)
            self._stop.wait(duration_seconds)
            if self.error_code is not None or not self.running:
                raise GatewayControlError(self.error_code or "internal_error", self.error or "Telemetry worker stopped")
            # The multicast socket cannot report a gateway that stopped, so it must answer at the end of the window.
            capabilities = probe_gateway(self.address)
            self.refresh(capabilities)
            after = gateway_counters(self.address, capabilities)
            gateway = {**gateway_identity(capabilities)}
            gateway["counters"] = counter_changes(before, after, instance, capabilities.get("instance_id"))
            self.state.gateway = gateway
            return self.state.snapshot(**query)
        finally:
            self.close()
