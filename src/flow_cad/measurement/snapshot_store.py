"""Append-only project-local journal of complete measurement label snapshots."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .snapshot_models import (
    MeasurementLabelState,
    MeasurementSnapshot,
    MeasurementSnapshotEvent,
)


MEASUREMENT_SNAPSHOT_SCHEMA_VERSION = 1
MEASUREMENT_SNAPSHOT_EVENT_TYPE = "measurement_snapshot_saved"
_THREAD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class MeasurementSnapshotStoreError(RuntimeError):
    pass


class MeasurementSnapshotIdempotencyConflictError(MeasurementSnapshotStoreError):
    pass


class UnsupportedMeasurementSnapshotSchemaError(MeasurementSnapshotStoreError):
    pass


class MeasurementSnapshotStore:
    """Persist full current label state without mutating earlier snapshots."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.path = self.project_root / ".flow" / "measurements.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def save_snapshot(
        self,
        *,
        thread_id: str,
        part_uuid: str,
        artifact_revision: str,
        measurements: Sequence[MeasurementLabelState],
        request_id: str,
    ) -> tuple[MeasurementSnapshotEvent, bool]:
        thread_id = _validate_thread_id(thread_id)
        part_uuid = _validate_part_uuid(part_uuid)
        artifact_revision = _validate_artifact_revision(artifact_revision)
        request_id = _validate_request_id(request_id)
        measurements_tuple = tuple(measurements)
        contract_json = _contract_json(artifact_revision, measurements_tuple)

        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM measurement_snapshot_events WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["thread_id"]) != thread_id
                    or str(existing["part_uuid"]) != part_uuid
                    or str(existing["artifact_revision"]) != artifact_revision
                    or str(existing["contract_json"]) != contract_json
                ):
                    raise MeasurementSnapshotIdempotencyConflictError(
                        "request_id already belongs to a different measurement snapshot: "
                        f"{request_id}"
                    )
                return self._event(existing), False

            event_id = f"measurement_event_{uuid.uuid4().hex}"
            snapshot_id = f"measurement_snapshot_{uuid.uuid4().hex}"
            created_at = datetime.now(UTC).isoformat()
            snapshot = MeasurementSnapshot(
                snapshot_id=snapshot_id,
                thread_id=thread_id,
                part_uuid=part_uuid,
                artifact_revision=artifact_revision,
                created_at=created_at,
                measurements=measurements_tuple,
            )
            cursor = connection.execute(
                """
                INSERT INTO measurement_snapshot_events(
                    event_id, request_id, thread_id, part_uuid, artifact_revision,
                    event_type, created_at, snapshot_json, contract_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    request_id,
                    thread_id,
                    part_uuid,
                    artifact_revision,
                    MEASUREMENT_SNAPSHOT_EVENT_TYPE,
                    created_at,
                    _json(snapshot.as_dict()),
                    contract_json,
                ),
            )
            event = MeasurementSnapshotEvent(
                sequence=int(cursor.lastrowid),
                event_id=event_id,
                request_id=request_id,
                thread_id=thread_id,
                part_uuid=part_uuid,
                event_type=MEASUREMENT_SNAPSHOT_EVENT_TYPE,
                created_at=created_at,
                snapshot=snapshot,
            )
        return event, True

    def snapshots(
        self,
        thread_id: str,
        part_uuid: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> tuple[MeasurementSnapshotEvent, ...]:
        thread_id = _validate_thread_id(thread_id)
        part_uuid = _validate_part_uuid(part_uuid)
        if after_sequence < 0:
            raise MeasurementSnapshotStoreError("after_sequence must be non-negative")
        if not 1 <= limit <= 1000:
            raise MeasurementSnapshotStoreError("limit must be between 1 and 1000")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM measurement_snapshot_events
                WHERE thread_id = ? AND part_uuid = ? AND sequence > ?
                ORDER BY sequence LIMIT ?
                """,
                (thread_id, part_uuid, after_sequence, limit),
            ).fetchall()
        return tuple(self._event(row) for row in rows)

    def latest_snapshot(self, thread_id: str, part_uuid: str) -> MeasurementSnapshot | None:
        thread_id = _validate_thread_id(thread_id)
        part_uuid = _validate_part_uuid(part_uuid)
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT * FROM measurement_snapshot_events
                WHERE thread_id = ? AND part_uuid = ?
                ORDER BY sequence DESC LIMIT 1
                """,
                (thread_id, part_uuid),
            ).fetchone()
        return self._event(row).snapshot if row is not None else None

    def _migrate(self) -> None:
        with self._transaction() as connection:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current > MEASUREMENT_SNAPSHOT_SCHEMA_VERSION:
                raise UnsupportedMeasurementSnapshotSchemaError(
                    f"measurement snapshot schema {current} is newer than supported schema "
                    f"{MEASUREMENT_SNAPSHOT_SCHEMA_VERSION}"
                )
            if current < 1:
                connection.executescript(
                    """
                    CREATE TABLE measurement_snapshot_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL UNIQUE,
                        request_id TEXT NOT NULL UNIQUE,
                        thread_id TEXT NOT NULL,
                        part_uuid TEXT NOT NULL,
                        artifact_revision TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL,
                        contract_json TEXT NOT NULL
                    );
                    CREATE INDEX idx_measurement_snapshot_thread_part_sequence
                        ON measurement_snapshot_events(thread_id, part_uuid, sequence);
                    CREATE TRIGGER measurement_snapshot_events_no_update
                    BEFORE UPDATE ON measurement_snapshot_events
                    BEGIN
                        SELECT RAISE(ABORT, 'measurement snapshot journal is append-only');
                    END;
                    CREATE TRIGGER measurement_snapshot_events_no_delete
                    BEFORE DELETE ON measurement_snapshot_events
                    BEGIN
                        SELECT RAISE(ABORT, 'measurement snapshot journal is append-only');
                    END;
                    PRAGMA user_version = 1;
                    """
                )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
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
    def _event(row: sqlite3.Row) -> MeasurementSnapshotEvent:
        payload: Mapping[str, Any] = json.loads(str(row["snapshot_json"]))
        raw_measurements = payload.get("measurements", [])
        if not isinstance(raw_measurements, list):
            raise MeasurementSnapshotStoreError("stored measurement snapshot is invalid")
        snapshot = MeasurementSnapshot(
            snapshot_id=str(payload["snapshot_id"]),
            thread_id=str(payload["thread_id"]),
            part_uuid=str(payload["part_uuid"]),
            artifact_revision=str(payload["artifact_revision"]),
            created_at=str(payload["created_at"]),
            measurements=tuple(
                MeasurementLabelState.from_mapping(measurement)
                for measurement in raw_measurements
            ),
        )
        return MeasurementSnapshotEvent(
            sequence=int(row["sequence"]),
            event_id=str(row["event_id"]),
            request_id=str(row["request_id"]),
            thread_id=str(row["thread_id"]),
            part_uuid=str(row["part_uuid"]),
            event_type=str(row["event_type"]),
            created_at=str(row["created_at"]),
            snapshot=snapshot,
        )


def _validate_thread_id(thread_id: str) -> str:
    normalized = thread_id.strip()
    if not _THREAD_ID.fullmatch(normalized):
        raise MeasurementSnapshotStoreError(
            "thread_id must contain only letters, numbers, dot, underscore, or dash"
        )
    return normalized


def _validate_part_uuid(part_uuid: str) -> str:
    normalized = part_uuid.strip().lower()
    try:
        parsed = uuid.UUID(normalized)
    except ValueError as error:
        raise MeasurementSnapshotStoreError("part_uuid must be a valid UUID") from error
    if str(parsed) != normalized:
        raise MeasurementSnapshotStoreError("part_uuid must be a canonical UUID")
    return normalized


def _validate_artifact_revision(artifact_revision: str) -> str:
    normalized = artifact_revision.strip()
    if _SHA256.fullmatch(normalized) is None:
        raise MeasurementSnapshotStoreError(
            "artifact_revision must contain 64 lowercase hexadecimal characters"
        )
    return normalized


def _validate_request_id(request_id: str) -> str:
    normalized = request_id.strip()
    if not normalized or len(normalized) > 200:
        raise MeasurementSnapshotStoreError(
            "request_id must contain between 1 and 200 characters"
        )
    return normalized


def _contract_json(
    artifact_revision: str,
    measurements: Sequence[MeasurementLabelState],
) -> str:
    return _json(
        {
            "artifact_revision": artifact_revision,
            "measurements": [measurement.as_dict() for measurement in measurements],
        }
    )


def _json(payload: Mapping[str, Any]) -> str:
    try:
        return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise MeasurementSnapshotStoreError(
            "measurement snapshot payload must be finite JSON data"
        ) from error
