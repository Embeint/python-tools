#!/usr/bin/env python3


from typing_extensions import Self


class Serializable:
    def to_json(self) -> dict:
        """Convert class to json dictionary"""
        raise NotImplementedError

    @classmethod
    def from_json(cls, values: dict) -> Self:
        """Reconstruct class from json dictionary"""
        raise NotImplementedError
