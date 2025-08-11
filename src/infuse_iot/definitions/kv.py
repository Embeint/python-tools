#!/usr/bin/env python3

import infuse_iot.generated.kv_definitions as _kv_base
from infuse_iot.util.internal import extension_load as _loader

if extension_module := _loader("kv_definitions"):

    class slots(_kv_base.slots, extension_module.slots):  # type: ignore
        pass

    class structs(_kv_base.structs, extension_module.structs):  # type: ignore
        pass

else:
    slots = _kv_base.slots  # type: ignore
    structs = _kv_base.structs  # type: ignore

__all__ = [
    "slots",
    "structs",
]
