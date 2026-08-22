"""Bounded in-process execution over the durable job journal."""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, TypeAlias

from .models import JobEvent, JobRecord
from .store import InvalidJobTransitionError, JobStore


JobResult: TypeAlias = Mapping[str, Any] | None
JobWork: TypeAlias = Callable[["JobContext"], JobResult]


class JobCancelled(RuntimeError):
    """Raised at a cooperative cancellation checkpoint."""


@dataclass(frozen=True, slots=True)
class JobSubmission:
    job: JobRecord
    created: bool


@dataclass(slots=True)
class _ActiveJob:
    cancel_event: threading.Event
    future: Future[None] | None = None


class JobContext:
    """The only execution surface a provider- or build-specific worker needs."""

    def __init__(self, job_id: str, store: JobStore, cancel_event: threading.Event) -> None:
        self.job_id = job_id
        self._store = store
        self._cancel_event = cancel_event

    @property
    def cancellation_requested(self) -> bool:
        return self._cancel_event.is_set() or self._store.cancellation_requested(self.job_id)

    def checkpoint(self) -> None:
        if self.cancellation_requested:
            raise JobCancelled(f"job cancelled: {self.job_id}")

    def report(self, phase: str, progress: float, message: str | None = None) -> JobRecord:
        self.checkpoint()
        try:
            return self._store.report(
                self.job_id,
                phase=phase,
                progress=progress,
                message=message,
            )
        except InvalidJobTransitionError:
            self.checkpoint()
            raise


class JobService:
    """Run generic jobs with fixed concurrency and durable observable state.

    One service instance owns the project-local runner. On construction it
    finalizes non-terminal records left by a previous process, so clients see a
    retryable terminal record rather than a permanently running job.
    """

    def __init__(
        self,
        project_root: Path,
        *,
        max_concurrency: int = 2,
        recover_interrupted: bool = True,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self.store = JobStore(project_root)
        if recover_interrupted:
            self.store.fail_interrupted()
        self.max_concurrency = max_concurrency
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrency,
            thread_name_prefix="flow-cad-job",
        )
        self._active: dict[str, _ActiveJob] = {}
        self._lock = threading.RLock()
        self._closed = False

    def submit(
        self,
        *,
        request_id: str,
        kind: str,
        work: JobWork,
        payload: Mapping[str, Any] | None = None,
    ) -> JobSubmission:
        if not callable(work):
            raise TypeError("work must be callable")
        with self._lock:
            if self._closed:
                raise RuntimeError("job service is closed")
            job, created = self.store.create(request_id=request_id, kind=kind, payload=payload)
            if not created:
                return JobSubmission(job=job, created=False)
            active = _ActiveJob(cancel_event=threading.Event())
            self._active[job.job_id] = active
            try:
                active.future = self._executor.submit(self._run, job.job_id, work, active.cancel_event)
            except BaseException as exc:
                self._active.pop(job.job_id, None)
                self.store.fail(job.job_id, f"job dispatch failed: {type(exc).__name__}: {exc}")
                raise
        return JobSubmission(job=self.store.get(job.job_id), created=True)

    def get(self, job_id: str) -> JobRecord:
        return self.store.get(job_id)

    def events(
        self,
        *,
        job_id: str | None = None,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> tuple[JobEvent, ...]:
        return self.store.events(
            job_id=job_id,
            after_sequence=after_sequence,
            limit=limit,
        )

    def cancel(self, job_id: str) -> JobRecord:
        record = self.store.request_cancel(job_id)
        with self._lock:
            active = self._active.get(job_id)
            if active is not None:
                active.cancel_event.set()
                if active.future is not None and active.future.cancel():
                    self._active.pop(job_id, None)
        return self.store.get(job_id) if not record.state.terminal else record

    def wait(self, job_id: str, *, timeout: float = 10.0) -> JobRecord:
        deadline = time.monotonic() + timeout
        while True:
            record = self.store.get(job_id)
            if record.state.terminal:
                return record
            if time.monotonic() >= deadline:
                raise TimeoutError(f"job did not finish within {timeout} seconds: {job_id}")
            time.sleep(0.01)

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = False) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            active_ids = tuple(self._active) if cancel_pending else ()
        for job_id in active_ids:
            self.cancel(job_id)
        self._executor.shutdown(wait=wait, cancel_futures=cancel_pending)

    def __enter__(self) -> "JobService":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.shutdown(wait=True)

    def _run(self, job_id: str, work: JobWork, cancel_event: threading.Event) -> None:
        try:
            record = self.store.start(job_id)
            if record.state.terminal:
                return
            context = JobContext(job_id, self.store, cancel_event)
            context.checkpoint()
            result = work(context)
            context.checkpoint()
            self.store.succeed(job_id, result)
        except JobCancelled:
            self.store.complete_cancelled(job_id)
        except BaseException as exc:
            self.store.fail(job_id, f"{type(exc).__name__}: {exc}")
        finally:
            with self._lock:
                self._active.pop(job_id, None)
