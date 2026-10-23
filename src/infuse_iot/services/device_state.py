"""Typed, timestamped TDF state with a presentation adapter for the viewer."""

import ctypes
import dataclasses
import math
import threading
import time
from collections import OrderedDict
from typing import Any

from infuse_iot.common import InfuseType
from infuse_iot.definitions.tdf import structs
from infuse_iot.epacket import interface
from infuse_iot.epacket.packet import Auth, PacketReceived
from infuse_iot.generated.tdf_base import TdfStructBase
from infuse_iot.services.pagination import SnapshotPages
from infuse_iot.tdf import TDF
from infuse_iot.time import InfuseTime
from infuse_iot.util.argparse import infuse_device_id_to_vendor

# Larger integers lose precision as JSON numbers in JavaScript.
MAX_SAFE_INTEGER = 2**53 - 1
FIRMWARE_READINGS = ("ANNOUNCE", "ANNOUNCE_V2")
# A stored sample outranks an earlier-stamped one only if received this recently, and not stamped this long after its
# receipt, so a wrong or reset device clock cannot freeze a reading.
SAMPLE_ORDER_WINDOW_S = 60.0


def _value(value: Any, name: str | None = None) -> Any:
    """A JSON value for a TDF field. Infuse IDs are hexadecimal strings, other unsafe integers decimal strings."""
    if isinstance(value, structs.tdf_struct_mcuboot_img_sem_ver):
        return f"{value.major}.{value.minor}.{value.revision}+{value.build_num:08x}"
    if isinstance(value, TdfStructBase):
        return {f.subfield: _value(f.val, f.subfield) for f in value.iter_fields("")}
    if isinstance(value, ctypes.Array | list | tuple):
        return [_value(v) for v in value[:256]]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, int) and not isinstance(value, bool):
        if name == "infuse_id" and 0 <= value < 2**64:
            return f"0x{value:016x}"
        if abs(value) > MAX_SAFE_INTEGER:
            return str(value)
    return value


def _hex_filter(value: str | int | None, name: str, digits: int) -> str | None:
    """Normalize an application or network ID filter to the form used in rows."""
    if value is None:
        return None
    try:
        number = value if isinstance(value, int) and not isinstance(value, bool) else int(str(value), 16)
    except ValueError:
        raise ValueError(f"{name} must be hexadecimal") from None
    if not 0 <= number < 16**digits:
        raise ValueError(f"{name} must fit in {digits} hexadecimal digits")
    return f"0x{number:0{digits}x}"


@dataclasses.dataclass
class _Reading:
    # Entries are replaced rather than mutated, so a snapshot can share them after copying its containers.
    values: dict[str, Any]
    units: dict[str, str]
    received_at: float
    received_monotonic: float
    sampled_at: float | None

    def outranks(self, sampled: float | None, now: float) -> bool:
        """Whether this reading should be kept over a sample stamped `sampled`, arriving at monotonic time `now`."""
        return (
            sampled is not None
            and self.sampled_at is not None
            and sampled < self.sampled_at
            # A sample stamped after its receipt shows the device clock was wrong.
            and self.sampled_at <= self.received_at + SAMPLE_ORDER_WINDOW_S
            # Later, the latest sample to arrive wins, as after a device clock reset.
            and now - self.received_monotonic < SAMPLE_ORDER_WINDOW_S
        )


@dataclasses.dataclass
class _Device:
    id: str
    first_seen_at: float
    last_seen_at: float = 0.0
    last_seen_monotonic: float = 0.0
    application_id: str | None = None
    network_id: str | None = None
    bluetooth: dict[str, Any] | None = None
    firmware_version: str | None = None
    firmware_observed_at: float | None = None
    firmware_monotonic: float | None = None
    readings: dict[str, _Reading] = dataclasses.field(default_factory=dict)


class DeviceState:
    def __init__(self, max_devices: int = 4096):
        self.lock = threading.RLock()
        self.decoder = TDF()
        self.started_at = time.time()
        self._devices: OrderedDict[int, _Device] = OrderedDict()
        self._max_devices = max_devices
        self._pages = SnapshotPages(self.started_at)
        self.decode_errors = 0
        self.evictions = 0
        # Identity of the gateway providing observations, set by the collector that attaches to it.
        self.gateway: dict[str, Any] | None = None
        # The existing viewer contract is maintained here, rather than decoded a second time.
        self.display_rows: dict[int, dict] = {}
        self.tdf_types: dict[str, Any] = {}

    def observe(self, packet: PacketReceived) -> bool:
        if packet.ptype != InfuseType.TDF or not packet.route:
            return False
        with self.lock:
            try:
                decoded = list(self.decoder.decode(packet.payload))
            except Exception:
                # Malformed TDF data from a device must not stop collection.
                self.decode_errors += 1
                return False
            source = packet.route[0]
            device, wall, mono = source.infuse_id, time.time(), time.monotonic()
            state = self._devices.pop(device, None) or _Device(f"0x{device:016x}", wall)
            state.last_seen_at, state.last_seen_monotonic = wall, mono
            self._devices[device] = state
            display = self.display_rows.setdefault(
                device,
                {
                    "infuse_id": infuse_device_id_to_vendor(device) or f"0x{device:016x}",
                    "application": "Unknown",
                    "network_id": "None",
                },
            )
            display["time"] = InfuseTime.utc_time_string(wall)
            if source.interface == interface.ID.BT_ADV:
                address = source.interface_address.val.addr_val.to_bytes(6, "big")
                state.bluetooth = {"address": address.hex(":").upper(), "rssi_dbm": source.rssi}
                display.update(bt_addr=address.hex(":"), bt_rssi=source.rssi)
            if source.auth == Auth.NETWORK:
                network = f"0x{source.key_identifier:06x}"
                state.network_id = network
                display["network_id"] = network
            for reading in decoded:
                if not reading.data:
                    continue
                value = reading.data[-1]
                # Only the device's own sample time is published, for the last sample of an array.
                sampled = None
                if reading.time is not None:
                    sampled = reading.time + (reading.period or 0) * (len(reading.data) - 1)
                previous = state.readings.get(value.NAME)
                if previous is not None and previous.outranks(sampled, mono):
                    # A delayed sample must not replace a newer one, in the viewer either.
                    continue
                self.tdf_types[value.NAME] = value
                display[value.NAME] = self._display(value)
                if value.NAME in FIRMWARE_READINGS:
                    display["application"] = f"0x{value.application:08x}"
                values = {f.field: _value(f.val, f.field) for f in value.iter_fields(nested_iter=False)}
                units = {f.name: f.postfix for f in value.iter_fields()}
                state.readings[value.NAME] = _Reading(values, units, wall, mono, sampled)
                if value.NAME in FIRMWARE_READINGS:
                    state.application_id = f"0x{value.application:08x}"
                    state.firmware_version = values["version"]
                    state.firmware_observed_at, state.firmware_monotonic = wall, mono
            while len(self._devices) > self._max_devices:
                expired, _ = self._devices.popitem(last=False)
                self.display_rows.pop(expired, None)
                self.evictions += 1
            return True

    @staticmethod
    def _display(reading) -> dict:
        result: dict[str, Any] = {}
        for field in reading.iter_fields(nested_iter=False):
            if isinstance(field.val, structs.tdf_struct_mcuboot_img_sem_ver):
                result[field.field] = _value(field.val)
            elif isinstance(field.val, TdfStructBase):
                result[field.field] = {f.subfield: f.val_fmt() for f in field.val.iter_fields(field.field)}
            else:
                result[field.field] = field.val_fmt()
        return result

    def snapshot(
        self,
        ids: list[str] | None = None,
        application_id: str | None = None,
        network_id: str | None = None,
        max_age_seconds: float = 120,
        fields: list[str] | None = None,
        cursor: str | None = None,
        limit: int = 50,
        max_bytes: int = 60000,
        paginate: bool = True,
    ) -> dict:
        """Devices observed within `max_age_seconds`, with the age of each reading and firmware announcement.

        Later pages are served from the snapshot taken for the first page. Without pagination, all
        matching devices are returned and no cursor is retained, for one-shot lookups.
        """
        if (
            isinstance(max_age_seconds, bool)
            or not isinstance(max_age_seconds, int | float)
            or (isinstance(max_age_seconds, float) and not math.isfinite(max_age_seconds))
            or not 0 <= max_age_seconds <= MAX_SAFE_INTEGER
        ):
            raise ValueError("max_age_seconds must be a finite nonnegative number")
        normalized = None
        if ids is not None:
            if isinstance(ids, str):
                raise ValueError("ids must be a list of device IDs")
            try:
                numbers = {int(d, 16) for d in ids}
            except (TypeError, ValueError):
                raise ValueError("Device IDs must be hexadecimal strings") from None
            if any(not 0 <= d < 2**64 for d in numbers):
                raise ValueError("Invalid device ID")
            normalized = {f"0x{d:016x}" for d in numbers}
        if fields is not None and (isinstance(fields, str) or not all(isinstance(f, str) for f in fields)):
            raise ValueError("fields must be a list of TDF names")
        query = {
            "ids": sorted(normalized) if normalized is not None else None,
            "application_id": _hex_filter(application_id, "application_id", 8),
            "network_id": _hex_filter(network_id, "network_id", 6),
            "max_age_seconds": max_age_seconds,
            "fields": None if fields is None else sorted(set(fields)),
        }

        def build() -> tuple[list[dict], dict]:
            now, wall = time.monotonic(), time.time()
            with self.lock:
                # Copy the mutable fields while locked; readings are immutable once stored.
                selected = [
                    (vars(state).copy(), dict(state.readings))
                    for _, state in sorted(self._devices.items())
                    if (normalized is None or state.id in normalized)
                    and query["application_id"] in (None, state.application_id)
                    and query["network_id"] in (None, state.network_id)
                    and now - state.last_seen_monotonic <= max_age_seconds
                ]
                counts = {"decode_errors": self.decode_errors, "evictions": self.evictions}
                gateway = self.gateway
            rows = [self._row(state, readings, now, wall, max_age_seconds, fields) for state, readings in selected]
            window = {"start": max(self.started_at, wall - max_age_seconds), "end": wall}
            return rows, {"filters": query, "observation_window": window, "gateway": gateway, **counts}

        return self._pages.page(build, query, cursor, limit, max_bytes=max_bytes, paginate=paginate)

    @staticmethod
    def _row(
        state: dict[str, Any],
        readings: dict[str, _Reading],
        now: float,
        wall: float,
        max_age: float,
        fields: list[str] | None,
    ) -> dict[str, Any]:
        firmware_age = None if state["firmware_monotonic"] is None else max(0, now - state["firmware_monotonic"])
        result = {
            "id": state["id"],
            "first_seen_at": state["first_seen_at"],
            "last_seen_at": state["last_seen_at"],
            "age_seconds": max(0, now - state["last_seen_monotonic"]),
            "application_id": state["application_id"],
            "network_id": state["network_id"],
            "firmware_version": state["firmware_version"],
            "firmware_observed_at": state["firmware_observed_at"],
            # The announcement's own freshness, which other telemetry does not refresh.
            "firmware_age_seconds": firmware_age,
            "firmware_stale": None if firmware_age is None else firmware_age > max_age,
            "readings": {},
        }
        if state["bluetooth"] is not None:
            result["bluetooth"] = state["bluetooth"]
        for name, reading in readings.items():
            if fields is not None and name not in fields:
                continue
            age = max(0, now - reading.received_monotonic)
            # A recently received backlog sample, or one from a wrong device clock, is not fresh evidence.
            sample_age = None if reading.sampled_at is None else max(0, wall - reading.sampled_at)
            result["readings"][name] = {
                "values": reading.values,
                "units": reading.units,
                "received_at": reading.received_at,
                "sampled_at": reading.sampled_at,
                "age_seconds": age,
                "sample_age_seconds": sample_age,
                "stale": age > max_age or (sample_age is not None and sample_age > max_age),
            }
        return result
