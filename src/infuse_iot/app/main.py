#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

"""Infuse-IoT SDK meta-tool (infuse) main module"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import argparse
import importlib.util
import pathlib
import pkgutil
import sys
import types

import argcomplete

import infuse_iot.tools
from infuse_iot.commands import InfuseCommand
from infuse_iot.credentials import get_custom_tool_path
from infuse_iot.version import __version__


class InfuseApp:
    """The infuse 'application' object"""

    def __init__(self):
        self.args = None
        self.parser = argparse.ArgumentParser("infuse")
        self.parser.add_argument("--version", action="version", version=f"{__version__}")
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

    def _load_from_module(self, parent_parser: argparse._SubParsersAction, module: types.ModuleType):
        tool_cls: InfuseCommand = module.SubCommand
        parser = parent_parser.add_parser(
            tool_cls.NAME,
            help=tool_cls.HELP,
            description=tool_cls.DESCRIPTION,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        parser.set_defaults(tool_class=tool_cls)
        tool_cls.add_parser(parser)

    def _load_tools(self, parser: argparse.ArgumentParser):
        tools_parser = parser.add_subparsers(title="commands", metavar="<command>", required=True)

        # Iterate over local tools
        for _, name, _ in pkgutil.walk_packages(infuse_iot.tools.__path__):
            full_name = f"{infuse_iot.tools.__name__}.{name}"
            module = importlib.import_module(full_name)
            self._load_from_module(tools_parser, module)

        # Load custom tools, if configured
        if extension_tools := get_custom_tool_path():
            extension_path = pathlib.Path(extension_tools)
            for _, name, _ in pkgutil.walk_packages([extension_tools]):
                full_name = f"{infuse_iot.tools.__name__}.{name}"
                full_path = str(extension_path / f"{name}.py")
                spec = importlib.util.spec_from_file_location(full_name, full_path)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)
                except Exception as _:
                    continue
                if hasattr(module, "SubCommand"):
                    self._load_from_module(tools_parser, module)


def main(argv=None):
    """Create the InfuseApp instance and let it run"""
    app = InfuseApp()
    try:
        app.run(argv or sys.argv[1:])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
