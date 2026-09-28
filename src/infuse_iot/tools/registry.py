#!/usr/bin/env python3

"""Tool registry definitions."""

import importlib.util
import pathlib
import types
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    """Lightweight command metadata for parser construction."""

    name: str
    help: str
    description: str
    module: str


@dataclass(frozen=True)
class RpcWrapperSpec:
    """Lightweight RPC wrapper metadata for parser construction."""

    name: str
    module: str


def _load_registry_module(path: pathlib.Path) -> types.ModuleType:
    registry_path = path / "registry.py"
    if not registry_path.exists():
        raise FileNotFoundError(f"Custom tools registry does not exist: {registry_path}")

    spec = importlib.util.spec_from_file_location("infuse_iot_custom_tools.registry", registry_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Failed to load custom tools registry: {registry_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_extension_tools(path: str | pathlib.Path) -> tuple[ToolSpec, ...]:
    """Load and validate ToolSpec entries from an extension tool directory."""
    extension_path = pathlib.Path(path)
    module = _load_registry_module(extension_path)
    _register_device_id_converters(module)

    if not hasattr(module, "TOOLS"):
        if hasattr(module, "RPC_WRAPPERS"):
            return ()
        raise ValueError(f"Custom tools registry {extension_path / 'registry.py'} does not define TOOLS")

    tools = module.TOOLS
    if not isinstance(tools, (list, tuple)):
        raise TypeError("Custom tools registry TOOLS must be a list or tuple of ToolSpec entries")

    names = set()
    validated_tools = []
    for tool in tools:
        if not isinstance(tool, ToolSpec):
            raise TypeError("Custom tools registry TOOLS must contain only ToolSpec entries")
        if tool.name in names:
            raise ValueError(f"Duplicate custom tool name: {tool.name}")
        names.add(tool.name)
        if not tool.name:
            raise ValueError("Custom tool name cannot be empty")
        if not tool.help:
            raise ValueError(f"Custom tool {tool.name} help cannot be empty")
        if not tool.description:
            raise ValueError(f"Custom tool {tool.name} description cannot be empty")
        if not tool.module:
            raise ValueError(f"Custom tool {tool.name} module cannot be empty")

        module_path = extension_path / f"{tool.module.replace('.', '/')}.py"
        if not module_path.exists():
            raise FileNotFoundError(f"Custom tool module does not exist: {module_path}")
        validated_tools.append(tool)

    return tuple(validated_tools)


def load_extension_rpc_wrappers(path: str | pathlib.Path) -> tuple[RpcWrapperSpec, ...]:
    """Load and validate RpcWrapperSpec entries from an extension tool directory."""
    extension_path = pathlib.Path(path)
    module = _load_registry_module(extension_path)

    wrappers = getattr(module, "RPC_WRAPPERS", ())
    if not isinstance(wrappers, (list, tuple)):
        raise TypeError("Custom tools registry RPC_WRAPPERS must be a list or tuple of RpcWrapperSpec entries")

    names = set()
    validated_wrappers = []
    for wrapper in wrappers:
        if not isinstance(wrapper, RpcWrapperSpec):
            raise TypeError("Custom tools registry RPC_WRAPPERS must contain only RpcWrapperSpec entries")
        if wrapper.name in names:
            raise ValueError(f"Duplicate custom RPC wrapper name: {wrapper.name}")
        names.add(wrapper.name)
        if not wrapper.name:
            raise ValueError("Custom RPC wrapper name cannot be empty")
        if not wrapper.module:
            raise ValueError(f"Custom RPC wrapper {wrapper.name} module cannot be empty")

        module_path = extension_path / f"{wrapper.module.replace('.', '/')}.py"
        if not module_path.exists():
            raise FileNotFoundError(f"Custom RPC wrapper module does not exist: {module_path}")
        validated_wrappers.append(wrapper)

    return tuple(validated_wrappers)


def import_extension_rpc_wrapper(extension_path: str | pathlib.Path, wrapper: RpcWrapperSpec) -> type:
    """Import a custom RPC wrapper class from an extension tool directory."""
    import importlib.util

    extension_path = pathlib.Path(extension_path)
    module_path = extension_path / f"{wrapper.module.replace('.', '/')}.py"
    module_name = f"infuse_iot_custom_tools.{wrapper.module}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to import custom RPC wrapper module: {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, wrapper.name)


def _register_device_id_converters(module: types.ModuleType) -> None:
    converters = getattr(module, "DEVICE_ID_CONVERTERS", ())
    if not isinstance(converters, (list, tuple)):
        raise TypeError("Custom tools registry DEVICE_ID_CONVERTERS must be a list or tuple of callables")

    reverse_converters = getattr(module, "DEVICE_ID_REVERSE_CONVERTERS", ())
    if not isinstance(reverse_converters, (list, tuple)):
        raise TypeError("Custom tools registry DEVICE_ID_REVERSE_CONVERTERS must be a list or tuple of callables")

    from infuse_iot.util.argparse import (
        register_infuse_device_id_fallback,
        register_infuse_device_id_reverse_fallback,
    )

    for converter in converters:
        if not callable(converter):
            raise TypeError("Custom tools registry DEVICE_ID_CONVERTERS must contain only callables")
        register_infuse_device_id_fallback(converter)

    for converter in reverse_converters:
        if not callable(converter):
            raise TypeError("Custom tools registry DEVICE_ID_REVERSE_CONVERTERS must contain only callables")
        register_infuse_device_id_reverse_fallback(converter)


TOOLS = (
    ToolSpec(
        name="annotate_events",
        help="Annotate events on Infuse Tags",
        description="Save labelled event annotations live on Infuse Tags",
        module="infuse_iot.tools.annotate_events",
    ),
    ToolSpec(
        name="audio_record",
        help="Record audio data to a file from TDF",
        description="Record audio data to a file from TDF",
        module="infuse_iot.tools.audio_record",
    ),
    ToolSpec(
        name="auto_activate",
        help="Automatically activate/deactivate observed devices",
        description="Automatically activate/deactivate observed devices",
        module="infuse_iot.tools.auto_activate",
    ),
    ToolSpec(
        name="bt_log",
        help="Connect to remote Bluetooth device serial logs",
        description="Connect to remote Bluetooth device serial logs",
        module="infuse_iot.tools.bt_log",
    ),
    ToolSpec(
        name="cloud",
        help="Infuse-IoT cloud interaction",
        description="Infuse-IoT cloud interaction",
        module="infuse_iot.tools.cloud",
    ),
    ToolSpec(
        name="credentials",
        help="Manage Infuse-IoT credentials",
        description="Manage Infuse-IoT credentials",
        module="infuse_iot.tools.credentials",
    ),
    ToolSpec(
        name="csv_annotate",
        help="Annotate CSV data",
        description="Annotate CSV data",
        module="infuse_iot.tools.csv_annotate",
    ),
    ToolSpec(
        name="csv_plot",
        help="Plot CSV data",
        description="Plot CSV data",
        module="infuse_iot.tools.csv_plot",
    ),
    ToolSpec(
        name="data_logger_sync",
        help="Synchronise data logger state from remote devices",
        description="Synchronise data logger state from remote devices",
        module="infuse_iot.tools.data_logger_sync",
    ),
    ToolSpec(
        name="dataset",
        help="Dataset helper tools",
        description="Dataset helper tools",
        module="infuse_iot.tools.dataset",
    ),
    ToolSpec(
        name="gateway",
        help="Connect to a local gateway device",
        description="Connect to a gateway device over serial and route commands to Bluetooth devices",
        module="infuse_iot.tools.gateway",
    ),
    ToolSpec(
        name="localhost",
        help="Run a local server for TDF viewing",
        description="Run a local server for TDF viewing",
        module="infuse_iot.tools.localhost",
    ),
    ToolSpec(
        name="native_bt",
        help="Native Bluetooth gateway",
        description="Use the local Bluetooth adapter for Bluetooth interaction",
        module="infuse_iot.tools.native_bt",
    ),
    ToolSpec(
        name="ota_upgrade",
        help="Automatically OTA upgrade observed devices",
        description="Automatically OTA upgrade observed devices",
        module="infuse_iot.tools.ota_upgrade",
    ),
    ToolSpec(
        name="provision",
        help="Provision device on Infuse Cloud",
        description="Provision device on Infuse Cloud",
        module="infuse_iot.tools.provision",
    ),
    ToolSpec(
        name="profile",
        help="Manage Infuse-IoT profiles",
        description="Manage Infuse-IoT profiles",
        module="infuse_iot.tools.profile",
    ),
    ToolSpec(
        name="rpc",
        help="Run remote procedure calls on devices",
        description="Run remote procedure calls on devices",
        module="infuse_iot.tools.rpc",
    ),
    ToolSpec(
        name="rpc_cloud",
        help="Manage remote procedure calls through Infuse-IoT cloud",
        description="Manage remote procedure calls through Infuse-IoT cloud",
        module="infuse_iot.tools.rpc_cloud",
    ),
    ToolSpec(
        name="schedule",
        help="Task schedule utilities",
        description="Task schedule utilities",
        module="infuse_iot.tools.schedule",
    ),
    ToolSpec(
        name="serial_throughput",
        help="Test serial throughput to local gateway",
        description="Test serial throughput to local gateway",
        module="infuse_iot.tools.serial_throughput",
    ),
    ToolSpec(
        name="tdf_csv",
        help="Save received TDFs in CSV files",
        description="Save received TDFs in CSV files",
        module="infuse_iot.tools.tdf_csv",
    ),
    ToolSpec(
        name="tdf_list",
        help="Display received TDFs in a list",
        description="Display received TDFs in a list",
        module="infuse_iot.tools.tdf_list",
    ),
)
