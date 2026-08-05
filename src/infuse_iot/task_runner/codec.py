"""Encoding, decoding, and raw formatting helpers for task schedules."""

import base64
import binascii
import ctypes
import re

from infuse_iot.generated import tasks
from infuse_iot.task_runner.describe import state_name, task_argument_option_class, task_class
from infuse_iot.task_runner.schedule import PeriodicityLockout, TaskSchedule

VALIDITY_NAMES = {
    TaskSchedule.Validity.ALWAYS: "TASK_VALID_ALWAYS",
    TaskSchedule.Validity.ACTIVE: "TASK_VALID_ACTIVE",
    TaskSchedule.Validity.INACTIVE: "TASK_VALID_INACTIVE",
    TaskSchedule.Validity.PERMANENTLY_RUNS: "TASK_VALID_PERMANENTLY_RUNS",
}

PERIODICITY_NAMES = {
    TaskSchedule.Periodicity.FIXED: "TASK_PERIODICITY_FIXED",
    TaskSchedule.Periodicity.LOCKOUT: "TASK_PERIODICITY_LOCKOUT",
    TaskSchedule.Periodicity.AFTER: "TASK_PERIODICITY_AFTER",
    TaskSchedule.Periodicity.LOCKOUT_DYNAMIC_BATTERY: "TASK_PERIODICITY_LOCKOUT_DYNAMIC_BATTERY",
}

TASK_ID_NAMES = {value: name for name, value in tasks.TaskArguments.TASK_IDS.items()}


def _task_id_expression(task_id: int) -> str:
    for cls_name, cls_value in vars(tasks).items():
        if not cls_name.startswith("Task") or not isinstance(cls_value, type):
            continue
        for attr_name in ("ID", "ALT1_ID", "ALT2_ID"):
            if getattr(cls_value, attr_name, None) == task_id:
                return f"tasks.{cls_name}.{attr_name}"
    return str(task_id)


def _task_class_name(task_id: int) -> str | None:
    task_expr = _task_id_expression(task_id)
    if task_expr.startswith("tasks.") and "." in task_expr.removeprefix("tasks."):
        return task_expr.split(".")[1]
    return None


def _mask_expression(mask: int, option_class, class_expression: str) -> str:
    if mask == 0 or option_class is None:
        return f"0x{mask:02x}"

    remaining = mask
    parts = []
    for name, value in vars(option_class).items():
        if not name.isupper() or not isinstance(value, int) or value == 0:
            continue
        if value & (value - 1):
            continue
        if mask & value == value:
            parts.append(f"{class_expression}.{name}")
            remaining &= ~value

    if remaining:
        parts.append(f"0x{remaining:02x}")
    return " | ".join(parts) if parts else f"0x{mask:02x}"


def _validity_expression(validity: int) -> str:
    locked = validity & TaskSchedule.LOCKED
    value = validity & TaskSchedule.Validity.MASK
    names = {
        TaskSchedule.Validity.ALWAYS: "TaskSchedule.Validity.ALWAYS",
        TaskSchedule.Validity.ACTIVE: "TaskSchedule.Validity.ACTIVE",
        TaskSchedule.Validity.INACTIVE: "TaskSchedule.Validity.INACTIVE",
        TaskSchedule.Validity.PERMANENTLY_RUNS: "TaskSchedule.Validity.PERMANENTLY_RUNS",
    }
    expr = names.get(value, str(value))
    if locked:
        expr = f"TaskSchedule.LOCKED | {expr}"
    return expr


def _periodicity_expression(periodicity: int) -> str:
    names = {
        TaskSchedule.Periodicity.FIXED: "TaskSchedule.Periodicity.FIXED",
        TaskSchedule.Periodicity.LOCKOUT: "TaskSchedule.Periodicity.LOCKOUT",
        TaskSchedule.Periodicity.AFTER: "TaskSchedule.Periodicity.AFTER",
        TaskSchedule.Periodicity.LOCKOUT_DYNAMIC_BATTERY: "TaskSchedule.Periodicity.LOCKOUT_DYNAMIC_BATTERY",
    }
    return names.get(periodicity, str(periodicity))


def _validate_periodicity_type(periodicity: int) -> None:
    if periodicity != 0 and periodicity not in PERIODICITY_NAMES:
        raise ValueError(f"unknown periodicity_type {periodicity}")


def _lockout_expression(lockout_s: int) -> str:
    if lockout_s & PeriodicityLockout.IGNORE_FIRST:
        value = lockout_s & ~PeriodicityLockout.IGNORE_FIRST
        if value:
            return f"PeriodicityLockout.IGNORE_FIRST | {value}"
        return "PeriodicityLockout.IGNORE_FIRST"
    return str(lockout_s)


def _append_assignment(lines: list[str], target: str, value: int, expression: str | None = None) -> None:
    if value == 0:
        return
    lines.append(f"{target} = {expression or value}")


def _append_array_assignments(lines: list[str], target: str, values) -> None:
    for idx, value in enumerate(values):
        _append_assignment(lines, f"{target}[{idx}]", value)


def _class_expression(cls) -> str:
    return f"tasks.{cls.__qualname__}"


def _task_argument_expression(field_name: str, field_value, field_owner_type, root_task_class) -> str | None:
    option_class = task_argument_option_class(field_name, field_owner_type, root_task_class)
    if option_class is None:
        return None
    return _mask_expression(field_value, option_class, _class_expression(option_class))


def _append_struct_assignments(lines: list[str], target: str, value, root_task_class) -> None:
    for field_name, _field_type in getattr(value, "_fields_", []):
        field_value = getattr(value, field_name)
        field_target = f"{target}.{field_name}"
        if hasattr(field_value, "_fields_"):
            _append_struct_assignments(lines, field_target, field_value, root_task_class)
        elif isinstance(field_value, ctypes.Array):
            _append_array_assignments(lines, field_target, field_value)
        else:
            expression = _task_argument_expression(field_name, field_value, type(value), root_task_class)
            _append_assignment(lines, field_target, field_value, expression)


def decode_schedule_input(value: str, expected_len: int | None = None) -> bytes:
    """Decode a task schedule from a hex or base64 string."""
    compact = re.sub(r"[\s:_-]", "", value)
    if compact.startswith(("0x", "0X")):
        compact = compact[2:]

    candidates: list[tuple[str, bytes]] = []
    if compact and len(compact) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", compact):
        candidates.append(("hex", bytes.fromhex(compact)))

    try:
        candidates.append(("base64", base64.b64decode(value, validate=True)))
    except binascii.Error:
        pass

    if not candidates:
        raise ValueError("input is neither an even-length hex string nor valid base64")

    expected = ctypes.sizeof(TaskSchedule) if expected_len is None else expected_len
    for _encoding, data in candidates:
        if len(data) == expected:
            return data
    return candidates[0][1]


def parse_schedule(value: str | bytes | bytearray) -> TaskSchedule:
    """Parse a task schedule from encoded text or raw bytes."""
    if isinstance(value, str):
        data = decode_schedule_input(value)
    else:
        data = bytes(value)

    expected = ctypes.sizeof(TaskSchedule)
    if len(data) != expected:
        raise ValueError(f"decoded {len(data)} bytes, expected {expected}")
    return TaskSchedule.from_buffer_copy(data)


def encode_schedule(schedule: TaskSchedule, encoding: str = "hex") -> str:
    """Encode a task schedule as hex or base64 text."""
    payload = bytes(schedule)
    if encoding == "hex":
        return payload.hex()
    if encoding == "base64":
        return base64.b64encode(payload).decode("ascii")
    raise ValueError("encoding must be 'hex' or 'base64'")


def scalar_value(value):
    if isinstance(value, ctypes.Array):
        return list(value)
    return value


def format_struct(obj, indent: int = 0) -> list[str]:
    lines = []
    prefix = " " * indent
    fields = getattr(obj, "_fields_", [])
    if not fields:
        return [f"{prefix}(no arguments)"]

    for name, _field_type in fields:
        value = getattr(obj, name)
        if hasattr(value, "_fields_"):
            lines.append(f"{prefix}{name}:")
            lines.extend(format_struct(value, indent + 2))
        else:
            lines.append(f"{prefix}{name}: {scalar_value(value)}")
    return lines


def raw_task_args(schedule: TaskSchedule) -> bytes:
    return ctypes.string_at(ctypes.addressof(schedule.task_args), ctypes.sizeof(schedule.task_args))


def format_state_conditions(states, empty_default: bool, indent: int = 4) -> list[str]:
    prefix = " " * indent
    state_ids = list(states.states)
    lines = [
        f"{prefix}metadata: 0x{states.metadata:02x}",
        f"{prefix}raw_states: {state_ids}",
    ]

    if state_ids[0] == 0:
        lines.append(f"{prefix}decoded: no states configured, evaluates to {empty_default}")
        return lines

    terms = []
    for idx, state_id in enumerate(state_ids):
        if state_id == 0:
            break
        inverted = bool(states.metadata & (1 << idx))
        operator = "OR" if states.metadata & (1 << (idx + 4)) else "AND"
        term = f"{'NOT ' if inverted else ''}{state_name(state_id)} ({state_id})"
        terms.append((operator, term))
        lines.append(f"{prefix}[{idx}] {operator} {term}")

    initial = "false" if terms[0][0] == "OR" else "true"
    expression = " ".join(f"{operator} {term}" for operator, term in terms)
    lines.append(f"{prefix}decoded: initial={initial}; {expression}")
    return lines


def format_schedule(schedule: TaskSchedule, source_len: int | None = None) -> str:
    """Format every raw task schedule field."""
    _validate_periodicity_type(schedule.periodicity_type)
    task_name = TASK_ID_NAMES.get(schedule.task_id, "unknown")
    validity = VALIDITY_NAMES.get(schedule.validity & TaskSchedule.Validity.MASK, "unknown")
    locked = bool(schedule.validity & TaskSchedule.LOCKED)
    periodicity = PERIODICITY_NAMES.get(schedule.periodicity_type, "unknown")
    arg_field = tasks.TaskArguments.TASK_ARG_FIELDS.get(schedule.task_id)
    source_size = ctypes.sizeof(TaskSchedule) if source_len is None else source_len

    lines = [
        "Task Schedule",
        f"  source_size: {source_size} bytes",
        f"  ctypes_size: {ctypes.sizeof(TaskSchedule)} bytes",
        f"  task_id: {schedule.task_id} ({task_name})",
        f"  validity: 0x{schedule.validity:02x} ({validity}, locked={locked})",
        f"  periodicity_type: {schedule.periodicity_type} ({periodicity})",
        f"  boot_lockout_minutes: {schedule.boot_lockout_minutes}",
        f"  timeout_s: {schedule.timeout_s}",
        "  battery_start:",
        f"    lower: {schedule.battery_start.lower}",
        f"    upper: {schedule.battery_start.upper}",
        "  battery_terminate:",
        f"    lower: {schedule.battery_terminate.lower}",
        f"    upper: {schedule.battery_terminate.upper}",
        "  periodicity:",
    ]

    if schedule.periodicity_type == TaskSchedule.Periodicity.FIXED:
        lines.append(f"    fixed.period_s: {schedule.periodicity.fixed.period_s}")
    elif schedule.periodicity_type == TaskSchedule.Periodicity.LOCKOUT:
        lines.append(f"    lockout.lockout_s: {schedule.periodicity.lockout.lockout_s}")
    elif schedule.periodicity_type == TaskSchedule.Periodicity.AFTER:
        lines.append(f"    after.schedule_idx: {schedule.periodicity.after.schedule_idx}")
        lines.append(f"    after.duration_s: {schedule.periodicity.after.duration_s}")
    elif schedule.periodicity_type == TaskSchedule.Periodicity.LOCKOUT_DYNAMIC_BATTERY:
        value = schedule.periodicity.lockout_dynamic_battery
        lines.extend(
            [
                f"    lockout_dynamic_battery.lockout_min: {value.lockout_min}",
                f"    lockout_dynamic_battery.lockout_max: {value.lockout_max}",
                f"    lockout_dynamic_battery.battery_min: {value.battery_min}",
                f"    lockout_dynamic_battery.battery_max: {value.battery_max}",
            ]
        )
    else:
        lines.append(f"    raw: {bytes(schedule.periodicity).hex()}")

    lines.extend(
        [
            f"  states_start_timeout_2x_s: {schedule.states_start_timeout_2x_s}",
        ]
    )
    lines.append("  states_start:")
    lines.extend(format_state_conditions(schedule.states_start, True, 4))
    lines.append("  states_terminate:")
    lines.extend(format_state_conditions(schedule.states_terminate, False, 4))
    lines.append("  task_logging:")
    for idx, logging in enumerate(schedule.task_logging):
        lines.append(f"    [{idx}] loggers=0x{logging.loggers:02x}, tdf_mask=0x{logging.tdf_mask:02x}")

    lines.append(f"  task_args_raw: {raw_task_args(schedule).hex()}")
    if arg_field is None:
        lines.append("  task_args: unknown task_id")
    else:
        lines.append(f"  task_args ({arg_field}):")
        lines.extend(format_struct(getattr(schedule.task_args, arg_field), 4))

    return "\n".join(lines)


def format_schedule_python(schedule: TaskSchedule) -> str:
    """Format a task schedule as Python assignment lines."""
    _validate_periodicity_type(schedule.periodicity_type)
    lines = ["schedule = TaskSchedule()"]

    _append_assignment(lines, "schedule.task_id", schedule.task_id, _task_id_expression(schedule.task_id))
    _append_assignment(lines, "schedule.validity", schedule.validity, _validity_expression(schedule.validity))
    _append_assignment(
        lines,
        "schedule.periodicity_type",
        schedule.periodicity_type,
        _periodicity_expression(schedule.periodicity_type),
    )
    _append_assignment(lines, "schedule.boot_lockout_minutes", schedule.boot_lockout_minutes)
    _append_assignment(lines, "schedule.timeout_s", schedule.timeout_s)
    _append_assignment(lines, "schedule.battery_start.lower", schedule.battery_start.lower)
    _append_assignment(lines, "schedule.battery_start.upper", schedule.battery_start.upper)
    _append_assignment(lines, "schedule.battery_terminate.lower", schedule.battery_terminate.lower)
    _append_assignment(lines, "schedule.battery_terminate.upper", schedule.battery_terminate.upper)

    if schedule.periodicity_type == TaskSchedule.Periodicity.FIXED:
        _append_assignment(lines, "schedule.periodicity.fixed.period_s", schedule.periodicity.fixed.period_s)
    elif schedule.periodicity_type == TaskSchedule.Periodicity.LOCKOUT:
        _append_assignment(
            lines,
            "schedule.periodicity.lockout.lockout_s",
            schedule.periodicity.lockout.lockout_s,
            _lockout_expression(schedule.periodicity.lockout.lockout_s),
        )
    elif schedule.periodicity_type == TaskSchedule.Periodicity.AFTER:
        _append_assignment(lines, "schedule.periodicity.after.schedule_idx", schedule.periodicity.after.schedule_idx)
        _append_assignment(lines, "schedule.periodicity.after.duration_s", schedule.periodicity.after.duration_s)
    elif schedule.periodicity_type == TaskSchedule.Periodicity.LOCKOUT_DYNAMIC_BATTERY:
        value = schedule.periodicity.lockout_dynamic_battery
        _append_assignment(lines, "schedule.periodicity.lockout_dynamic_battery.lockout_min", value.lockout_min)
        _append_assignment(lines, "schedule.periodicity.lockout_dynamic_battery.lockout_max", value.lockout_max)
        _append_assignment(lines, "schedule.periodicity.lockout_dynamic_battery.battery_min", value.battery_min)
        _append_assignment(lines, "schedule.periodicity.lockout_dynamic_battery.battery_max", value.battery_max)

    _append_assignment(lines, "schedule.states_start_timeout_2x_s", schedule.states_start_timeout_2x_s)
    _append_assignment(lines, "schedule.states_start.metadata", schedule.states_start.metadata)
    _append_array_assignments(lines, "schedule.states_start.states", schedule.states_start.states)
    _append_assignment(lines, "schedule.states_terminate.metadata", schedule.states_terminate.metadata)
    _append_array_assignments(lines, "schedule.states_terminate.states", schedule.states_terminate.states)

    for idx, logging in enumerate(schedule.task_logging):
        task_class_name = _task_class_name(schedule.task_id)
        logging_class = tasks.TaskArguments.TASK_LOGGING_CLASSES.get(schedule.task_id)
        tdf_mask_expression = (
            _mask_expression(logging.tdf_mask, logging_class, f"tasks.{task_class_name}.Logging")
            if task_class_name is not None
            else f"0x{logging.tdf_mask:02x}"
        )
        _append_assignment(
            lines,
            f"schedule.task_logging[{idx}].loggers",
            logging.loggers,
            _mask_expression(logging.loggers, tasks.TdfDataLogger, "tasks.TdfDataLogger"),
        )
        _append_assignment(lines, f"schedule.task_logging[{idx}].tdf_mask", logging.tdf_mask, tdf_mask_expression)

    arg_field = tasks.TaskArguments.TASK_ARG_FIELDS.get(schedule.task_id)
    if arg_field is None:
        for idx, value in enumerate(raw_task_args(schedule)):
            _append_assignment(lines, f"schedule.task_args.raw[{idx}]", value, f"0x{value:02x}")
    else:
        root_task_class = task_class(schedule.task_id)
        task_args = getattr(schedule.task_args, arg_field)
        _append_struct_assignments(lines, f"schedule.task_args.{arg_field}", task_args, root_task_class)

    return "\n".join(lines)
