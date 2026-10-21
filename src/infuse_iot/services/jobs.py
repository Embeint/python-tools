"""Durable, idempotent jobs that only the accepting server instance executes, with explicit uncertain outcomes."""

import json
import os
import re
import sqlite3
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any
from uuid import uuid4

from infuse_iot.services.device_operations import DeviceError
from infuse_iot.socket_comms import GatewayControlError

TERMINAL = {"completed", "failed", "cancelled", "unknown"}
SCHEMA_VERSION = 1
COLUMNS = "id,request_key,specification,state,created,updated,progress,result,error,cancel_requested,gateway"
STOPPED = {
    "code": "server_stopped",
    "message": "The server that accepted this job stopped before sending anything to the device",
    "retryable": True,
}
INTERRUPTED = {
    "code": "interrupted",
    "message": "Server stopped while the action may have reached the device; reconcile device state before retrying",
    "retryable": False,
}

if sys.platform == "win32":
    import msvcrt

    def _lock(descriptor: int) -> bool:
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True

    def _unlock(descriptor: int) -> None:
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(descriptor: int) -> bool:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _unlock(descriptor: int) -> None:
        fcntl.flock(descriptor, fcntl.LOCK_UN)


class JobCancelled(Exception):
    pass


class JobContext:
    """Checkpoints for a handler. Call `sending()` immediately before the first device-visible effect."""

    def __init__(self, jobs: "JobManager", job_id: str):
        self.jobs, self.job_id = jobs, job_id
        self.sent = False
        self.outcome: dict | None = None

    def check_cancelled(self) -> None:
        if self.jobs._stop.is_set() or self.jobs._cancel_requested(self.job_id):
            raise JobCancelled

    def wait(self, seconds: float) -> None:
        """Sleep, raising `JobCancelled` promptly on cancellation or server stop."""
        deadline = time.monotonic() + seconds
        while (remaining := deadline - time.monotonic()) > 0:
            self.jobs._stop.wait(min(remaining, 0.25))
            self.check_cancelled()

    def sending(self) -> None:
        """Pass the last checkpoint; a stop can no longer cancel the job, so its outcome may become unknown."""
        self.check_cancelled()
        with self.jobs._send_lock:
            if self.jobs._stop.is_set():
                raise JobCancelled
            self.sent = True

    def progress(self, phase: str, **values) -> None:
        try:
            self.jobs._update(self.job_id, progress={"phase": phase, **values})
        except sqlite3.Error as error:
            # Progress is informational; the outcome is recorded separately.
            self.jobs._report(f"recording progress of {self.job_id}", error)


class JobManager:
    def __init__(self, directory: Path, gateway: str | None = None, retention_seconds: float = 30 * 86400):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.gateway = gateway
        self.instance = uuid4().hex
        self._instances = directory / "instances"
        self._retention = retention_seconds
        self._lock = threading.RLock()
        self._send_lock = threading.Lock()
        self._connection = sqlite3.connect(directory / "jobs.sqlite3", timeout=5, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._migrate()
        self.handlers: dict[str, Callable[[dict, JobContext], dict]] = {}
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._worker: threading.Thread | None = None
        self._instance_lock: int | None = None
        self._current: JobContext | None = None
        self._error: str | None = None

    def _migrate(self) -> None:
        # Pre-release servers used a `jobs` table, left untouched so that one still running cannot claim these jobs.
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            version = self._connection.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(f"Job database schema {version} is newer than this version supports")
            self._connection.execute("""CREATE TABLE IF NOT EXISTS jobs_v1 (
                id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, specification TEXT NOT NULL,
                state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                progress TEXT NOT NULL, result TEXT, error TEXT,
                cancel_requested INTEGER NOT NULL DEFAULT 0, owner TEXT, gateway TEXT)""")
            self._connection.execute("CREATE INDEX IF NOT EXISTS jobs_v1_state ON jobs_v1(state, owner)")
            self._connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    @contextmanager
    def _storage(self) -> Iterator[None]:
        try:
            yield
        except sqlite3.Error as error:
            raise DeviceError("state_unavailable", f"Job database unavailable: {type(error).__name__}", True) from error

    def _report(self, activity: str, error: BaseException) -> None:
        detail = f"{type(error).__name__}: {error}"
        print(f"infuse jobs: {activity}: {detail}", file=sys.stderr, flush=True)
        # Health is a tool result, so it omits other messages, which can include local paths.
        self._error = f"{activity}: {detail if isinstance(error, sqlite3.Error) else type(error).__name__}"

    def health(self) -> dict:
        worker = self._worker
        running = worker is not None and worker.is_alive() and not self._stop.is_set()
        return {"worker_running": running, "last_error": self._error}

    def _has_exited(self, owner: str | None) -> bool:
        """Whether the server instance that accepted a job has exited, judged by its OS file lock."""
        if owner is None or not re.fullmatch("[0-9a-f]{32}", owner):
            return True
        path = self._instances / f"{owner}.lock"
        try:
            descriptor = os.open(path, os.O_RDWR)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        try:
            if not _lock(descriptor):
                return False
            _unlock(descriptor)
        finally:
            os.close(descriptor)
        with suppress(OSError):
            path.unlink()
        return True

    def _recover(self) -> None:
        """Close out jobs of exited servers: queued work was never sent, running work may have been."""
        with self._lock:
            owners = self._connection.execute(
                "SELECT DISTINCT owner FROM jobs_v1 WHERE state IN ('queued','running') AND owner IS NOT ?",
                (self.instance,),
            ).fetchall()
            for (owner,) in owners:
                if self._has_exited(owner):
                    with self._connection:
                        self._close_out(owner, None)

    def _close_out(self, owner: str | None, current: JobContext | None) -> None:
        now = time.time()
        if current is not None:
            outcome = current.outcome or (
                {"state": "unknown", "error": INTERRUPTED} if current.sent else {"state": "cancelled", "error": STOPPED}
            )
            self._set(current.job_id, **outcome)
        statements = (("cancelled", STOPPED, "queued"), ("unknown", INTERRUPTED, "running"))
        for state, error, previous in statements:
            self._connection.execute(
                "UPDATE jobs_v1 SET state=?, error=?, updated=? WHERE owner IS ? AND state=?",
                (state, json.dumps(error), now, owner, previous),
            )

    def _prune(self) -> None:
        with self._lock, self._connection:
            self._connection.execute(
                "DELETE FROM jobs_v1 WHERE state IN ('completed','failed','cancelled','unknown') AND updated < ?",
                (time.time() - self._retention,),
            )
        # Instances that crashed with no open jobs leave only their lock file behind.
        cutoff = time.time() - 3600
        for path in self._instances.glob("*.lock"):
            if path.stem != self.instance and path.stat().st_mtime < cutoff:
                self._has_exited(path.stem)

    def start(self) -> None:
        with self._lock:
            if self._stop.is_set():
                raise DeviceError("server_stopped", "The job worker has stopped", True)
            if self._worker is not None and self._worker.is_alive():
                return
            if self._instance_lock is None:
                # Hold the lock before any job names this instance, so others never mistake it for exited.
                self._instances.mkdir(exist_ok=True, mode=0o700)
                descriptor = os.open(self._instances / f"{self.instance}.lock", os.O_RDWR | os.O_CREAT, 0o600)
                if not _lock(descriptor):
                    os.close(descriptor)
                    raise RuntimeError("Could not lock the job instance file")
                self._instance_lock = descriptor
                try:
                    self._recover()
                    self._prune()
                except (OSError, sqlite3.Error) as error:
                    self._report("recovering jobs", error)
            self._worker = threading.Thread(target=self._run, name="infuse-jobs", daemon=True)
            self._worker.start()

    def submit(self, request_key: str, specification: dict) -> dict:
        if not 1 <= len(request_key) <= 128:
            raise ValueError("request_key must contain 1..128 characters")
        if specification.get("action") not in self.handlers:
            raise ValueError("Unsupported job action")
        encoded = json.dumps(specification, sort_keys=True, allow_nan=False)
        self.start()
        now = time.time()
        with self._storage(), self._lock, self._connection:
            self._connection.execute(
                """INSERT OR IGNORE INTO jobs_v1
                (id,request_key,specification,state,created,updated,progress,owner,gateway)
                VALUES (?,?,?,'queued',?,?,'{}',?,?)""",
                (uuid4().hex, request_key, encoded, now, now, self.instance, self.gateway),
            )
            row = self._connection.execute(
                "SELECT id,specification FROM jobs_v1 WHERE request_key=?", (request_key,)
            ).fetchone()
        if row["specification"] != encoded:
            raise DeviceError("idempotency_conflict", "request_key was already used for a different operation")
        self._wake.set()
        return self.status(row["id"])

    def status(self, job_id: str) -> dict[str, Any]:
        with self._storage(), self._lock:
            row = self._connection.execute(f"SELECT {COLUMNS} FROM jobs_v1 WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise DeviceError("job_not_found", "No job has this ID")
        result = dict(row)
        for field in ("specification", "progress", "result", "error"):
            result[field] = json.loads(result[field]) if result[field] is not None else None
        result["cancel_requested"] = bool(result["cancel_requested"])
        result["worker"] = self.health()
        return result

    def cancel(self, job_id: str) -> dict:
        self.status(job_id)
        with self._storage(), self._lock, self._connection:
            self._connection.execute(
                """UPDATE jobs_v1 SET cancel_requested=1,
                   state=CASE WHEN state='queued' THEN 'cancelled' ELSE state END, updated=?
                   WHERE id=? AND state IN ('queued','running')""",
                (time.time(), job_id),
            )
        self._wake.set()
        return self.status(job_id)

    def _cancel_requested(self, job_id: str) -> bool:
        with self._lock:
            row = self._connection.execute("SELECT cancel_requested FROM jobs_v1 WHERE id=?", (job_id,)).fetchone()
        return bool(row and row[0])

    def _set(self, job_id: str, **values) -> bool:
        values["updated"] = time.time()
        encoded = {
            key: json.dumps(value, allow_nan=False) if key in ("progress", "result", "error") else value
            for key, value in values.items()
        }
        columns = ",".join(f"{key}=?" for key in encoded)
        # Terminal states are immutable; only this instance's running job may change.
        cursor = self._connection.execute(
            f"UPDATE jobs_v1 SET {columns} WHERE id=? AND owner=? AND state='running'",
            (*encoded.values(), job_id, self.instance),
        )
        return cursor.rowcount == 1

    def _update(self, job_id: str, **values) -> bool:
        with self._lock, self._connection:
            return self._set(job_id, **values)

    def _claim(self) -> tuple[JobContext, dict] | None:
        with self._lock:
            if self._stop.is_set():
                return None
            rows = self._connection.execute(
                "SELECT id,specification FROM jobs_v1 WHERE owner=? AND state='queued' ORDER BY rowid", (self.instance,)
            ).fetchall()
            for row in rows:
                with self._connection:
                    claimed = self._connection.execute(
                        "UPDATE jobs_v1 SET state='running',updated=? WHERE id=? AND state='queued'",
                        (time.time(), row["id"]),
                    ).rowcount
                if claimed:
                    self._current = JobContext(self, row["id"])
                    return self._current, json.loads(row["specification"])
        return None

    def _run(self) -> None:
        delay = 0.25
        while not self._stop.is_set():
            try:
                self._recover()
                job = self._claim()
                if job is not None:
                    self._execute(*job)
                self._error = None
                delay = 0.25
            except Exception as error:
                # Storage can be locked or full for a while; keep the worker alive and report it.
                self._report("running jobs", error)
                self._stop.wait(delay)
                delay = min(delay * 2, 5)
                continue
            if job is None:
                self._wake.wait(0.25)
                self._wake.clear()

    def _execute(self, context: JobContext, specification: dict) -> None:
        try:
            context.check_cancelled()
            result = self.handlers[specification["action"]](specification, context)
            context.outcome = {"state": "completed", "result": result}
        except JobCancelled:
            if context.sent:
                context.outcome = {"state": "unknown", "error": INTERRUPTED}
            elif self._stop.is_set():
                context.outcome = {"state": "cancelled", "error": STOPPED}
            else:
                context.outcome = {"state": "cancelled"}
        except DeviceError as error:
            state = "unknown" if error.code == "outcome_unknown" else "failed"
            context.outcome = {
                "state": state,
                "error": {"code": error.code, "message": error.message, "retryable": error.retryable},
            }
        except Exception as error:
            # Report the exception type only; arbitrary messages could carry credentials or local paths.
            state, code, retryable, message = "failed", "internal_error", False, "Nothing was sent to the device"
            if context.sent:
                state, message = "unknown", "Reconcile device state before retrying"
            elif isinstance(error, GatewayControlError):
                code, message = error.code, error.message or error.code
                retryable = code in ("device_busy", "operation_expired", "gateway_unavailable")
            elif isinstance(error, sqlite3.Error):
                code, retryable = "state_unavailable", True
            elif isinstance(error, OSError):
                code, retryable = "gateway_unavailable", True
            elif isinstance(error, ValueError | TypeError | KeyError):
                code = "invalid_request"
            context.outcome = {
                "state": state,
                "error": {"code": code, "message": message, "retryable": retryable, "type": type(error).__name__},
            }
        self._finish(context)

    def _finish(self, context: JobContext) -> None:
        assert context.outcome is not None
        delay = 0.1
        while True:
            try:
                recorded = self._update(context.job_id, **context.outcome)
                break
            except sqlite3.Error as error:
                self._report(f"recording the outcome of {context.job_id}", error)
                if self._stop.wait(delay):
                    return  # close() records it, or the next server marks the job unknown
                delay = min(delay * 2, 5)
        if not recorded:
            print(f"infuse jobs: {context.job_id} was already closed out; outcome not recorded", file=sys.stderr)
        with self._lock:
            self._current = None

    def close(self, timeout: float = 12) -> None:
        """Stop the worker, waiting up to `timeout` only for an action that may already have been sent."""
        with self._send_lock:
            if self._stop.is_set():
                return
            self._stop.set()
        self._wake.set()
        worker = self._worker
        if worker is not None:
            current = self._current
            worker.join(timeout if current is not None and current.sent else 0.5)
        try:
            with self._lock, self._connection:
                self._close_out(self.instance, self._current)
        except sqlite3.Error as error:
            # Releasing the instance lock below lets the next server close these jobs out instead.
            self._report("closing jobs", error)
        if self._instance_lock is not None:
            path = self._instances / f"{self.instance}.lock"
            _unlock(self._instance_lock)
            os.close(self._instance_lock)
            self._instance_lock = None
            with suppress(OSError):
                path.unlink()
        if worker is None or not worker.is_alive():
            self._connection.close()
