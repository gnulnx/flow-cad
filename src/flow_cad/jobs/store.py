"""Project-local durable job records and append-only progress events."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

from .models import JobEvent, JobRecord, JobState


JOBS_SCHEMA_VERSION = 1


class JobStoreError(RuntimeError):
    pass


class JobNotFoundError(JobStoreError):
    pass


class IdempotencyConflictError(JobStoreError):
    pass


class InvalidJobTransitionError(JobStoreError):
    pass


class UnsupportedJobsSchemaError(JobStoreError):
    pass


class JobStore:
    """Own the durable job journal under a project's ignored ``.flow`` state."""

    def __init__(self, project_root: Path, *, clock: Callable[[], float] = time.time) -> None:
        self.project_root = project_root.resolve()
        self.path = self.project_root / ".flow" / "jobs.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._clock = clock
        self._migrate()

    def create(
        self,
        *,
        request_id: str,
        kind: str,
        payload: Mapping[str, Any] | None = None,
    ) -> tuple[JobRecord, bool]:
        request_id = _required_text(request_id, "request_id")
        kind = _required_text(kind, "kind")
        payload_json = _json_object(payload or {}, "payload")
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM jobs WHERE request_id = ?", (request_id,)
            ).fetchone()
            if existing is not None:
                same_contract = (
                    str(existing["kind"]) == kind
                    and str(existing["payload_json"]) == payload_json
                )
                if not same_contract:
                    raise IdempotencyConflictError(
                        f"request_id already belongs to a different job: {request_id}"
                    )
                return self._record(existing), False

            now_epoch = self._clock()
            now = _timestamp(now_epoch)
            job_id = f"job_{uuid.uuid4().hex}"
            connection.execute(
                """
                INSERT INTO jobs(
                    job_id, request_id, kind, state, phase, progress, message,
                    created_at, created_epoch, updated_at, started_at, finished_at,
                    elapsed_seconds, cancellation_requested, payload_json, result_json, error
                ) VALUES (?, ?, ?, 'queued', 'queued', 0, 'Queued', ?, ?, ?, NULL, NULL,
                          0, 0, ?, NULL, NULL)
                """,
                (job_id, request_id, kind, now, now_epoch, now, payload_json),
            )
            row = self._require(connection, job_id)
            self._event(connection, row, "created")
            return self._record(row), True

    def get(self, job_id: str) -> JobRecord:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise JobNotFoundError(f"job not found: {job_id}")
        return self._record(row)

    def list(self, *, state: JobState | None = None, limit: int = 100) -> tuple[JobRecord, ...]:
        limit = _limit(limit)
        if state is None:
            sql, parameters = "SELECT * FROM jobs ORDER BY created_epoch DESC LIMIT ?", (limit,)
        else:
            sql = "SELECT * FROM jobs WHERE state = ? ORDER BY created_epoch DESC LIMIT ?"
            parameters = (state.value, limit)
        with closing(self._connect()) as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return tuple(self._record(row) for row in rows)

    def events(
        self,
        *,
        job_id: str | None = None,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> tuple[JobEvent, ...]:
        if after_sequence < 0:
            raise JobStoreError("after_sequence must be non-negative")
        limit = _limit(limit)
        if job_id is None:
            sql = "SELECT * FROM job_events WHERE sequence > ? ORDER BY sequence LIMIT ?"
            parameters: tuple[Any, ...] = (after_sequence, limit)
        else:
            sql = (
                "SELECT * FROM job_events WHERE job_id = ? AND sequence > ? "
                "ORDER BY sequence LIMIT ?"
            )
            parameters = (job_id, after_sequence, limit)
        with closing(self._connect()) as connection:
            rows = connection.execute(sql, parameters).fetchall()
        return tuple(self._event_record(row) for row in rows)

    def start(self, job_id: str) -> JobRecord:
        with self._transaction() as connection:
            row = self._require(connection, job_id)
            state = JobState(str(row["state"]))
            if state.terminal:
                return self._record(row)
            if state is not JobState.QUEUED:
                raise InvalidJobTransitionError(f"cannot start {state.value} job: {job_id}")
            if bool(row["cancellation_requested"]):
                return self._transition(
                    connection, row, JobState.CANCELLED, "cancelled", "cancelled",
                    message="Cancelled before start", terminal=True,
                )
            return self._transition(
                connection, row, JobState.RUNNING, "running", "started",
                message="Running", started=True,
            )

    def report(
        self,
        job_id: str,
        *,
        phase: str,
        progress: float,
        message: str | None = None,
    ) -> JobRecord:
        phase = _required_text(phase, "phase")
        progress = _progress(progress)
        with self._transaction() as connection:
            row = self._require(connection, job_id)
            state = JobState(str(row["state"]))
            if state is not JobState.RUNNING:
                raise InvalidJobTransitionError(
                    f"cannot report progress for {state.value} job: {job_id}"
                )
            if bool(row["cancellation_requested"]):
                raise InvalidJobTransitionError(f"job cancellation was requested: {job_id}")
            previous = float(row["progress"])
            if progress < previous:
                raise JobStoreError(f"progress cannot move backwards: {progress} < {previous}")
            return self._transition(
                connection, row, JobState.RUNNING, phase, "progress",
                progress=progress, message=message,
            )

    def request_cancel(self, job_id: str) -> JobRecord:
        with self._transaction() as connection:
            row = self._require(connection, job_id)
            state = JobState(str(row["state"]))
            if state.terminal:
                return self._record(row)
            if state is JobState.QUEUED:
                return self._transition(
                    connection, row, JobState.CANCELLED, "cancelled", "cancelled",
                    message="Cancelled before start", cancellation_requested=True, terminal=True,
                )
            return self._transition(
                connection, row, JobState.RUNNING, "cancelling", "cancellation_requested",
                message="Cancellation requested", cancellation_requested=True,
            )

    def cancellation_requested(self, job_id: str) -> bool:
        return self.get(job_id).cancellation_requested

    def succeed(self, job_id: str, result: Mapping[str, Any] | None = None) -> JobRecord:
        result_json = _json_object(result, "result") if result is not None else None
        with self._transaction() as connection:
            row = self._require(connection, job_id)
            state = JobState(str(row["state"]))
            if state.terminal:
                return self._record(row)
            if state is not JobState.RUNNING:
                raise InvalidJobTransitionError(f"cannot complete {state.value} job: {job_id}")
            if bool(row["cancellation_requested"]):
                return self._transition(
                    connection, row, JobState.CANCELLED, "cancelled", "cancelled",
                    message="Cancelled", terminal=True,
                )
            return self._transition(
                connection, row, JobState.SUCCEEDED, "complete", "succeeded",
                progress=1.0, message="Complete", result_json=result_json, terminal=True,
            )

    def fail(self, job_id: str, error: str) -> JobRecord:
        error = _required_text(error, "error")
        with self._transaction() as connection:
            row = self._require(connection, job_id)
            state = JobState(str(row["state"]))
            if state.terminal:
                return self._record(row)
            if bool(row["cancellation_requested"]):
                return self._transition(
                    connection, row, JobState.CANCELLED, "cancelled", "cancelled",
                    message="Cancelled", terminal=True,
                )
            return self._transition(
                connection, row, JobState.FAILED, "failed", "failed",
                message="Failed", error=error, terminal=True,
            )

    def complete_cancelled(self, job_id: str) -> JobRecord:
        with self._transaction() as connection:
            row = self._require(connection, job_id)
            if JobState(str(row["state"])).terminal:
                return self._record(row)
            return self._transition(
                connection, row, JobState.CANCELLED, "cancelled", "cancelled",
                message="Cancelled", terminal=True,
            )

    def fail_interrupted(self) -> tuple[JobRecord, ...]:
        """Finalize records that cannot survive a runtime process restart."""

        completed: list[JobRecord] = []
        with self._transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE state IN ('queued', 'running') ORDER BY created_epoch"
            ).fetchall()
            for row in rows:
                completed.append(
                    self._transition(
                        connection, row, JobState.FAILED, "interrupted", "interrupted",
                        message="Runtime stopped before the job completed",
                        error="runtime stopped before the job completed; submit a new request to retry",
                        terminal=True,
                    )
                )
        return tuple(completed)

    def _transition(
        self,
        connection: sqlite3.Connection,
        row: sqlite3.Row,
        state: JobState,
        phase: str,
        event_type: str,
        *,
        progress: float | None = None,
        message: str | None,
        cancellation_requested: bool | None = None,
        started: bool = False,
        terminal: bool = False,
        result_json: str | None = None,
        error: str | None = None,
    ) -> JobRecord:
        now_epoch = self._clock()
        now = _timestamp(now_epoch)
        progress = float(row["progress"]) if progress is None else progress
        started_at = now if started and row["started_at"] is None else row["started_at"]
        finished_at = now if terminal else row["finished_at"]
        cancel_flag = (
            bool(row["cancellation_requested"])
            if cancellation_requested is None
            else cancellation_requested
        )
        elapsed = max(0.0, now_epoch - float(row["created_epoch"]))
        connection.execute(
            """
            UPDATE jobs SET state = ?, phase = ?, progress = ?, message = ?, updated_at = ?,
                started_at = ?, finished_at = ?, elapsed_seconds = ?,
                cancellation_requested = ?, result_json = ?, error = ?
            WHERE job_id = ?
            """,
            (
                state.value, phase, progress, message, now, started_at, finished_at, elapsed,
                int(cancel_flag), result_json, error, str(row["job_id"]),
            ),
        )
        updated = self._require(connection, str(row["job_id"]))
        self._event(connection, updated, event_type)
        return self._record(updated)

    def _migrate(self) -> None:
        with self._transaction() as connection:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current > JOBS_SCHEMA_VERSION:
                raise UnsupportedJobsSchemaError(
                    f"jobs schema {current} is newer than supported schema {JOBS_SCHEMA_VERSION}"
                )
            if current == 0:
                connection.executescript(
                    """
                    CREATE TABLE jobs (
                        job_id TEXT PRIMARY KEY,
                        request_id TEXT NOT NULL UNIQUE,
                        kind TEXT NOT NULL,
                        state TEXT NOT NULL CHECK(state IN
                            ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
                        phase TEXT NOT NULL,
                        progress REAL NOT NULL CHECK(progress >= 0 AND progress <= 1),
                        message TEXT,
                        created_at TEXT NOT NULL,
                        created_epoch REAL NOT NULL,
                        updated_at TEXT NOT NULL,
                        started_at TEXT,
                        finished_at TEXT,
                        elapsed_seconds REAL NOT NULL,
                        cancellation_requested INTEGER NOT NULL DEFAULT 0,
                        payload_json TEXT NOT NULL,
                        result_json TEXT,
                        error TEXT
                    );
                    CREATE INDEX idx_jobs_state_created ON jobs(state, created_epoch);
                    CREATE TABLE job_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL UNIQUE,
                        job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
                        event_type TEXT NOT NULL,
                        state TEXT NOT NULL,
                        phase TEXT NOT NULL,
                        progress REAL NOT NULL,
                        message TEXT,
                        elapsed_seconds REAL NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE INDEX idx_job_events_job_sequence
                        ON job_events(job_id, sequence);
                    PRAGMA user_version = 1;
                    """
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _require(connection: sqlite3.Connection, job_id: str) -> sqlite3.Row:
        row = connection.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        if row is None:
            raise JobNotFoundError(f"job not found: {job_id}")
        return row

    @staticmethod
    def _event(connection: sqlite3.Connection, row: sqlite3.Row, event_type: str) -> None:
        connection.execute(
            """
            INSERT INTO job_events(
                event_id, job_id, event_type, state, phase, progress, message,
                elapsed_seconds, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"event_{uuid.uuid4().hex}", row["job_id"], event_type, row["state"],
                row["phase"], row["progress"], row["message"], row["elapsed_seconds"],
                row["updated_at"],
            ),
        )

    @staticmethod
    def _record(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            job_id=str(row["job_id"]), request_id=str(row["request_id"]),
            kind=str(row["kind"]), state=JobState(str(row["state"])),
            phase=str(row["phase"]), progress=float(row["progress"]),
            message=str(row["message"]) if row["message"] is not None else None,
            created_at=str(row["created_at"]), updated_at=str(row["updated_at"]),
            started_at=str(row["started_at"]) if row["started_at"] is not None else None,
            finished_at=str(row["finished_at"]) if row["finished_at"] is not None else None,
            elapsed_seconds=float(row["elapsed_seconds"]),
            cancellation_requested=bool(row["cancellation_requested"]),
            payload=json.loads(str(row["payload_json"])),
            result=json.loads(str(row["result_json"])) if row["result_json"] is not None else None,
            error=str(row["error"]) if row["error"] is not None else None,
        )

    @staticmethod
    def _event_record(row: sqlite3.Row) -> JobEvent:
        return JobEvent(
            sequence=int(row["sequence"]), event_id=str(row["event_id"]),
            job_id=str(row["job_id"]), event_type=str(row["event_type"]),
            state=JobState(str(row["state"])), phase=str(row["phase"]),
            progress=float(row["progress"]),
            message=str(row["message"]) if row["message"] is not None else None,
            elapsed_seconds=float(row["elapsed_seconds"]), updated_at=str(row["updated_at"]),
        )


def _required_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise JobStoreError(f"{field} must not be empty")
    return normalized


def _json_object(value: Mapping[str, Any], field: str) -> str:
    try:
        encoded = json.dumps(dict(value), sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise JobStoreError(f"{field} must be a JSON object") from exc
    if not isinstance(json.loads(encoded), dict):
        raise JobStoreError(f"{field} must be a JSON object")
    return encoded


def _progress(value: float) -> float:
    normalized = float(value)
    if not 0.0 <= normalized <= 1.0:
        raise JobStoreError("progress must be between 0 and 1")
    return normalized


def _limit(value: int) -> int:
    if value < 1 or value > 1000:
        raise JobStoreError("limit must be between 1 and 1000")
    return value


def _timestamp(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=UTC).isoformat()
