"""Optional local MCP server entry point."""

import contextlib
import importlib.metadata
import importlib.util
import sys

from infuse_iot.commands import InfuseCommand
from infuse_iot.util.argparse import add_server_port_parser

INSTALL = 'pip install "infuse-iot[mcp]"'


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--transport", choices=["stdio"], default="stdio")
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
                from infuse_iot.mcp_server.server import create_server

                server = create_server(self.args.server_sock)
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
