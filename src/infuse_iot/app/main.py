#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

"""Infuse-IoT SDK meta-tool (infuse) main module"""

__author__ = "Jordan Yates"
__copyright__ = "Copyright 2024, Embeint Holdings Pty Ltd"

import argparse
import importlib
import importlib.util
import os
import pathlib
import sys
import types
from dataclasses import dataclass
from typing import Any

import argcomplete
from argcomplete.lexers import split_line

from infuse_iot.credentials import get_custom_tool_path
from infuse_iot.tools.registry import TOOLS, ToolSpec, load_extension_tools
from infuse_iot.version import __version__


@dataclass(frozen=True)
class RegisteredTool:
    spec: ToolSpec
    extension_path: pathlib.Path | None = None


class InfuseApp:
    """The infuse 'application' object"""

    def __init__(self):
        self.args = None
        self.parser = argparse.ArgumentParser("infuse")
        self.parser.add_argument("--version", action="version", version=f"{__version__}")
        self._tools: dict[str, RegisteredTool] = {}
        self._tool_parsers = {}
        self._loaded_tools = set()
        # Load tools
        self._load_tools(self.parser)

    def run(self, argv):
        """Run the chosen subtool handler"""
        argv = argv or sys.argv[1:]
        self._load_selected_tool(argv)
        self._load_selected_completion_tool()
        # Handle CLI tab completion
        argcomplete.autocomplete(self.parser)
        self.args = self.parser.parse_args(argv)

        tool = self.args.tool_class(self.args)
        tool.run()

    def _load_from_module(
        self,
        parent_parser: argparse._SubParsersAction,
        module: types.ModuleType,
        parser: argparse.ArgumentParser | None = None,
    ):
        tool_cls: Any = module.SubCommand
        if parser is None:
            parser = parent_parser.add_parser(
                tool_cls.NAME,
                help=tool_cls.HELP,
                description=tool_cls.DESCRIPTION,
                formatter_class=argparse.RawDescriptionHelpFormatter,
            )
        parser.set_defaults(tool_class=tool_cls)
        tool_cls.add_parser(parser)

    def _load_selected_tool(self, argv: list[str]):
        if not argv:
            return

        if argv[0] not in self._tools or argv[0] in self._loaded_tools:
            return

        tool = self._tools[argv[0]]
        module = self._import_tool_module(tool)
        self._load_from_module(self._tools_parser, module, self._tool_parsers[tool.spec.name])
        self._loaded_tools.add(tool.spec.name)

    def _import_tool_module(self, tool: RegisteredTool) -> types.ModuleType:
        if tool.extension_path is None:
            return importlib.import_module(tool.spec.module)

        module_path = tool.extension_path / f"{tool.spec.module.replace('.', '/')}.py"
        module_name = f"infuse_iot_custom_tools.{tool.spec.module}"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to import custom tool module: {module_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _load_selected_completion_tool(self):
        if "_ARGCOMPLETE" not in os.environ:
            return

        comp_line = os.environ["COMP_LINE"]
        comp_point = int(os.environ["COMP_POINT"])
        _, _, _, comp_words, _ = split_line(comp_line, comp_point)

        # Match argcomplete's own executable/module offset handling.
        start = int(os.environ["_ARGCOMPLETE"]) - 1
        parser_words = comp_words[start:]
        if len(parser_words) > 1:
            self._load_selected_tool(parser_words[1:])

    def _load_tools(self, parser: argparse.ArgumentParser):
        self._tools_parser = parser.add_subparsers(title="commands", metavar="<command>", required=True)

        # Register local tools without importing their implementation modules.
        for tool in TOOLS:
            self._register_tool(tool)

        # Load custom tools, if configured
        if extension_tools := get_custom_tool_path():
            extension_path = pathlib.Path(extension_tools)
            for tool in load_extension_tools(extension_path):
                self._register_tool(tool, extension_path)

    def _register_tool(self, tool: ToolSpec, extension_path: pathlib.Path | None = None):
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")

        self._tools[tool.name] = RegisteredTool(tool, extension_path)
        self._tool_parsers[tool.name] = self._tools_parser.add_parser(
            tool.name,
            help=tool.help,
            description=tool.description,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )


def main(argv=None):
    """Create the InfuseApp instance and let it run"""
    app = InfuseApp()
    try:
        app.run(argv or sys.argv[1:])
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
