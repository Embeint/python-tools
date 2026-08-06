#!/usr/bin/env python3

import pytest

from infuse_iot.app.main import InfuseApp
from infuse_iot.generated import tasks
from infuse_iot.task_runner import (
    PeriodicityLockout,
    TaskSchedule,
    encode_schedule,
    format_description,
    format_schedule,
    format_schedule_python,
)


def _example_schedule() -> TaskSchedule:
    schedule = TaskSchedule()

    schedule.task_id = tasks.TaskBattery.ID
    schedule.validity = TaskSchedule.Validity.ACTIVE
    schedule.periodicity_type = TaskSchedule.Periodicity.LOCKOUT
    schedule.boot_lockout_minutes = 5
    schedule.timeout_s = 30

    schedule.battery_start.lower = 20
    schedule.battery_terminate.lower = 10
    schedule.periodicity.lockout.lockout_s = PeriodicityLockout.IGNORE_FIRST | 3600
    schedule.task_logging[0].loggers = tasks.TdfDataLogger.FLASH_ONBOARD
    schedule.task_logging[0].tdf_mask = tasks.TaskBattery.Logging.SOC
    schedule.task_args.battery.repeat_interval_ms = 1000

    return schedule


def test_format_schedule_python_reconstructs_schedule():
    schedule = _example_schedule()
    output = format_schedule_python(schedule)
    namespace = {
        "PeriodicityLockout": PeriodicityLockout,
        "TaskSchedule": TaskSchedule,
        "tasks": tasks,
    }

    exec(output, namespace)

    rebuilt = namespace["schedule"]
    assert isinstance(rebuilt, TaskSchedule)
    assert bytes(rebuilt) == bytes(schedule)
    assert "schedule.task_id = tasks.TaskBattery.ID" in output
    assert "schedule.task_logging[0].tdf_mask = tasks.TaskBattery.Logging.SOC" in output


def test_format_schedule_python_reconstructs_unknown_task_raw_args():
    data = bytearray(bytes(TaskSchedule()))
    data[0] = 250
    data[-1] = 0x5A
    schedule = TaskSchedule.from_buffer_copy(data)

    output = format_schedule_python(schedule)

    assert_python_output_rebuilds_schedule(output, schedule)
    assert "schedule.task_args.raw[16] = 0x5a" in output


def test_schedule_formatters_fault_unknown_periodicity_type():
    data = bytearray(bytes(TaskSchedule()))
    data[2] = 99
    data[12:18] = b"abcdef"
    schedule = TaskSchedule.from_buffer_copy(data)

    with pytest.raises(ValueError, match="unknown periodicity_type 99"):
        format_schedule(schedule)
    with pytest.raises(ValueError, match="unknown periodicity_type 99"):
        format_schedule_python(schedule)


def assert_python_output_rebuilds_schedule(output: str, schedule: TaskSchedule):
    namespace = {
        "PeriodicityLockout": PeriodicityLockout,
        "TaskSchedule": TaskSchedule,
        "tasks": tasks,
    }

    exec(output, namespace)

    rebuilt = namespace["schedule"]
    assert isinstance(rebuilt, TaskSchedule)
    assert bytes(rebuilt) == bytes(schedule)


def test_schedule_decode_defaults_to_description(capsys, monkeypatch):
    schedule = _example_schedule()
    monkeypatch.setattr("infuse_iot.app.main.get_custom_tool_path", lambda: None)

    InfuseApp().run(["schedule", "decode", encode_schedule(schedule)])

    output = capsys.readouterr().out
    assert "Task 2 (battery)." in output
    assert "Start conditions:" in output


def test_schedule_decode_python(capsys, monkeypatch):
    schedule = _example_schedule()
    monkeypatch.setattr("infuse_iot.app.main.get_custom_tool_path", lambda: None)

    InfuseApp().run(["schedule", "decode", "--python", encode_schedule(schedule)])

    output = capsys.readouterr().out
    assert "schedule = TaskSchedule()" in output
    assert "schedule.periodicity.lockout.lockout_s = PeriodicityLockout.IGNORE_FIRST | 3600" in output


def test_description_names_task_argument_bitfields():
    schedule = TaskSchedule()
    schedule.task_id = tasks.TaskGnss.ID
    schedule.validity = TaskSchedule.Validity.ALWAYS
    schedule.periodicity_type = TaskSchedule.Periodicity.FIXED
    schedule.periodicity.fixed.period_s = 60
    schedule.task_args.gnss.constellations = tasks.TaskGnss.Constellations.GPS | tasks.TaskGnss.Constellations.GALILEO
    schedule.task_args.gnss.flags = tasks.TaskGnss.Flags.RUN_TO_LOCATION_FIX | tasks.TaskGnss.Flags.PERFORMANCE_MODE

    output = format_description(schedule)

    assert "constellations: 0x05 (GPS, GALILEO)" in output
    assert "flags: 0x81 (RUN_TO_LOCATION_FIX, PERFORMANCE_MODE)" in output


def test_format_schedule_python_names_task_argument_bitfields():
    schedule = TaskSchedule()
    schedule.task_id = tasks.TaskGnss.ID
    schedule.validity = TaskSchedule.Validity.ALWAYS
    schedule.periodicity_type = TaskSchedule.Periodicity.FIXED
    schedule.periodicity.fixed.period_s = 60
    schedule.task_args.gnss.constellations = tasks.TaskGnss.Constellations.GPS | tasks.TaskGnss.Constellations.GALILEO
    schedule.task_args.gnss.flags = tasks.TaskGnss.Flags.RUN_TO_LOCATION_FIX | tasks.TaskGnss.Flags.PERFORMANCE_MODE

    output = format_schedule_python(schedule)

    assert_python_output_rebuilds_schedule(output, schedule)
    assert (
        "schedule.task_args.gnss.constellations = "
        "tasks.TaskGnss.Constellations.GPS | tasks.TaskGnss.Constellations.GALILEO"
    ) in output
    assert (
        "schedule.task_args.gnss.flags = "
        "tasks.TaskGnss.Flags.RUN_TO_LOCATION_FIX | tasks.TaskGnss.Flags.PERFORMANCE_MODE"
    ) in output
    assert "RUN_MASK" not in output


def test_description_names_nested_task_argument_bitfields():
    schedule = TaskSchedule()
    schedule.task_id = tasks.TaskNetworkScan.ID
    schedule.validity = TaskSchedule.Validity.ALWAYS
    schedule.periodicity_type = TaskSchedule.Periodicity.FIXED
    schedule.periodicity.fixed.period_s = 60
    schedule.task_args.network_scan.flags = (
        tasks.TaskNetworkScan.Flags.LTE_CELLS | tasks.TaskNetworkScan.Flags.SKIP_LTE_IF_WIFI_GOOD
    )
    schedule.task_args.network_scan.wifi.flags = (
        tasks.TaskNetworkScan.WifiArgs.Flags.INCLUDE_DUPLICATES | tasks.TaskNetworkScan.WifiArgs.Flags.SCAN_ACTIVE
    )

    output = format_description(schedule)

    assert "flags: 0x81 (LTE_CELLS, SKIP_LTE_IF_WIFI_GOOD)" in output
    assert "wifi.flags: 0x05 (INCLUDE_DUPLICATES, SCAN_ACTIVE)" in output


def test_format_schedule_python_names_nested_task_argument_bitfields():
    schedule = TaskSchedule()
    schedule.task_id = tasks.TaskNetworkScan.ID
    schedule.validity = TaskSchedule.Validity.ALWAYS
    schedule.periodicity_type = TaskSchedule.Periodicity.FIXED
    schedule.periodicity.fixed.period_s = 60
    schedule.task_args.network_scan.flags = (
        tasks.TaskNetworkScan.Flags.LTE_CELLS | tasks.TaskNetworkScan.Flags.SKIP_LTE_IF_WIFI_GOOD
    )
    schedule.task_args.network_scan.wifi.flags = (
        tasks.TaskNetworkScan.WifiArgs.Flags.INCLUDE_DUPLICATES | tasks.TaskNetworkScan.WifiArgs.Flags.SCAN_ACTIVE
    )

    output = format_schedule_python(schedule)

    assert_python_output_rebuilds_schedule(output, schedule)
    assert (
        "schedule.task_args.network_scan.flags = "
        "tasks.TaskNetworkScan.Flags.LTE_CELLS | tasks.TaskNetworkScan.Flags.SKIP_LTE_IF_WIFI_GOOD"
    ) in output
    assert (
        "schedule.task_args.network_scan.wifi.flags = "
        "tasks.TaskNetworkScan.WifiArgs.Flags.INCLUDE_DUPLICATES | tasks.TaskNetworkScan.WifiArgs.Flags.SCAN_ACTIVE"
    ) in output
