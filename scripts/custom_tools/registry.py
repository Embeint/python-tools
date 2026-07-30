#!/usr/bin/env python3

"""Example out-of-tree tool registry."""

from infuse_iot.tools.registry import ToolSpec

TOOLS = (
    ToolSpec(
        name="custom_tool",
        help="Test out-of-tree tool",
        description="Test out-of-tree tool",
        module="custom_tool",
    ),
)
