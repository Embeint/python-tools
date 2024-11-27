#!/usr/bin/env python3

from typing import Dict

from typing_extensions import Self


class Serializable:
    def to_json(self) -> Dict:
        """Convert class to json dictionary"""
        raise NotImplementedError

    @classmethod
    def from_json(cls, values: Dict) -> Self:
        """Reconstruct class from json dictionary"""
        raise NotImplementedError
