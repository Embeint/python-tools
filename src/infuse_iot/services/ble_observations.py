"""Raw Bluetooth evidence, independent of Infuse credentials or decryption."""

import re
import threading
import time
from collections import OrderedDict
from collections.abc import Iterable
from itertools import islice
from typing import Any

from infuse_iot.services.pagination import SnapshotPages, encode

INFUSE_MANUFACTURER = "0x0de4"
INFUSE_SERVICE = "0000fc74-0000-1000-8000-00805f9b34fb"
MAX_AGE_SECONDS = 120

_ADDRESS = re.compile(r"[0-9a-fA-F]{2}([:-][0-9a-fA-F]{2}){5}")


def bluetooth_identifier(identifier: str) -> str:
    """Canonical form of a Bluetooth address (upper case, colon separated) or other platform identifier."""
    if _ADDRESS.fullmatch(identifier):
        return identifier.replace("-", ":").upper()
    return identifier


def _fit(row: dict[str, Any], budget: int) -> dict[str, Any]:
    """Drop markers, keeping Infuse markers, then shorten the name until the row fits the budget."""
    row = {**row, "truncated": True}
    for key, infuse in (("service_uuids", INFUSE_SERVICE), ("manufacturer_ids", INFUSE_MANUFACTURER)):
        values = [v for v in row[key] if v == infuse] + [v for v in row[key] if v != infuse]
        while values and len(encode({**row, key: values})) > budget:
            values.pop()
        row[key] = sorted(values)
    while row["name"] and len(encode(row)) > budget:
        row["name"] = row["name"][: len(row["name"]) // 2] or None
    return row


class BleObservations:
    def __init__(self, max_devices: int = 4096):
        self._lock = threading.Lock()
        self._devices: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._max_devices = max_devices
        self.started_at = time.time()
        self.advertisements = 0
        self.evictions = 0
        self._pages = SnapshotPages(self.started_at)

    def observe(
        self,
        identifier: str,
        name: str | None,
        rssi: int,
        manufacturer_ids: Iterable[int],
        service_uuids: Iterable[str],
    ) -> None:
        now, wall = time.monotonic(), time.time()
        identifier = bluetooth_identifier(identifier)
        with self._lock:
            self.advertisements += 1
            row = self._devices.pop(
                identifier,
                {"identifier": identifier, "first_seen_at": wall, "name": None, "manufacturer": {}, "services": {}},
            )
            row.update(last_seen_at=wall, last_seen_monotonic=now, rssi=rssi)
            if name:
                row.update(name=name[:256], name_observed_at=wall)
            row["manufacturer"] = {k: v for k, v in row["manufacturer"].items() if v >= now - MAX_AGE_SECONDS}
            row["services"] = {k: v for k, v in row["services"].items() if v >= now - MAX_AGE_SECONDS}
            for value in islice(manufacturer_ids, 32):
                row["manufacturer"][int(value)] = now
            for service in islice(service_uuids, 32):
                row["services"][service.lower()[:64]] = now
            for kind in ("manufacturer", "services"):
                row[kind] = dict(sorted(row[kind].items(), key=lambda entry: entry[1])[-128:])
            self._devices[identifier] = row
            while len(self._devices) > self._max_devices:
                self._devices.popitem(last=False)
                self.evictions += 1

    def snapshot(
        self,
        max_age_seconds: float = 20,
        cursor: str | None = None,
        limit: int = 50,
        infuse_only: bool = False,
        max_bytes: int = 5000,
        paginate: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict:
        """Identifiers observed within `max_age_seconds`, merging their markers over that window.

        Rows that would exceed the byte budget drop markers and are flagged `truncated`. Without
        pagination, all rows are returned in full and no cursor is retained. `metadata` is added to
        the result, such as the identity of the gateway that made the observations.
        """
        # The range check also rejects NaN and infinity
        if (
            isinstance(max_age_seconds, bool)
            or not isinstance(max_age_seconds, int | float)
            or not 0 <= max_age_seconds <= MAX_AGE_SECONDS
        ):
            raise ValueError(f"max_age_seconds must be a number between 0 and {MAX_AGE_SECONDS}")
        if not isinstance(infuse_only, bool):
            raise ValueError("infuse_only must be a boolean")
        filters = {"max_age_seconds": max_age_seconds, "infuse_only": infuse_only}

        def build() -> tuple[list[dict], dict]:
            now, wall = time.monotonic(), time.time()
            cutoff = now - max_age_seconds
            rows = []
            with self._lock:
                for item in self._devices.values():
                    if item["last_seen_monotonic"] < cutoff:
                        continue
                    manufacturer = sorted(k for k, seen in item["manufacturer"].items() if seen >= cutoff)
                    services = sorted(k for k, seen in item["services"].items() if seen >= cutoff)
                    candidate = 0x0DE4 in manufacturer or INFUSE_SERVICE in services
                    if infuse_only and not candidate:
                        continue
                    row = {k: item[k] for k in ("identifier", "name", "rssi", "first_seen_at", "last_seen_at")}
                    row.update(
                        manufacturer_ids=[f"0x{k:04x}" for k in manufacturer],
                        service_uuids=services,
                        infuse_candidate=candidate,
                        name_observed_at=item.get("name_observed_at"),
                        truncated=False,
                    )
                    rows.append(row)
                counts = {"advertisements_since_start": self.advertisements, "evictions": self.evictions}
            window = {"start": max(self.started_at, wall - max_age_seconds), "end": wall}
            rows.sort(key=lambda r: r["identifier"])
            return rows, {"filters": filters, "observation_window": window, **counts, **(metadata or {})}

        return self._pages.page(build, filters, cursor, limit, max_bytes=max_bytes, paginate=paginate, fit=_fit)
