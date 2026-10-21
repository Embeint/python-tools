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
        add_server_port_parser(parser)

    def __init__(self, args):
        self.args = args

    def run(self):
        if sys.version_info < (3, 11):
            sys.exit(f"MCP needs Python 3.11 or newer, but this is Python {sys.version_info[0]}.{sys.version_info[1]}")
        if importlib.util.find_spec("mcp") is None:
            sys.exit(f"MCP needs the optional extra: {INSTALL}")
        try:
            with contextlib.redirect_stdout(sys.stderr):
                from infuse_iot.mcp_server.server import ReadService, create_server

                service = ReadService(self.args.server_sock)
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
