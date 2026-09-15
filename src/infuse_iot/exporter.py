#!/usr/bin/env python3

import os
from collections.abc import Callable
from io import TextIOWrapper
from pathlib import Path


class Exporter:
    _files: dict[Path, TextIOWrapper] = {}

    def __init__(self, save_path: Path):
        """Initialize the Exporter with a save path.
        :param save_path: The directory where exported files will be saved.
        """
        self.save_path = save_path

    def write_lines(self, filename: Path, lines: list[str], header: Callable[[], str] | None = None):
        """Write text to a tracked file, creating it (and adding an optional header) if necessary."""
        full_path = self.save_path / filename

        if full_path not in self._files:
            if full_path.exists():
                print(f"Appending to existing {full_path}")
                self._files[full_path] = open(full_path, "a", encoding="utf-8")  # noqa: SIM115
            else:
                print(f"Opening new {full_path}")
                self._files[full_path] = open(full_path, "w", encoding="utf-8")  # noqa: SIM115
                if header:
                    self._files[full_path].write(header() + os.linesep)
        for line in lines:
            self._files[full_path].write(line + os.linesep)
        self._files[full_path].flush()
