"""Human-readable descriptions of task schedule behavior."""

from infuse_iot.generated import tasks
from infuse_iot.task_runner.schedule import PeriodicityLockout, TaskSchedule

TASK_ID_NAMES = {value: name for name, value in tasks.TaskArguments.TASK_IDS.items()}


def task_class(task_id: int):
    for cls_name, cls_value in vars(tasks).items():
        if not cls_name.startswith("Task") or not isinstance(cls_value, type):
            continue
        for attr_name in ("ID", "ALT1_ID", "ALT2_ID"):
            if getattr(cls_value, attr_name, None) == task_id:
                return cls_value
    return None


def task_argument_field(task_id: int) -> str | None:
    return tasks.TaskArguments.TASK_ARG_FIELDS.get(task_id)


def task_logging_class(task_id: int):
    return tasks.TaskArguments.TASK_LOGGING_CLASSES.get(task_id)


class InfuseState:
    REBOOTING = 1
    APPLICATION_ACTIVE = 2
    TIME_KNOWN = 3
    DEVICE_STATIONARY = 4
    HIGH_PRIORITY_UPLINK = 5
    DEVICE_STARTED_MOVING = 6
    DEVICE_STOPPED_MOVING = 7
    LED_SUPPRESS = 8
    DEVICE_MOVING = 9
    APP_START = 128
    END = 255

    NAMES = {
        REBOOTING: "REBOOTING",
        APPLICATION_ACTIVE: "APPLICATION_ACTIVE",
        TIME_KNOWN: "TIME_KNOWN",
        DEVICE_STATIONARY: "DEVICE_STATIONARY",
        HIGH_PRIORITY_UPLINK: "HIGH_PRIORITY_UPLINK",
        DEVICE_STARTED_MOVING: "DEVICE_STARTED_MOVING",
        DEVICE_STOPPED_MOVING: "DEVICE_STOPPED_MOVING",
        LED_SUPPRESS: "LED_SUPPRESS",
        DEVICE_MOVING: "DEVICE_MOVING",
        APP_START: "INFUSE_STATES_APP_START",
        END: "INFUSE_STATES_END",
    }


def state_name(state_id: int) -> str:
    if state_id in InfuseState.NAMES:
        return InfuseState.NAMES[state_id]
    if InfuseState.APP_START <= state_id < InfuseState.END:
        return f"application_state_{state_id}"
    return "unknown"


def state_condition_phrase(states, empty_default: bool) -> str:
    state_ids = list(states.states)
    if state_ids[0] == 0:
        return "no state condition is configured" if empty_default else "no stop state is configured"

    terms = []
    for idx, state_id in enumerate(state_ids):
        if state_id == 0:
            break
        inverted = bool(states.metadata & (1 << idx))
        operator = "or" if states.metadata & (1 << (idx + 4)) else "and"
        phrase = f"{state_name(state_id)} is {'not set' if inverted else 'set'}"
        terms.append((operator, phrase))

    if not terms:
        return "no state condition is configured" if empty_default else "no stop state is configured"

    text = terms[0][1]
    for operator, phrase in terms[1:]:
        text = f"[{text} {operator} {phrase}]"
    return text


def periodicity_start_phrase(schedule: TaskSchedule) -> str | None:
    if schedule.periodicity_type == 0:
        return None
    if schedule.periodicity_type == TaskSchedule.Periodicity.FIXED:
        return f"the epoch time is on a {schedule.periodicity.fixed.period_s} second boundary"
    if schedule.periodicity_type == TaskSchedule.Periodicity.LOCKOUT:
        lockout = schedule.periodicity.lockout.lockout_s
        ignore_first = bool(lockout & PeriodicityLockout.IGNORE_FIRST)
        lockout &= ~PeriodicityLockout.IGNORE_FIRST
        phrase = f"at least {lockout} seconds have elapsed since the task last started"
        if ignore_first:
            phrase += ", except the first run may start immediately after boot"
        else:
            phrase += " or the application booted"
        return phrase
    if schedule.periodicity_type == TaskSchedule.Periodicity.AFTER:
        after = schedule.periodicity.after
        return f"schedule index {after.schedule_idx} terminated exactly {after.duration_s} seconds ago"
    if schedule.periodicity_type == TaskSchedule.Periodicity.LOCKOUT_DYNAMIC_BATTERY:
        ldb = schedule.periodicity.lockout_dynamic_battery
        return (
            "the dynamic battery lockout has elapsed "
            f"({ldb.lockout_min}s at <= {ldb.battery_min}% SoC, "
            f"{ldb.lockout_max}s at >= {ldb.battery_max}% SoC, linearly scaled between)"
        )
    return f"the periodicity condition for unknown type {schedule.periodicity_type} passes"


def start_battery_phrase(schedule: TaskSchedule) -> str | None:
    lower = schedule.battery_start.lower
    upper = schedule.battery_start.upper
    parts = []
    if lower:
        parts.append(f"SoC is at least {lower}%")
    if upper:
        parts.append(f"SoC is at most {upper}%")
    if not parts:
        return None
    return " and ".join(parts)


def terminate_battery_phrases(schedule: TaskSchedule) -> list[str]:
    parts = []
    if schedule.battery_terminate.lower:
        parts.append(f"SoC falls to {schedule.battery_terminate.lower}% or below")
    if schedule.battery_terminate.upper:
        parts.append(f"SoC rises to {schedule.battery_terminate.upper}% or above")
    return parts


def start_state_phrase(schedule: TaskSchedule) -> str | None:
    if list(schedule.states_start.states)[0] == 0:
        return None

    phrase = state_condition_phrase(schedule.states_start, True)
    if schedule.states_start_timeout_2x_s:
        timeout = 2 * schedule.states_start_timeout_2x_s
        return f"{phrase}, or {timeout} seconds have elapsed since last start"
    return phrase


def stop_state_phrase(schedule: TaskSchedule) -> str | None:
    if list(schedule.states_terminate.states)[0] == 0:
        return None
    return state_condition_phrase(schedule.states_terminate, False)


def start_condition_phrases(schedule: TaskSchedule) -> list[str]:
    validity = schedule.validity & TaskSchedule.Validity.MASK
    conditions = []

    if validity == TaskSchedule.Validity.ACTIVE:
        conditions.append("APPLICATION_ACTIVE is set")
    elif validity == TaskSchedule.Validity.INACTIVE:
        conditions.append("APPLICATION_ACTIVE is cleared")

    if schedule.boot_lockout_minutes:
        conditions.append(f"uptime is at least {schedule.boot_lockout_minutes} minute(s)")

    periodicity_start = periodicity_start_phrase(schedule)
    if periodicity_start:
        conditions.append(periodicity_start)

    battery_start = start_battery_phrase(schedule)
    if battery_start:
        conditions.append(battery_start)

    state_start = start_state_phrase(schedule)
    if state_start:
        conditions.append(state_start)

    return conditions


def stop_condition_phrases(schedule: TaskSchedule) -> list[str]:
    validity = schedule.validity & TaskSchedule.Validity.MASK
    conditions = []

    if validity == TaskSchedule.Validity.ACTIVE:
        conditions.append("APPLICATION_ACTIVE is cleared")
    elif validity == TaskSchedule.Validity.INACTIVE:
        conditions.append("APPLICATION_ACTIVE is set")

    if schedule.timeout_s:
        conditions.append(f"the task has run for at least {schedule.timeout_s} seconds")

    conditions.extend(terminate_battery_phrases(schedule))

    state_stop = stop_state_phrase(schedule)
    if state_stop:
        conditions.append(state_stop)

    return conditions


def is_set_value(value) -> bool:
    if hasattr(value, "_fields_"):
        return any(is_set_value(getattr(value, name)) for name, _field_type in value._fields_)
    return value != 0


def option_mask_names(mask: int, option_class) -> str | None:
    if option_class is None:
        return None

    names = []
    known_mask = 0
    for name, value in vars(option_class).items():
        if not name.isupper() or not isinstance(value, int) or value == 0:
            continue
        if value & (value - 1):
            continue
        known_mask |= value
        if mask & value:
            names.append(name)

    unknown_mask = mask & ~known_mask
    if unknown_mask:
        names.append(f"unknown_bits=0x{unknown_mask:02x}")

    if not names:
        return None
    return ", ".join(names)


def task_argument_option_class(field_name: str, field_type, root_task_class):
    if field_name == "flags":
        class_names = ("Flags",)
    elif field_name == "loggers":
        return tasks.TdfDataLogger
    elif field_name in ("constellations", "tdfs"):
        class_names = ("".join(part.capitalize() for part in field_name.split("_")),)
    else:
        return None

    for class_name in class_names:
        option_class = getattr(field_type, class_name, None)
        if option_class is not None:
            return option_class
        option_class = getattr(root_task_class, class_name, None)
        if option_class is not None:
            return option_class
    return None


def task_argument_value_line(field_name: str, field_value, field_owner_type, root_task_class) -> str:
    option_class = task_argument_option_class(
        field_name.rsplit(".", maxsplit=1)[-1],
        field_owner_type,
        root_task_class,
    )
    if option_class is None:
        return f"{field_name}: {field_value}"

    names = option_mask_names(field_value, option_class)
    suffix = f" ({names})" if names else ""
    return f"{field_name}: 0x{field_value:02x}{suffix}"


def task_argument_lines(value, root_task_class, prefix: str = "") -> list[str]:
    lines = []
    for name, _field_type in getattr(value, "_fields_", []):
        field_value = getattr(value, name)
        field_name = f"{prefix}.{name}" if prefix else name
        if hasattr(field_value, "_fields_"):
            lines.extend(task_argument_lines(field_value, root_task_class, field_name))
        elif is_set_value(field_value):
            lines.append(task_argument_value_line(field_name, field_value, type(value), root_task_class))
    return lines


def schedule_task_argument_lines(schedule: TaskSchedule) -> list[str]:
    arg_field = task_argument_field(schedule.task_id)
    root_task_class = task_class(schedule.task_id)
    if arg_field is None or root_task_class is None:
        return ["unknown task_id"]
    return task_argument_lines(getattr(schedule.task_args, arg_field), root_task_class)


def schedule_logging_lines(schedule: TaskSchedule) -> list[str]:
    logging_class = task_logging_class(schedule.task_id)
    lines = []

    for idx, logging_config in enumerate(schedule.task_logging):
        if not logging_config.loggers and not logging_config.tdf_mask:
            continue

        logger_names = option_mask_names(logging_config.loggers, tasks.TdfDataLogger)
        logger_suffix = f" ({logger_names})" if logger_names else ""
        lines.append(f"[{idx}].loggers: 0x{logging_config.loggers:02x}{logger_suffix}")

        mask_names = option_mask_names(logging_config.tdf_mask, logging_class)
        mask_suffix = f" ({mask_names})" if mask_names else ""
        lines.append(f"[{idx}].tdf_mask: 0x{logging_config.tdf_mask:02x}{mask_suffix}")

    return lines


def append_logging_configuration(lines: list[str], schedule: TaskSchedule) -> None:
    logging_values = schedule_logging_lines(schedule)
    lines.extend(["", "Logging configuration:"])
    if logging_values:
        for value in logging_values:
            lines.append(f"  - {value}")
    else:
        lines.append("  No task logging is configured.")


def append_task_arguments(lines: list[str], schedule: TaskSchedule) -> None:
    task_argument_values = schedule_task_argument_lines(schedule)
    lines.extend(["", "Task arguments:"])
    if task_argument_values:
        for value in task_argument_values:
            lines.append(f"  - {value}")
    else:
        lines.append("  No task-specific arguments are set.")


def format_description(schedule: TaskSchedule) -> str:
    task_name = TASK_ID_NAMES.get(schedule.task_id, "unknown")
    locked = " locked against KV-store updates" if schedule.validity & TaskSchedule.LOCKED else ""
    validity = schedule.validity & TaskSchedule.Validity.MASK
    lines = [
        f"Task {schedule.task_id} ({task_name}){locked}.",
        "",
    ]

    if validity == 0 or validity >= TaskSchedule.Validity.END:
        lines.append(
            f"Schedule is invalid: validity value 0x{schedule.validity:02x} "
            f"masks to {validity}, outside 1..{TaskSchedule.Validity.END - 1}."
        )
        append_logging_configuration(lines, schedule)
        append_task_arguments(lines, schedule)
        return "\n".join(lines)

    lines.append("Start conditions:")

    if validity == TaskSchedule.Validity.PERMANENTLY_RUNS:
        lines.append("  The task starts or restarts whenever it is not running.")
        lines.extend(
            [
                "",
                "Stop conditions:",
                "  Normal stop conditions are not evaluated for permanently-running tasks.",
            ]
        )
        append_logging_configuration(lines, schedule)
        append_task_arguments(lines, schedule)
        return "\n".join(lines)

    start_conditions = start_condition_phrases(schedule)
    if start_conditions:
        lines.append("  All of these must be true:")
    else:
        lines.append("  No schedule start conditions are configured.")
    for condition in start_conditions:
        lines.append(f"  - {condition}.")

    stop_conditions = stop_condition_phrases(schedule)
    lines.extend(["", "Stop conditions:"])
    if stop_conditions:
        lines.append("  Any of these will request the task to stop:")
    else:
        lines.append("  No schedule stop conditions are configured.")
    for condition in stop_conditions:
        lines.append(f"  - {condition}.")

    append_logging_configuration(lines, schedule)
    append_task_arguments(lines, schedule)
    return "\n".join(lines)
