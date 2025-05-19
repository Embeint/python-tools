#!/usr/bin/env python3

import functools
import platform


@functools.cache
def is_wsl(v: str = platform.uname().release) -> bool:
    """
    Are we running under WSL?
    """
    return v.endswith("-Microsoft") or v.endswith("microsoft-standard-WSL2")
