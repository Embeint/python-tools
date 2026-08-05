#!/usr/bin/env python3
"""ctypes mirror of ``struct task_schedule`` from ``schedule.h``.

This file depends on ``infuse_iot.generated.tasks`` for the task-specific
argument union.
"""

import ctypes

from infuse_iot.generated.tasks import TaskArguments


class TaskScheduleTdfLogging(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("loggers", ctypes.c_uint8),
        ("tdf_mask", ctypes.c_uint8),
    ]


class TaskScheduleStateConditions(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("metadata", ctypes.c_uint8),
        ("states", ctypes.c_uint8 * 4),
    ]


class BatteryStartThresholds(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("lower", ctypes.c_uint8),
        ("upper", ctypes.c_uint8),
    ]


class BatteryTerminateThresholds(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("lower", ctypes.c_uint8),
        ("upper", ctypes.c_uint8),
    ]


class PeriodicityPeriodic(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("period_s", ctypes.c_uint32),
    ]


class PeriodicityLockout(ctypes.LittleEndianStructure):
    IGNORE_FIRST = 1 << 31

    _pack_ = 1
    _fields_ = [
        ("lockout_s", ctypes.c_uint32),
    ]


class PeriodicityAfter(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("schedule_idx", ctypes.c_uint8),
        ("duration_s", ctypes.c_uint16),
    ]


class PeriodicityLockoutDynamicBattery(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ("lockout_min", ctypes.c_uint16),
        ("lockout_max", ctypes.c_uint16),
        ("battery_min", ctypes.c_uint8),
        ("battery_max", ctypes.c_uint8),
    ]


class PeriodicityArgs(ctypes.Union):
    _pack_ = 1
    _fields_ = [
        ("fixed", PeriodicityPeriodic),
        ("lockout", PeriodicityLockout),
        ("after", PeriodicityAfter),
        ("lockout_dynamic_battery", PeriodicityLockoutDynamicBattery),
    ]


class TaskSchedule(ctypes.LittleEndianStructure):
    LOCKED = 0x80

    class Validity:
        ALWAYS = 1
        ACTIVE = 2
        INACTIVE = 3
        PERMANENTLY_RUNS = 4
        END = 5
        MASK = 0x7F

    class Periodicity:
        FIXED = 1
        LOCKOUT = 2
        AFTER = 3
        LOCKOUT_DYNAMIC_BATTERY = 4

    EXPECTED_SIZE = 51

    _pack_ = 1
    _fields_ = [
        ("task_id", ctypes.c_uint8),
        ("validity", ctypes.c_uint8),
        ("periodicity_type", ctypes.c_uint8),
        ("boot_lockout_minutes", ctypes.c_uint8),
        ("timeout_s", ctypes.c_uint32),
        ("battery_start", BatteryStartThresholds),
        ("battery_terminate", BatteryTerminateThresholds),
        ("periodicity", PeriodicityArgs),
        ("states_start_timeout_2x_s", ctypes.c_uint16),
        ("states_start", TaskScheduleStateConditions),
        ("states_terminate", TaskScheduleStateConditions),
        ("task_logging", TaskScheduleTdfLogging * 2),
        ("task_args", TaskArguments),
    ]


def _field_offsets(struct_type):
    return {field_name: getattr(struct_type, field_name).offset for field_name, _field_type in struct_type._fields_}


if __name__ == "__main__":
    print(f"TaskSchedule size: {ctypes.sizeof(TaskSchedule)} bytes")
    print(f"Expected size: {TaskSchedule.EXPECTED_SIZE} bytes")
    print("Field offsets:")
    for name, offset in _field_offsets(TaskSchedule).items():
        print(f"  {name}: {offset}")
