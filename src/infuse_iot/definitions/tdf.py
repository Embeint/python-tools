#!/usr/bin/env python3

import infuse_iot.generated.tdf_definitions as _tdf_base
from infuse_iot.util.internal import extension_load as _loader

if _extension_module := _loader("tdf_definitions"):
    id_type_mapping = {
        **_tdf_base.id_type_mapping,
        **_extension_module.id_type_mapping,
    }

    class readings(_tdf_base.readings, _extension_module.readings):  # type: ignore
        pass

    class structs(_tdf_base.structs, _extension_module.structs):  # type: ignore
        pass
else:
    id_type_mapping = _tdf_base.id_type_mapping
    readings = _tdf_base.readings  # type: ignore
    structs = _tdf_base.structs  # type: ignore


__all__ = [
    "id_type_mapping",
    "readings",
    "structs",
]
