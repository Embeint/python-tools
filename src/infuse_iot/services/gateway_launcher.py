"""Start a local gateway on demand, owned by the process that started it.

Run as a module, it serves `infuse` arguments in a process that stops once its owner closes its stdin, including
when the owner is killed.
"""

import _thread
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from infuse_iot.services.device_operations import DeviceError
from infuse_iot.services.jobs import _lock

GATEWAYS = ("native_bt", "serial")
STARTUP_S = 30.0
STOP_S = 5.0
POLL_S = 0.5


def gateway_command(kind: str, port: int, serial: str | None = None, baud: int = 115200) -> list[str]:
    """The command that serves `kind` on `port`, stopping with its owner."""
    if kind == "native_bt":
        arguments = ["native_bt"]
    elif kind == "serial" and serial:
        arguments = ["gateway", "--serial", serial, "--baud", str(baud)]
    else:
        raise ValueError("A serial gateway needs its serial port")
    return [sys.executable, "-m", "infuse_iot.services.gateway_launcher", *arguments, "--server-port", str(port)]


def exit_with_owner() -> None:
    """Interrupt this process once stdin closes, and end it if it has not stopped within `STOP_S`."""

    def watch() -> None:
        try:
            while sys.stdin.buffer.read(4096):
                pass
        except (OSError, ValueError):
            pass
        if sys.platform == "win32":
            _thread.interrupt_main()
        else:
            # A real signal, unlike `interrupt_main`, also ends blocking waits
            os.kill(os.getpid(), signal.SIGINT)
        time.sleep(STOP_S)
        os._exit(0)

    threading.Thread(target=watch, name="infuse-gateway-owner", daemon=True).start()


class GatewayLauncher:
    """Start `command` when no gateway answers, and stop it on `close()`.

    An OS lock per server port makes one process the owner, so concurrent MCP servers wait for its gateway rather
    than starting another. The process keeps its output in `log_path`, away from the MCP protocol on stdout.
    """

    def __init__(
        self, kind: str, command: list[str], lock_path: Path, log_path: Path, startup_seconds: float = STARTUP_S
    ):
        self.kind = kind
        self.command = command
        self.lock_path = lock_path
        self.log_path = log_path
        self.startup_seconds = startup_seconds
        self.started_at: float | None = None
        self.exit_code: int | None = None
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._descriptor: int | None = None

    def ensure(self, probe: Callable[[], Any], check: Callable[[], None] = lambda: None) -> bool:
        """Wait until a gateway answers `probe`, starting one if none does. True if this call started it.

        `check` raises to abandon the wait; a started gateway keeps running for later calls.
        """
        with self._lock:
            if self._answers(probe):
                return False
            started = False
            if not self._running():
                self._reap()
                if self._acquire():
                    # Another gateway may have started while the lock was free
                    if self._answers(probe):
                        self._release()
                        return False
                    self._spawn()
                    started = True
            deadline = time.monotonic() + self.startup_seconds
            while True:
                check()
                if self._answers(probe):
                    return started
                if self._process is not None and self._process.poll() is not None:
                    self._reap()
                    raise DeviceError(
                        "gateway_start_failed",
                        f"{self.kind} exited with code {self.exit_code}: {self._last_line()} (log {self.log_path})",
                    )
                if time.monotonic() > deadline:
                    owner = "it" if self._process is not None else "another Infuse MCP server's gateway"
                    message = f"No gateway answered; {owner} did not answer within {self.startup_seconds:g} s"
                    raise DeviceError("gateway_unavailable", f"{message} (log {self.log_path})", True)
                time.sleep(POLL_S)

    def status(self) -> dict[str, Any]:
        process = self._process
        running = process is not None and process.poll() is None
        return {
            "kind": self.kind,
            "running": running,
            "pid": process.pid if running and process is not None else None,
            "started_at": self.started_at,
            "exit_code": None if running else self.exit_code,
            "log": str(self.log_path),
        }

    def close(self) -> None:
        """Stop a started gateway, giving it `STOP_S` to release Bluetooth or its serial port."""
        process = self._process
        if process is not None and process.poll() is None:
            if process.stdin is not None:
                process.stdin.close()
            try:
                process.wait(STOP_S + 1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        self._reap()

    @staticmethod
    def _answers(probe: Callable[[], Any]) -> bool:
        try:
            probe()
        except (TimeoutError, OSError):
            return False
        return True

    def _running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def _acquire(self) -> bool:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        if not _lock(descriptor):
            os.close(descriptor)
            return False
        self._descriptor = descriptor
        return True

    def _release(self) -> None:
        if self._descriptor is not None:
            # Closing the descriptor releases its lock
            os.close(self._descriptor)
            self._descriptor = None

    def _spawn(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        options: dict[str, Any] = {}
        if sys.platform == "win32":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            # Signals for the host's process group reach this server, which then stops the gateway itself
            options["start_new_session"] = True
        with open(self.log_path, "wb") as log:
            self._process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=subprocess.STDOUT,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
                **options,
            )
        self.started_at, self.exit_code = time.time(), None

    def _reap(self) -> None:
        process, self._process = self._process, None
        if process is not None:
            self.exit_code = process.poll()
            if process.stdin is not None:
                process.stdin.close()
        self._release()

    def _last_line(self) -> str:
        try:
            lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return "no output"
        line = next((line.strip() for line in reversed(lines) if line.strip()), "no output")
        return line[:200]


if __name__ == "__main__":
    exit_with_owner()
    from infuse_iot.app.main import main

    main(sys.argv[1:])
