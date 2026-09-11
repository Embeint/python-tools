#!/usr/bin/env python3

"""Example out-of-tree tool registry."""

from infuse_iot.tools.registry import ToolSpec


def custom_device_id(value: str) -> int | None:
    if not value.startswith("custom-"):
        return None
    return int(value.removeprefix("custom-"), 16)


DEVICE_ID_CONVERTERS = (custom_device_id,)

TOOLS = (
    ToolSpec(
        name="custom_tool",
        help="Test out-of-tree tool",
        description="Test out-of-tree tool",
        module="custom_tool",
    ),
)
