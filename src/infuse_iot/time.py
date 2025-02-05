#!/usr/bin/env python3

import datetime
import enum


class InfuseTimeSource:
    class base(enum.IntEnum):
        NONE = 0
        GNSS = 1
        NTP = 2
        RPC = 3
        INVALID = 4

    def __init__(self, value: int):
        self.recovered: bool = value & 0x80 != 0
        self.source = self.base(value & 0x7F)

    def __str__(self) -> str:
        postfix = " (recovered after reboot)" if self.recovered else ""
        base = self.source.name if self.source.name is not None else "Unknown"
        return base + postfix


class InfuseTime:
    GPS_UNIX_OFFSET = 315964800
    UNIX_LEAP_SECONDS = 18

    @classmethod
    def unix_time_from_gps_seconds(cls, gps_seconds: int) -> int:
        return gps_seconds + cls.GPS_UNIX_OFFSET - cls.UNIX_LEAP_SECONDS

    @classmethod
    def unix_time_from_epoch(cls, epoch_time: int) -> float:
        whole = epoch_time // 65536
        partial = epoch_time % 65536
        return cls.unix_time_from_gps_seconds(whole) + (partial / 65536)

    @classmethod
    def gps_seconds_from_unix(cls, unix_seconds: int) -> int:
        return unix_seconds - cls.GPS_UNIX_OFFSET + cls.UNIX_LEAP_SECONDS

    @classmethod
    def epoch_time_from_unix(cls, unix_time: float) -> int:
        whole = int(unix_time)
        frac = unix_time - whole
        return (cls.gps_seconds_from_unix(whole) * 65536) + int(frac * 65536)

    @classmethod
    def utc_time_string(cls, unix_time: float) -> str:
        # Trim timezone prefix and microseconds
        return str(datetime.datetime.fromtimestamp(unix_time, datetime.timezone.utc))[:-9]

    @classmethod
    def utc_time_string_log(cls, unix_time: float) -> str:
        obj = datetime.datetime.fromtimestamp(unix_time, datetime.timezone.utc)
        return obj.strftime("%Y-%m-%dT%H:%M:%S.%f")
