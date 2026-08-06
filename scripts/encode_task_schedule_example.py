#!/usr/bin/env python3
"""Example: build a task schedule in Python and print its encoded bytes."""

import argparse
import base64

from infuse_iot.generated import tasks
from infuse_iot.task_runner.schedule import TaskSchedule


def example_schedule() -> TaskSchedule:
    schedule = TaskSchedule()
    schedule.task_id = tasks.TaskGnss.ID
    schedule.validity = TaskSchedule.Validity.ACTIVE
    schedule.states_start.states[0] = 9
    schedule.states_terminate.metadata = 1
    schedule.states_terminate.states[0] = 9
    schedule.task_logging[0].loggers = tasks.TdfDataLogger.BT_PERIPH
    schedule.task_logging[0].tdf_mask = tasks.TaskGnss.Logging.PVT
    schedule.task_args.gnss.constellations = (
        tasks.TaskGnss.Constellations.GPS | tasks.TaskGnss.Constellations.GALILEO | tasks.TaskGnss.Constellations.QZSS
    )
    schedule.task_args.gnss.accuracy_m = 100
    schedule.task_args.gnss.position_dop = 250
    schedule.task_args.gnss.dynamic_model = 4

    return schedule


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--encoding",
        choices=("hex", "base64"),
        default="hex",
        help="output encoding",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = bytes(example_schedule())

    if args.encoding == "base64":
        print(base64.b64encode(payload).decode("ascii"))
    else:
        print(payload.hex())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
