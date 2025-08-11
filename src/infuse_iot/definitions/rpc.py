#!/usr/bin/env python3

from infuse_iot.generated.rpc_definitions import *  # noqa: F403
from infuse_iot.util.internal import extension_load as _loader

if _extension_module := _loader("rpc_definitions"):
    _globals = globals()
    for _name in _extension_module.__all__:
        _globals[_name] = getattr(_extension_module, _name)
