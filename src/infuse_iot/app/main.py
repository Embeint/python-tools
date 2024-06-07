#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

"""Infuse-IoT SDK meta-tool (infuse) main module"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Inc"

import argparse
import sys
import pkgutil
import importlib.util
import argcomplete

import infuse_iot.tools
from infuse_iot.commands import InfuseCommand


class InfuseApp:
    """The infuse 'application' object"""

    def __init__(self):
        self.parser = argparse.ArgumentParser("infuse")
        self._tools = {}
        # Load tools
        self._load_tools(self.parser)
        # Handle CLI tab completion
        argcomplete.autocomplete(self.parser)

    def run(self, argv):
        """Run the chosen subtool handler"""
        self.args = self.parser.parse_args(argv)

        tool = self.args.tool_class(self.args)
        tool.run()

    def _load_tools(self, parser: argparse.ArgumentParser):
        tools_parser = parser.add_subparsers(title="commands", metavar="<command>")

        # Iterate over tools
        for _, name, _ in pkgutil.walk_packages(infuse_iot.tools.__path__):
            full_name = f"{infuse_iot.tools.__name__}.{name}"
            module = importlib.import_module(full_name)

            # Add tool to parser
            tool_cls: InfuseCommand = getattr(module, "SubCommand")
            parser = tools_parser.add_parser(
                tool_cls.NAME,
                help=tool_cls.HELP,
                description=tool_cls.DESCRIPTION,
                formatter_class=argparse.RawDescriptionHelpFormatter,
            )
            parser.set_defaults(tool_class=tool_cls)
            tool_cls.add_parser(parser)


def main(argv=None):
    """Create the InfuseApp instance and let it run"""
    app = InfuseApp()
    try:
        app.run(argv or sys.argv[1:])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
