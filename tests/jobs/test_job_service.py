from __future__ import annotations

import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from flow_cad.jobs import (
    IdempotencyConflictError,
    JobService,
    JobState,
    JobStore,
)


def test_submit_is_idempotent_and_events_are_durable_for_sse_polling(tmp_path: Path) -> None:
    release = threading.Event()
    started = threading.Event()
    calls = 0

    def work(context):
        nonlocal calls
        calls += 1
        started.set()
        context.report("prepare", 0.25, "Preparing")
        assert release.wait(timeout=2)
        context.report("write", 0.75, "Writing")
        return {"artifact_hash": "abc123"}

    with JobService(tmp_path, max_concurrency=1) as service:
        before_submit = time.monotonic()
        first = service.submit(
            request_id="request-1",
            kind="display-conversion",
            work=work,
            payload={"part_uuid": "part-1"},
        )
        submit_elapsed = time.monotonic() - before_submit
        assert submit_elapsed < 0.25
        assert started.wait(timeout=1)
        assert service.get(first.job.job_id).state is JobState.RUNNING
        duplicate = service.submit(
            request_id="request-1",
            kind="display-conversion",
            work=lambda _context: pytest.fail("duplicate work ran"),
            payload={"part_uuid": "part-1"},
        )
        assert first.created is True
        assert duplicate.created is False
        assert duplicate.job.job_id == first.job.job_id
        release.set()
        complete = service.wait(first.job.job_id)

        assert calls == 1
        assert complete.state is JobState.SUCCEEDED
        assert complete.phase == "complete"
        assert complete.progress == 1.0
        assert complete.result == {"artifact_hash": "abc123"}
        events = service.events(job_id=first.job.job_id)
        assert [event.event_type for event in events] == [
            "created",
            "started",
            "progress",
            "progress",
            "succeeded",
        ]
        assert all(event.updated_at for event in events)
        assert all(event.elapsed_seconds >= 0 for event in events)
        tail = service.events(after_sequence=events[-2].sequence)
        assert [event.event_type for event in tail] == ["succeeded"]

    reopened = JobStore(tmp_path)
    assert reopened.get(first.job.job_id) == complete
    assert len(reopened.events(job_id=first.job.job_id)) == 5


def test_request_id_conflict_rejects_different_job_contract(tmp_path: Path) -> None:
    with JobService(tmp_path, max_concurrency=1) as service:
        first = service.submit(
            request_id="same-request",
            kind="build",
            payload={"part": "alpha"},
            work=lambda _context: None,
        )
        service.wait(first.job.job_id)
        with pytest.raises(IdempotencyConflictError):
            service.submit(
                request_id="same-request",
                kind="build",
                payload={"part": "beta"},
                work=lambda _context: None,
            )


def test_executor_never_exceeds_configured_concurrency(tmp_path: Path) -> None:
    release = threading.Event()
    two_started = threading.Event()
    lock = threading.Lock()
    running = 0
    maximum_running = 0

    def work(context):
        nonlocal running, maximum_running
        context.report("work", 0.5, "Working")
        with lock:
            running += 1
            maximum_running = max(maximum_running, running)
            if running == 2:
                two_started.set()
        assert release.wait(timeout=3)
        with lock:
            running -= 1
        return None

    with JobService(tmp_path, max_concurrency=2) as service:
        submissions = [
            service.submit(request_id=f"bounded-{index}", kind="test", work=work)
            for index in range(6)
        ]
        assert two_started.wait(timeout=2)
        time.sleep(0.05)
        assert maximum_running == 2
        release.set()
        assert all(service.wait(item.job.job_id).state is JobState.SUCCEEDED for item in submissions)
        assert maximum_running == 2


def test_running_and_queued_jobs_cancel_cooperatively(tmp_path: Path) -> None:
    running_started = threading.Event()
    queued_ran = False

    def running_work(context):
        running_started.set()
        while True:
            context.checkpoint()
            time.sleep(0.005)

    def queued_work(_context):
        nonlocal queued_ran
        queued_ran = True
        return None

    with JobService(tmp_path, max_concurrency=1) as service:
        running = service.submit(request_id="running", kind="test", work=running_work)
        queued = service.submit(request_id="queued", kind="test", work=queued_work)
        assert running_started.wait(timeout=2)

        queued_record = service.cancel(queued.job.job_id)
        assert queued_record.state is JobState.CANCELLED
        assert queued_record.started_at is None
        service.cancel(running.job.job_id)

        assert service.wait(running.job.job_id).state is JobState.CANCELLED
        assert queued_ran is False
        running_events = service.events(job_id=running.job.job_id)
        assert "cancellation_requested" in [event.event_type for event in running_events]
        assert running_events[-1].event_type == "cancelled"


def test_failures_and_restart_interruptions_have_clear_terminal_records(tmp_path: Path) -> None:
    with JobService(tmp_path, max_concurrency=1) as service:
        failed = service.submit(
            request_id="failure",
            kind="test",
            work=lambda _context: (_ for _ in ()).throw(ValueError("bad input")),
        )
        failed_record = service.wait(failed.job.job_id)
        assert failed_record.state is JobState.FAILED
        assert failed_record.phase == "failed"
        assert failed_record.error == "ValueError: bad input"

    store = JobStore(tmp_path)
    interrupted, created = store.create(request_id="interrupted", kind="test")
    assert created is True
    assert store.start(interrupted.job_id).state is JobState.RUNNING

    with JobService(tmp_path, max_concurrency=1) as recovered:
        recovered_record = recovered.get(interrupted.job_id)
        assert recovered_record.state is JobState.FAILED
        assert recovered_record.phase == "interrupted"
        assert "submit a new request" in (recovered_record.error or "")
        assert recovered.events(job_id=interrupted.job_id)[-1].event_type == "interrupted"


def test_joining_live_project_journal_does_not_interrupt_owned_jobs(
    tmp_path: Path,
) -> None:
    started = threading.Event()
    release = threading.Event()

    def work(_context):
        started.set()
        assert release.wait(timeout=2)
        return {"owner": "still-live"}

    with JobService(tmp_path, max_concurrency=1) as owner:
        submitted = owner.submit(request_id="live-owner", kind="test", work=work)
        assert started.wait(timeout=1)
        with JobService(tmp_path, max_concurrency=1) as joined:
            assert joined.get(submitted.job.job_id).state is JobState.RUNNING
            release.set()
            assert owner.wait(submitted.job.job_id).state is JobState.SUCCEEDED


def test_jobs_package_import_does_not_load_cad_kernel(tmp_path: Path) -> None:
    command = [
        sys.executable,
        "-c",
        (
            "import sys; import flow_cad.jobs; "
            "blocked = [name for name in sys.modules "
            "if name == 'build123d' or name.startswith('build123d.') "
            "or name == 'OCP' or name.startswith('OCP.')]; "
            "assert not blocked, blocked"
        ),
    ]
    subprocess.run(command, cwd=tmp_path, check=True, capture_output=True, text=True)
