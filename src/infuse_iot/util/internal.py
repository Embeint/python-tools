#!/usr/bin/env python

import importlib
import os
import pathlib
import types

import infuse_iot.credentials


def extension_load(name: str) -> None | types.ModuleType:
    if os.environ.get("_ARGCOMPLETE") == "1":
        # Skip expensive imports when running argcomplete
        return None

    defs_path = infuse_iot.credentials.get_custom_definitions_path()
    if defs_path is None:
        return None
    extensions_file = pathlib.Path(defs_path) / f"{name}.py"
    if not extensions_file.exists():
        return None

    try:
        # Import the extension file
        spec = importlib.util.spec_from_file_location(f"infuse_iot.extension.{name}", str(extensions_file))
        if spec is None or spec.loader is None:
            return None
        file_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(file_module)
    except Exception as _:
        return None

    # Return the loaded file
    return file_module
