"""Reject test runs that could access a user's credential store, and provide shared fixtures."""

import ctypes
import os
import threading
from collections.abc import Callable
from pathlib import Path

import keyring
import pytest

from infuse_iot import rpc
from infuse_iot.common import InfuseType
from infuse_iot.epacket import interface
from infuse_iot.epacket.packet import Auth, HopReceived, PacketReceived
from infuse_iot.socket_comms import (
    ClientNotificationCommsCheck,
    ClientNotificationConnectionCreated,
    ClientNotificationConnectionDropped,
    ClientNotificationEpacketReceived,
    GatewayRequest,
    GatewayRequestCommsCheck,
    GatewayRequestConnectionRelease,
    GatewayRequestConnectionRequest,
    GatewayRequestEpacketSend,
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
            request = self.server.receive()
            if isinstance(request, GatewayRequestCommsCheck):
                self.server.broadcast(ClientNotificationCommsCheck())
            elif request is not None:
                self.handle(request)

    def handle(self, request: GatewayRequest):
        pass

    def send_raw(self, datagram: bytes):
        self.server._output_sock.sendto(datagram, self.address)

    def close(self):
        self._stop.set()
        self._thread.join()
        self.server.close()


class DeviceGateway(LoopbackGateway):
    """A loopback gateway that connects to any device and answers RPCs with `respond`.

    `respond(device, command_id, request)` returns a return code and payload, or `None` to stay silent.
    Released links report their teardown after `drop_delay`, except for the gateway's `local_device`.
    """

    def __init__(self, port: int, local_device: int | None = None):
        self.respond: Callable[[int, int, bytes], tuple[int, bytes] | None] = lambda device, command, request: (0, b"")
        self.connect = True
        self.drop_delay = 0.0
        self.requests: list[GatewayRequest] = []
        super().__init__(port)
        if local_device is not None:
            self.server.control.is_local = lambda device: device == local_device

    def handle(self, request: GatewayRequest):
        self.requests.append(request)
        if isinstance(request, GatewayRequestConnectionRequest):
            if self.connect:
                self.server.broadcast(ClientNotificationConnectionCreated(request.infuse_id, 244))
        elif isinstance(request, GatewayRequestConnectionRelease):
            if not self.server.control.is_local(request.infuse_id):
                drop = ClientNotificationConnectionDropped(request.infuse_id)
                threading.Timer(self.drop_delay, self._broadcast_quietly, (drop,)).start()
        elif isinstance(request, GatewayRequestEpacketSend) and request.epacket.ptype == InfuseType.RPC_CMD:
            header = rpc.RequestHeader.from_buffer_copy(request.epacket.payload)
            body = request.epacket.payload[ctypes.sizeof(rpc.RequestHeader) :]
            reply = self.respond(request.epacket.infuse_id, header.command_id, body)
            if reply is None:
                return
            response = bytes(rpc.ResponseHeader(header.request_id, header.command_id, reply[0])) + reply[1]
            address = interface.Address(interface.Address.BluetoothLeAddr(0, 0))
            hop = HopReceived(request.epacket.infuse_id, interface.ID.BT_CENTRAL, address, Auth.DEVICE, 0, 0, 0, -60)
            packet = PacketReceived([hop], InfuseType.RPC_RSP, response)
            self.server.broadcast(ClientNotificationEpacketReceived(packet))

    def _broadcast_quietly(self, notification):
        try:
            self.server.broadcast(notification)
        except OSError:
            # The gateway closed before a delayed notification
            pass


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


@pytest.fixture
def device_gateway():
    """Start gateways that connect to devices and answer RPCs, on unused loopback ports."""
    gateways: list[DeviceGateway] = []

    def start(port: int, local_device: int | None = None) -> DeviceGateway:
        gateways.append(DeviceGateway(port, local_device))
        return gateways[-1]

    yield start
    for gateway in gateways:
        gateway.close()
