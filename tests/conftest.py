"""Reject test runs that could access a user's credential store, and provide shared fixtures."""

import os
import threading
from pathlib import Path

import keyring
import pytest

from infuse_iot.socket_comms import (
    ClientNotificationCommsCheck,
    GatewayRequestCommsCheck,
    LocalServer,
    default_multicast_address,
)


def pytest_sessionstart():
    test_root = os.environ.get("TOXTEMPDIR")
    if not test_root or os.environ.get("PYTHON_KEYRING_BACKEND") != "keyrings.alt.file.PlaintextKeyring":
        raise pytest.UsageError("Run these tests using tox to isolate credential storage")
    backend = keyring.get_keyring()
    keyring_path = getattr(backend, "file_path", None)
    if keyring_path is None or not Path(keyring_path).resolve().is_relative_to(Path(test_root).resolve()):
        raise pytest.UsageError("Test keyring must be stored inside TOXTEMPDIR")


class LoopbackGateway:
    """A gateway server on a loopback port, answering requests as both gateways do."""

    def __init__(self, port: int):
        self.address = default_multicast_address(port)
        self.server = LocalServer(self.address)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        while not self._stop.is_set():
            # Capability and control requests are answered within `receive`
            if isinstance(self.server.receive(), GatewayRequestCommsCheck):
                self.server.broadcast(ClientNotificationCommsCheck())

    def send_raw(self, datagram: bytes):
        self.server._output_sock.sendto(datagram, self.address)

    def close(self):
        self._stop.set()
        self._thread.join()
        self.server.close()


@pytest.fixture
def loopback_gateway():
    """Start gateways on unused loopback ports, distinct from the default 8751."""
    gateways: list[LoopbackGateway] = []

    def start(port: int) -> LoopbackGateway:
        gateways.append(LoopbackGateway(port))
        return gateways[-1]

    yield start
    for gateway in gateways:
        gateway.close()
