import json
import sqlite3
import subprocess
import sys
import threading
import time

import pytest

from infuse_iot.services.device_operations import DeviceError
from infuse_iot.services.jobs import JobManager
from infuse_iot.socket_comms import GatewayControlError


def wait(jobs, job_id, state="completed"):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = jobs.status(job_id)
        if result["state"] == state:
            return result
        time.sleep(0.01)
    pytest.fail(f"Job never reached {state}: {jobs.status(job_id)}")


def wait_for(condition):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.01)
    pytest.fail("Condition was never met")


def query(directory, statement, *parameters):
    """Use the database as another process would."""
    connection = sqlite3.connect(directory / "jobs.sqlite3")
    try:
        with connection:
            return connection.execute(statement, parameters).fetchall()
    finally:
        connection.close()


def recorder(calls):
    def handler(spec, context):
        calls.append(spec)
        return {}

    return handler


def insert(connection, job_id, state, owner, updated=None, table="jobs_v1"):
    now = time.time()
    with connection:
        connection.execute(
            f"""INSERT INTO {table} (id,request_key,specification,state,created,updated,progress,owner)
            VALUES (?,?,?,?,?,?,'{{}}',?)""",
            (job_id, job_id, json.dumps({"action": "test"}), state, now, now if updated is None else updated, owner),
        )


def test_request_keys_are_durable_and_cannot_change_specification(tmp_path):
    calls = []
    jobs = JobManager(tmp_path)

    def handler(spec, context):
        calls.append(spec)
        return {"done": True}

    jobs.handlers["test"] = handler
    try:
        initial = jobs.submit("unique", {"action": "test", "target": "0x123"})
        wait(jobs, initial["id"])
        assert jobs.submit("unique", {"action": "test", "target": "0x123"})["id"] == initial["id"]
        with pytest.raises(DeviceError) as conflict:
            jobs.submit("unique", {"action": "test", "target": "0x456"})
        assert conflict.value.code == "idempotency_conflict"
    finally:
        jobs.close()
    restored = JobManager(tmp_path)
    try:
        assert restored.status(initial["id"])["result"] == {"done": True}
        assert len(calls) == 1
    finally:
        restored.close()


def test_two_managers_claim_a_job_only_once(tmp_path):
    calls = []
    first, second = JobManager(tmp_path), JobManager(tmp_path)

    def handler(spec, context):
        calls.append(spec)
        return {"done": True}

    for jobs in (first, second):
        jobs.handlers["test"] = handler
    try:
        a = first.submit("same", {"action": "test"})
        b = second.submit("same", {"action": "test"})
        assert a["id"] == b["id"]
        wait(first, a["id"])
        assert len(calls) == 1
    finally:
        first.close()
        second.close()


def test_only_the_accepting_server_runs_its_jobs(tmp_path):
    release, calls = threading.Event(), []
    first = JobManager(tmp_path, gateway="224.1.1.1:8751")
    second = JobManager(tmp_path, gateway="224.1.1.1:9000")

    def handler_for(name):
        def run(spec, context):
            calls.append((name, spec["n"]))
            release.wait(5)
            return {"by": name}

        return run

    first.handlers["test"], second.handlers["test"] = handler_for("first"), handler_for("second")
    try:
        second.start()
        one = first.submit("one", {"action": "test", "n": 1})
        two = first.submit("two", {"action": "test", "n": 2})
        wait_for(lambda: calls)
        # The other server neither steals queued work nor closes out a live server's running job.
        second._recover()
        time.sleep(0.3)
        assert second.status(one["id"])["state"] == "running"
        assert second.status(two["id"])["state"] == "queued"
        release.set()
        assert wait(second, two["id"])["gateway"] == "224.1.1.1:8751"
        assert calls == [("first", 1), ("first", 2)]
    finally:
        release.set()
        first.close()
        second.close()


def test_stop_cancels_unsent_jobs_and_a_later_server_never_runs_them(tmp_path):
    started, release = threading.Event(), threading.Event()
    sent: list[dict] = []
    calls: list[dict] = []
    first = JobManager(tmp_path)

    def connecting(spec, context):
        started.set()
        release.wait(5)
        context.sending()
        sent.append(spec)
        return {}

    first.handlers["test"] = connecting
    running = first.submit("running", {"action": "test", "n": 1})
    assert started.wait(2)
    queued = first.submit("queued", {"action": "test", "n": 2})
    first.close()
    release.set()
    second = JobManager(tmp_path)
    second.handlers["test"] = recorder(calls)
    try:
        second.start()
        time.sleep(0.3)
        for job in (running, queued):
            result = second.status(job["id"])
            assert (result["state"], result["error"]["code"]) == ("cancelled", "server_stopped")
        assert not sent and not calls
    finally:
        second.close()


CHILD = """
import sys, threading
from pathlib import Path
from infuse_iot.services.jobs import JobManager
jobs = JobManager(Path(sys.argv[1]))
jobs.handlers["test"] = lambda spec, context: context.sending() or threading.Event().wait()
running = jobs.submit("running", {"action": "test", "n": 1})
queued = jobs.submit("queued", {"action": "test", "n": 2})
print(running["id"], queued["id"], flush=True)
sys.stdin.read()
"""


def test_jobs_of_a_server_that_exited_abruptly_are_closed_out_not_run(tmp_path):
    calls: list[dict] = []
    jobs = JobManager(tmp_path)
    jobs.handlers["test"] = recorder(calls)
    child = subprocess.Popen(
        [sys.executable, "-c", CHILD, str(tmp_path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )
    try:
        assert child.stdout is not None
        running, queued = child.stdout.readline().split()
        jobs.start()
        wait(jobs, running, "running")
        time.sleep(0.3)
        assert jobs.status(running)["state"] == "running"
        assert jobs.status(queued)["state"] == "queued"
        child.kill()
        child.wait()
        assert wait(jobs, running, "unknown")["error"]["code"] == "interrupted"
        assert wait(jobs, queued, "cancelled")["error"]["code"] == "server_stopped"
        assert not calls
    finally:
        child.kill()
        child.communicate()
        jobs.close()


def test_stop_waits_for_an_acknowledgement_in_flight(tmp_path):
    jobs = JobManager(tmp_path)
    sent = threading.Event()

    def handler(spec, context):
        context.sending()
        sent.set()
        time.sleep(0.3)
        return {"status": "acknowledged"}

    jobs.handlers["test"] = handler
    job = jobs.submit("sent", {"action": "test"})
    assert sent.wait(2)
    jobs.close()
    restored = JobManager(tmp_path)
    try:
        assert restored.status(job["id"])["state"] == "completed"
    finally:
        restored.close()


def test_stop_without_acknowledgement_is_unknown_and_not_overwritten(tmp_path):
    jobs = JobManager(tmp_path)
    sent, release = threading.Event(), threading.Event()

    def handler(spec, context):
        context.sending()
        sent.set()
        release.wait(5)
        return {"status": "acknowledged"}

    jobs.handlers["test"] = handler
    job = jobs.submit("late", {"action": "test"})
    assert sent.wait(2)
    jobs.close(timeout=0.1)
    worker = jobs._worker
    assert worker is not None
    result = jobs.status(job["id"])
    assert (result["state"], result["error"]["code"]) == ("unknown", "interrupted")
    release.set()
    worker.join(2)
    assert not worker.is_alive()
    assert jobs.status(job["id"])["state"] == "unknown"


def test_terminal_states_are_immutable(tmp_path):
    jobs = JobManager(tmp_path)
    release = threading.Event()

    def handler(spec, context):
        release.wait(5)
        return {"status": "acknowledged"}

    jobs.handlers["test"] = handler
    try:
        job = jobs.submit("closed", {"action": "test"})
        wait(jobs, job["id"], "running")
        # Another writer closes the job out while its worker is still running.
        query(tmp_path, "UPDATE jobs_v1 SET state='unknown' WHERE id=?", job["id"])
        release.set()
        wait(jobs, jobs.submit("next", {"action": "test"})["id"])
        assert jobs.status(job["id"])["result"] is None
        assert jobs.cancel(job["id"])["state"] == "unknown"
    finally:
        release.set()
        jobs.close()


def test_queued_cancellation_prevents_execution(tmp_path):
    started, release = threading.Event(), threading.Event()
    jobs = JobManager(tmp_path)
    calls = []

    def handler(spec, context):
        calls.append(spec["target"])
        started.set()
        release.wait(2)
        context.check_cancelled()
        return {"done": True}

    jobs.handlers["test"] = handler
    try:
        first = jobs.submit("first", {"action": "test", "target": "first"})
        assert started.wait(2)
        queued = jobs.submit("second", {"action": "test", "target": "second"})
        assert jobs.cancel(queued["id"])["state"] == "cancelled"
        release.set()
        wait(jobs, first["id"])
        assert calls == ["first"]
    finally:
        release.set()
        jobs.close()


def test_running_cancellation_is_cooperative(tmp_path):
    started = threading.Event()
    jobs = JobManager(tmp_path)

    def handler(spec, context):
        started.set()
        while True:
            context.check_cancelled()
            time.sleep(0.01)

    jobs.handlers["test"] = handler
    try:
        job = jobs.submit("cancel", {"action": "test"})
        assert started.wait(2)
        jobs.cancel(job["id"])
        assert wait(jobs, job["id"], "cancelled")["error"] is None
    finally:
        jobs.close()


@pytest.mark.parametrize(
    "sent,failure,code,retryable",
    [
        (False, OSError("socket closed"), "gateway_unavailable", True),
        (False, GatewayControlError("device_busy", "Another operation is active"), "device_busy", True),
        (False, GatewayControlError("unsupported_capability"), "unsupported_capability", False),
        (False, RuntimeError("/private/secret/path"), "internal_error", False),
        (True, OSError("socket closed"), "internal_error", False),
        (True, GatewayControlError("device_busy"), "internal_error", False),
    ],
)
def test_unexpected_errors_are_failures_only_before_sending(tmp_path, sent, failure, code, retryable):
    jobs = JobManager(tmp_path)

    def handler(spec, context):
        if sent:
            context.sending()
        raise failure

    jobs.handlers["test"] = handler
    try:
        job = jobs.submit("error", {"action": "test"})
        result = wait(jobs, job["id"], "unknown" if sent else "failed")
        assert (result["error"]["code"], result["error"]["retryable"]) == (code, retryable)
        assert "secret" not in json.dumps(result)
    finally:
        jobs.close()


def test_missing_acknowledgement_is_unknown(tmp_path):
    jobs = JobManager(tmp_path)

    def handler(spec, context):
        raise DeviceError("outcome_unknown", "Inspect device state before retrying")

    jobs.handlers["test"] = handler
    try:
        job = jobs.submit("uncertain", {"action": "test"})
        result = wait(jobs, job["id"], "unknown")
        assert result["error"]["code"] == "outcome_unknown"
    finally:
        jobs.close()


def test_worker_survives_storage_errors_and_reports_them(tmp_path):
    jobs = JobManager(tmp_path)
    jobs._connection.execute("PRAGMA busy_timeout=50")
    jobs.handlers["test"] = lambda spec, context: {"done": True}
    insert(jobs._connection, "orphan", "queued", None)
    blocker = sqlite3.connect(tmp_path / "jobs.sqlite3", isolation_level=None)
    try:
        blocker.execute("BEGIN IMMEDIATE")
        jobs.start()
        wait_for(lambda: jobs.health()["last_error"])
        time.sleep(0.3)
        assert jobs.health()["worker_running"]
        assert "locked" in jobs.status("orphan")["worker"]["last_error"]
        blocker.execute("COMMIT")
        assert wait(jobs, "orphan", "cancelled")["error"]["code"] == "server_stopped"
        result = wait(jobs, jobs.submit("after", {"action": "test"})["id"])
        assert result["worker"] == {"worker_running": True, "last_error": None}
    finally:
        blocker.close()
        jobs.close()


def test_outcome_is_recorded_once_storage_recovers(tmp_path):
    jobs = JobManager(tmp_path)
    jobs._connection.execute("PRAGMA busy_timeout=50")
    blocker = sqlite3.connect(tmp_path / "jobs.sqlite3", isolation_level=None, check_same_thread=False)

    def handler(spec, context):
        context.sending()
        # Another writer holds the database as the device acknowledges.
        blocker.execute("BEGIN IMMEDIATE")
        threading.Timer(0.5, blocker.execute, ("COMMIT",)).start()
        return {"status": "acknowledged"}

    jobs.handlers["test"] = handler
    try:
        job = jobs.submit("ack", {"action": "test"})
        wait_for(lambda: jobs.health()["last_error"])
        assert wait(jobs, job["id"])["result"] == {"status": "acknowledged"}
        assert jobs.health()["worker_running"]
    finally:
        jobs.close()
        blocker.close()


PRE_RELEASE_SCHEMA = """CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, specification TEXT NOT NULL,
    state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
    progress TEXT NOT NULL, result TEXT, error TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
    owner TEXT, lease_until REAL)"""


def test_pre_release_jobs_are_left_to_pre_release_servers(tmp_path):
    connection = sqlite3.connect(tmp_path / "jobs.sqlite3")
    connection.execute(PRE_RELEASE_SCHEMA)
    insert(connection, "queued", "queued", None, table="jobs")
    insert(connection, "running", "running", "f" * 32, table="jobs")
    connection.close()
    release = threading.Event()
    jobs = JobManager(tmp_path)
    jobs.handlers["test"] = lambda spec, context: {"released": release.wait(5)}
    try:
        jobs.start()
        with pytest.raises(DeviceError) as missing:
            jobs.status("queued")
        assert missing.value.code == "job_not_found"
        rows = "SELECT id,state FROM jobs ORDER BY id"
        assert query(tmp_path, rows) == [("queued", "queued"), ("running", "running")]
        # The same request key starts a new job, queued behind another.
        first = jobs.submit("first", {"action": "test"})
        wait(jobs, first["id"], "running")
        second = jobs.submit("running", {"action": "test"})
        assert second["id"] != "running" and second["state"] == "queued"
        # A pre-release server still running claims queued jobs and closes out expired ones, in its own table.
        query(tmp_path, "UPDATE jobs SET state='running',owner='old',lease_until=0 WHERE state='queued'")
        query(tmp_path, "UPDATE jobs SET state='unknown' WHERE state='running' AND lease_until < ?", time.time())
        release.set()
        assert wait(jobs, second["id"])["result"] == {"released": True}
        assert query(tmp_path, rows) == [("queued", "unknown"), ("running", "running")]
        assert "gateway" not in [column[1] for column in query(tmp_path, "PRAGMA table_info(jobs)")]
    finally:
        release.set()
        jobs.close()


def test_newer_database_schema_is_refused(tmp_path):
    query(tmp_path, "PRAGMA user_version=2")
    with pytest.raises(RuntimeError, match="newer"):
        JobManager(tmp_path)


def test_old_finished_jobs_are_pruned(tmp_path):
    jobs = JobManager(tmp_path, retention_seconds=60)
    insert(jobs._connection, "old", "completed", None, updated=time.time() - 120)
    insert(jobs._connection, "recent", "completed", None)
    try:
        jobs.start()
        with pytest.raises(DeviceError) as pruned:
            jobs.status("old")
        assert pruned.value.code == "job_not_found"
        assert jobs.status("recent")["state"] == "completed"
    finally:
        jobs.close()
