"""Optional local MCP server entry point."""

import contextlib
import sys

from infuse_iot.commands import InfuseCommand
from infuse_iot.util.argparse import add_server_port_parser


class SubCommand(InfuseCommand):
    @classmethod
    def add_parser(cls, parser):
        parser.add_argument("--transport", choices=["stdio"], default="stdio")
        add_server_port_parser(parser)

    def __init__(self, args):
        self.args = args

    def run(self):
        try:
            with contextlib.redirect_stdout(sys.stderr):
                from infuse_iot.mcp_server.server import create_server

                server = create_server(self.args.server_sock)
        except ImportError as error:
            sys.exit(f'MCP needs the optional extra: pip install "infuse-iot[mcp]" ({error.name} is missing)')
        server.run(transport=self.args.transport)
