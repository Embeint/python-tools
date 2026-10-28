"""Optional local MCP server entry point."""

import contextlib
import importlib.metadata
import importlib.util
import sqlite3
import sys
from pathlib import Path

from infuse_iot.commands import InfuseCommand
from infuse_iot.util.argparse import add_server_port_parser

INSTALL = 'pip install "infuse-iot[mcp]"'


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--transport", choices=["stdio"], default="stdio")
        parser.add_argument("--allow-writes", action="store_true", help="Expose targeted actions and persistent jobs")
        parser.add_argument("--state-directory", type=Path, help="Override the profile-scoped job state directory")
        parser.add_argument(
            "--start-gateway",
            choices=["native_bt", "serial"],
            help="Start this gateway when a tool needs one and none answers, stopping it when the server exits",
        )
        parser.add_argument("--gateway-serial", help="Serial port for a started serial gateway")
        parser.add_argument("--gateway-baud", type=int, default=115200, help="Baudrate for a started serial gateway")
        parser.add_argument(
            "--scan-seconds",
            type=float,
            default=20.0,
            help="Wait up to this long for an unheard device before connecting, and scan this long after starting "
            "a gateway (default 20)",
        )
        add_server_port_parser(parser)

    def __init__(self, args):
        self.args = args

    def run(self):
        if (self.args.start_gateway == "serial") != (self.args.gateway_serial is not None):
            sys.exit("--gateway-serial is needed for, and only used with, --start-gateway serial")
        if not 0 <= self.args.scan_seconds <= 60:
            sys.exit("--scan-seconds must be in 0..60")
        if sys.version_info < (3, 11):
            sys.exit(f"MCP needs Python 3.11 or newer, but this is Python {sys.version_info[0]}.{sys.version_info[1]}")
        if importlib.util.find_spec("mcp") is None:
            sys.exit(f"MCP needs the optional extra: {INSTALL}")
        try:
            with contextlib.redirect_stdout(sys.stderr):
                from infuse_iot.mcp_server.server import ReadService, create_server

                service = ReadService(self.args.server_sock, self._launcher(), self.args.scan_seconds)
                server = create_server(
                    self.args.server_sock,
                    service,
                    allow_writes=self.args.allow_writes,
                    state_directory=self.args.state_directory,
                )
                if service.jobs is not None:
                    # Recovery uses SQLite, so it runs before serving rather than on the event loop.
                    service.jobs.start()
        except (OSError, sqlite3.Error, RuntimeError) as error:
            if not self.args.allow_writes:
                raise
            # Writes are never silently disabled, so a server without its job state does not start.
            sys.exit(f"MCP writes need the job state, which is unavailable: {error}")
        except ImportError as error:
            # Only an SDK that lacks what the server imports is explained; other failures are defects.
            if error.name is None or error.name.partition(".")[0] != "mcp":
                raise
            try:
                installed = importlib.metadata.version("mcp")
            except importlib.metadata.PackageNotFoundError:
                installed = "unknown"
            sys.exit(f"MCP needs mcp>=2.3,<3, but version {installed} is installed: {INSTALL}")
        server.run(transport=self.args.transport)

    def _launcher(self):
        if self.args.start_gateway is None:
            return None
        import platformdirs

        from infuse_iot.services.gateway_launcher import GatewayLauncher, gateway_command

        kind, port = self.args.start_gateway, self.args.server_sock[1]
        directory = self.args.state_directory or Path(platformdirs.user_cache_dir("infuse-iot", "Embeint")) / "mcp"
        command = gateway_command(kind, port, self.args.gateway_serial, self.args.gateway_baud)
        return GatewayLauncher(kind, command, directory / f"gateway-{port}.lock", directory / f"{kind}-{port}.log")
