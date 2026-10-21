"""Bounded immutable snapshots for consistent pagination of live observations."""

import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from infuse_iot.socket_comms import GatewayControlError

# A cursor stays valid this long after its last use, up to the snapshot's maximum lifetime.
IDLE_EXPIRY_S = 60.0
MAX_LIFETIME_S = 600.0
MAX_SNAPSHOTS = 8
MAX_LIMIT = 200


class PaginationError(GatewayControlError):
    """A page request failed with code `snapshot_expired`, `invalid_cursor` or `item_exceeds_response_budget`."""


def encode(value: Any) -> str:
    return json.dumps(value, allow_nan=False)


@dataclass
class _Snapshot:
    query: dict
    metadata: dict
    generated_at: float
    rows: list[str]
    created: float
    accessed: float


class SnapshotPages:
    """Serve pages of immutable snapshots, so that live updates cannot shift rows between pages.

    Only snapshots with further pages are retained, so single-page and unpaginated results never
    evict another caller's cursor.
    """

    def __init__(self, started_at: float):
        self.started_at = started_at
        self._lock = threading.Lock()
        self._snapshots: OrderedDict[str, _Snapshot] = OrderedDict()

    def page(
        self,
        build: Callable[[], tuple[list[dict], dict]] | None,
        query: dict,
        cursor: str | None = None,
        limit: int = 50,
        max_bytes: int = 60000,
        paginate: bool = True,
        fit: Callable[[dict, int], dict] | None = None,
    ) -> dict[str, Any]:
        """Return the first page of the rows and metadata from `build`, or a later page of a cursor's snapshot.

        `build` is only called without a cursor. `fit` can shrink a row to a byte budget, rather than failing.
        Without pagination, every row is returned and nothing is retained.
        """
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit must be an integer between 1 and {MAX_LIMIT}")
        now = time.monotonic()
        if cursor is None:
            if build is None:
                raise ValueError("No rows to paginate")
            rows, metadata = build()
            key, offset = uuid4().hex, 0
            snapshot = _Snapshot(query, metadata, time.time(), [], now, now)
            budget = max_bytes - self._size(self._envelope(key, snapshot, len(rows), f"{key}:{len(rows)}"))
            for row in rows:
                encoded = encode(row)
                if paginate and fit is not None and len(encoded) > budget:
                    encoded = encode(fit(row, budget))
                snapshot.rows.append(encoded)
            if not paginate:
                result = self._envelope(None, snapshot, len(rows), None)
                result["items"] = [json.loads(row) for row in snapshot.rows]
                return result
        else:
            if not paginate:
                raise ValueError("A cursor continues a paginated snapshot")
            key, offset = self._parse(cursor)
            with self._lock:
                self._expire(now)
                found = self._snapshots.get(key)
                if found is None:
                    raise PaginationError("snapshot_expired", "The snapshot expired or was evicted; start again")
                if found.query != query:
                    raise PaginationError("invalid_cursor", "The cursor belongs to a query with different parameters")
                if offset > len(found.rows):
                    raise PaginationError("invalid_cursor", "The cursor is beyond the end of the snapshot")
                found.accessed = now
                self._snapshots.move_to_end(key)
            snapshot = found
        result = self._envelope(key, snapshot, len(snapshot.rows), None)
        # Size against the longest cursor, which a shorter cursor or `null` cannot exceed.
        size = self._size({**result, "next_cursor": f"{key}:{len(snapshot.rows)}"})
        end = offset
        for encoded in snapshot.rows[offset : offset + limit]:
            # Rows after the first are separated by ", "
            added = len(encoded) + (2 if end > offset else 0)
            if size + added > max_bytes:
                if end == offset:
                    raise PaginationError(
                        "item_exceeds_response_budget", "A row exceeds the response budget; select fewer fields"
                    )
                break
            size += added
            end += 1
        result["items"] = [json.loads(row) for row in snapshot.rows[offset:end]]
        if end < len(snapshot.rows):
            result["next_cursor"] = f"{key}:{end}"
            if cursor is None:
                with self._lock:
                    self._expire(now)
                    self._snapshots[key] = snapshot
                    while len(self._snapshots) > MAX_SNAPSHOTS:
                        self._snapshots.popitem(last=False)
        return result

    @staticmethod
    def _size(value: dict) -> int:
        return len(encode(value).encode())

    def _envelope(self, key: str | None, snapshot: _Snapshot, total: int, next_cursor: str | None) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "snapshot_id": key,
            "generated_at": snapshot.generated_at,
            "collector_started_at": self.started_at,
            **snapshot.metadata,
            "total": total,
            "items": [],
            "next_cursor": next_cursor,
        }

    @staticmethod
    def _parse(cursor: Any) -> tuple[str, int]:
        if not isinstance(cursor, str) or len(cursor) > 128:
            raise PaginationError("invalid_cursor", "The cursor must be a string returned as `next_cursor`")
        key, _, offset_text = cursor.partition(":")
        if not (offset_text.isascii() and offset_text.isdigit()):
            raise PaginationError("invalid_cursor", "The cursor must be a string returned as `next_cursor`")
        return key, int(offset_text)

    def _expire(self, now: float) -> None:
        for key, snapshot in list(self._snapshots.items()):
            if snapshot.accessed + IDLE_EXPIRY_S < now or snapshot.created + MAX_LIFETIME_S < now:
                del self._snapshots[key]
