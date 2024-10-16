# Copyright (c) 2019, Nordic Semiconductor ASA
#
# Don't put anything else in here!
#
# This is the Python 3 version of option 3 in:
# https://packaging.python.org/guides/single-sourcing-package-version/#single-sourcing-the-version

import importlib.metadata

__version__ = importlib.metadata.version("infuse_iot")
