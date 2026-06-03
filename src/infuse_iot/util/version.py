#!/usr/bin/env


class Version:
    def __init__(self, major: int, minor: int, revision: int, build_num: int):
        self.major = major
        self.minor = minor
        self.revision = revision
        self.build_num = build_num

    @classmethod
    def from_string(cls, version_string: str):
        "Convert 'x.y.z+rev' string to version instance"

        rev_split = version_string.split("+")
        if len(rev_split) != 2:
            raise ValueError(f"'{version_string}' is not a valid version string")
        ver_split = rev_split[0].split(".")
        if len(ver_split) != 3:
            raise ValueError(f"'{version_string}' is not a valid version string")
        return cls(int(ver_split[0]), int(ver_split[1]), int(ver_split[2]), int(rev_split[1], 16))

    def __str__(self):
        return f"{self.major}.{self.minor}.{self.revision}+{self.build_num:08x}"

    def __hash__(self):
        return self.major << 56 | self.minor << 48 | self.revision << 32 | self.build_num

    def __eq__(self, other):
        if not isinstance(other, Version):
            raise NotImplementedError
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.revision == other.revision
            and self.build_num == other.build_num
        )
