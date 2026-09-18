#!/usr/bin/env python3

"""Example out-of-tree tool registry."""

from infuse_iot.tools.registry import RpcWrapperSpec, ToolSpec


def custom_device_id(value: str) -> int | None:
    if not value.startswith("custom-"):
        return None
    return int(value.removeprefix("custom-"), 16)


def custom_device_id_reverse(value: int) -> str | None:
    if not 0 <= value <= 0xFFFFFFFF:
        return None
    return f"custom-{value:08x}"


DEVICE_ID_CONVERTERS = (custom_device_id,)
DEVICE_ID_REVERSE_CONVERTERS = (custom_device_id_reverse,)

TOOLS = (
    ToolSpec(
        name="custom_tool",
        help="Test out-of-tree tool",
        description="Test out-of-tree tool",
        module="custom_tool",
    ),
)

RPC_WRAPPERS = (
    RpcWrapperSpec(
        name="custom_rpc",
        module="custom_rpc",
    ),
)
