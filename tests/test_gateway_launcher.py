"""Gateways started on demand are owned by one process and stop with it."""

import subprocess
import sys
import time

import pytest

from infuse_iot.services.device_operations import DeviceError
from infuse_iot.services.gateway_launcher import GatewayLauncher, gateway_command
from infuse_iot.socket_comms import LocalClient, default_multicast_address

GATEWAY = """
import sys

from infuse_iot.services.gateway_launcher import exit_with_owner
from infuse_iot.socket_comms import (
    ClientNotificationCommsCheck,
    GatewayRequestCommsCheck,
    LocalServer,
    default_multicast_address,
)

exit_with_owner()
server = LocalServer(default_multicast_address(int(sys.argv[1])))
print("serving", flush=True)
try:
    while True:
        if isinstance(server.receive(), GatewayRequestCommsCheck):
            server.broadcast(ClientNotificationCommsCheck())
except KeyboardInterrupt:
    server.close()
"""


def probe_for(port: int):
    def probe() -> dict:
        client = LocalClient(default_multicast_address(port))
        try:
            return client.capabilities()
        finally:
            client.close()

    return probe


def launcher_for(tmp_path, command: list[str], startup_seconds: float = 15) -> GatewayLauncher:
    return GatewayLauncher("native_bt", command, tmp_path / "gateway.lock", tmp_path / "gateway.log", startup_seconds)


def test_gateway_command_serves_the_requested_port():
    command = gateway_command("native_bt", 8751)
    assert command[:3] == [sys.executable, "-m", "infuse_iot.services.gateway_launcher"]
    assert command[3:] == ["native_bt", "--server-port", "8751"]
    command = gateway_command("serial", 8753, "/dev/ttyACM0", 1000000)
    assert command[3:] == ["gateway", "--serial", "/dev/ttyACM0", "--baud", "1000000", "--server-port", "8753"]
    with pytest.raises(ValueError, match="serial port"):
        gateway_command("serial", 8753)


def test_gateway_stops_once_its_owner_closes_stdin():
    code = "from infuse_iot.services.gateway_launcher import exit_with_owner; exit_with_owner(); import time; "
    process = subprocess.Popen([sys.executable, "-c", code + "time.sleep(60)"], stdin=subprocess.PIPE)
    time.sleep(0.5)
    assert process.poll() is None
    assert process.stdin is not None
    # As when the owner exits or is killed
    process.stdin.close()
    process.wait(timeout=3)


def test_started_gateway_is_reused_and_stopped_on_close(tmp_path):
    script = tmp_path / "gateway.py"
    script.write_text(GATEWAY, encoding="utf-8")
    probe = probe_for(28995)
    launcher = launcher_for(tmp_path, [sys.executable, str(script), "28995"])
    other = launcher_for(tmp_path / "other", [sys.executable, "-c", "raise SystemExit(1)"])
    try:
        assert launcher.ensure(probe) is True
        assert launcher.ensure(probe) is False
        assert other.ensure(probe) is False
        status = launcher.status()
        assert status["running"] and status["pid"] and status["exit_code"] is None
        assert "serving" in (tmp_path / "gateway.log").read_text()
    finally:
        launcher.close()
    assert not launcher.status()["running"] and launcher.status()["exit_code"] is not None
    with pytest.raises(TimeoutError):
        probe()


def test_gateway_that_exits_reports_its_last_output(tmp_path):
    code = "print('Bluetooth adapter unavailable'); raise SystemExit(3)"
    launcher = launcher_for(tmp_path, [sys.executable, "-c", code])
    with pytest.raises(DeviceError) as raised:
        launcher.ensure(probe_for(28997))
    assert raised.value.code == "gateway_start_failed" and not raised.value.retryable
    assert "code 3: Bluetooth adapter unavailable" in raised.value.message
    # The lock is released, so a later call can start it again
    assert launcher._acquire()
    launcher._release()


def test_a_gateway_another_server_is_starting_is_awaited(tmp_path):
    probe = probe_for(28999)
    silent = "from infuse_iot.services.gateway_launcher import exit_with_owner; exit_with_owner(); import time; "
    starting = launcher_for(tmp_path, [sys.executable, "-c", silent + "time.sleep(30)"], startup_seconds=0.5)
    waiting = launcher_for(tmp_path, [sys.executable, "-c", "raise SystemExit(1)"], startup_seconds=1)
    waiting.log_path = tmp_path / "waiting.log"
    try:
        with pytest.raises(DeviceError, match="did not answer"):
            starting.ensure(probe)
        assert starting.status()["running"]
        with pytest.raises(DeviceError, match="another Infuse MCP server") as raised:
            waiting.ensure(probe)
        assert raised.value.code == "gateway_unavailable" and raised.value.retryable
        assert not waiting.log_path.exists()
    finally:
        starting.close()
