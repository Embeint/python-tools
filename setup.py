#!/usr/bin/env python3

import setuptools

VERSION = "0.0.1"
DESCRIPTION = "Infuse-IoT Platform python package"
LONG_DESCRIPTION = (
    "Meta-tool and helper libraries for working with the Infuse-IoT Platform"
)

setuptools.setup(
    name="infuse_iot",
    version=VERSION,
    author="Embeint Holdings Pty Ltd",
    author_email="support@embeint.com",
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    url="https://github.com/Embeint/python-tools",
    packages=setuptools.find_packages(where="src"),
    package_dir={"": "src"},
    include_package_data=True,
    install_requires=[
        "argcomplete",
        "colorama",
        "pylink-square",
        "pyserial",
        "tabulate",
    ],
    python_requires=">=3.10",
    entry_points={"console_scripts": ("infuse = infuse_iot.app.main:main",)},
    zip_safe=False,
)
