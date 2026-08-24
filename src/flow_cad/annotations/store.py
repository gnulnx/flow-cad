"""Append-only project-local viewport annotation journal."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .models import AnnotationContext, AnnotationEvent, AnnotationMark, AnnotationSnapshot


ANNOTATION_SCHEMA_VERSION = 1
ANNOTATION_EVENT_TYPE = "annotation_snapshot_saved"
_THREAD_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


class AnnotationStoreError(RuntimeError):
    pass


class IdempotencyConflictError(AnnotationStoreError):
    pass


class UnsupportedAnnotationSchemaError(AnnotationStoreError):
    pass


class AnnotationStore:
    """Persist complete review snapshots without mutating prior annotation history."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.path = self.project_root / ".flow" / "annotations.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def save_snapshot(
        self,
        *,
        thread_id: str,
        marks: Sequence[AnnotationMark],
        context: AnnotationContext,
        hidden: bool = False,
        request_id: str | None = None,
    ) -> tuple[AnnotationEvent, bool]:
        thread_id = _validate_thread_id(thread_id)
        durable_request_id = _request_id(request_id)
        marks_tuple = tuple(marks)
        payload_contract = _contract_json(marks_tuple, context, hidden)

        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM annotation_events WHERE request_id = ?",
                (durable_request_id,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["thread_id"]) != thread_id
                    or str(existing["contract_json"]) != payload_contract
                ):
                    raise IdempotencyConflictError(
                        f"request_id already belongs to a different annotation snapshot: "
                        f"{durable_request_id}"
                    )
                return self._event(existing), False

            event_id = f"annotation_event_{uuid.uuid4().hex}"
            snapshot_id = f"annotation_snapshot_{uuid.uuid4().hex}"
            created_at = datetime.now(UTC).isoformat()
            snapshot = AnnotationSnapshot(
                snapshot_id=snapshot_id,
                thread_id=thread_id,
                created_at=created_at,
                hidden=bool(hidden),
                marks=marks_tuple,
                context=context,
            )
            cursor = connection.execute(
                """
                INSERT INTO annotation_events(
                    event_id, request_id, thread_id, event_type, created_at,
                    snapshot_json, contract_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    durable_request_id,
                    thread_id,
                    ANNOTATION_EVENT_TYPE,
                    created_at,
                    _json(snapshot.as_dict()),
                    payload_contract,
                ),
            )
            event = AnnotationEvent(
                sequence=int(cursor.lastrowid),
                event_id=event_id,
                request_id=durable_request_id,
                thread_id=thread_id,
                event_type=ANNOTATION_EVENT_TYPE,
                created_at=created_at,
                snapshot=snapshot,
            )
        return event, True

    def events(
        self,
        thread_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 100,
    ) -> tuple[AnnotationEvent, ...]:
        thread_id = _validate_thread_id(thread_id)
        if after_sequence < 0:
            raise AnnotationStoreError("after_sequence must be non-negative")
        if not 1 <= limit <= 1000:
            raise AnnotationStoreError("limit must be between 1 and 1000")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM annotation_events
                WHERE thread_id = ? AND sequence > ?
                ORDER BY sequence LIMIT ?
                """,
                (thread_id, after_sequence, limit),
            ).fetchall()
        return tuple(self._event(row) for row in rows)

    def latest_snapshot(self, thread_id: str) -> AnnotationSnapshot | None:
        thread_id = _validate_thread_id(thread_id)
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT * FROM annotation_events
                WHERE thread_id = ? ORDER BY sequence DESC LIMIT 1
                """,
                (thread_id,),
            ).fetchone()
        return self._event(row).snapshot if row is not None else None

    def _migrate(self) -> None:
        with self._transaction() as connection:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current > ANNOTATION_SCHEMA_VERSION:
                raise UnsupportedAnnotationSchemaError(
                    f"annotation schema {current} is newer than supported schema "
                    f"{ANNOTATION_SCHEMA_VERSION}"
                )
            if current < 1:
                connection.executescript(
                    """
                    CREATE TABLE annotation_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL UNIQUE,
                        request_id TEXT NOT NULL UNIQUE,
                        thread_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL,
                        contract_json TEXT NOT NULL
                    );
                    CREATE INDEX idx_annotation_events_thread_sequence
                        ON annotation_events(thread_id, sequence);
                    CREATE TRIGGER annotation_events_no_update
                    BEFORE UPDATE ON annotation_events
                    BEGIN
                        SELECT RAISE(ABORT, 'annotation event journal is append-only');
                    END;
                    CREATE TRIGGER annotation_events_no_delete
                    BEFORE DELETE ON annotation_events
                    BEGIN
                        SELECT RAISE(ABORT, 'annotation event journal is append-only');
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
    def _event(row: sqlite3.Row) -> AnnotationEvent:
        payload: Mapping[str, Any] = json.loads(str(row["snapshot_json"]))
        raw_marks = payload.get("marks", [])
        raw_context = payload.get("context", {})
        if not isinstance(raw_marks, list) or not isinstance(raw_context, Mapping):
            raise AnnotationStoreError("stored annotation snapshot is invalid")
        snapshot = AnnotationSnapshot(
            snapshot_id=str(payload["snapshot_id"]),
            thread_id=str(payload["thread_id"]),
            created_at=str(payload["created_at"]),
            hidden=bool(payload["hidden"]),
            marks=tuple(AnnotationMark.from_mapping(mark) for mark in raw_marks),
            context=AnnotationContext.from_mapping(raw_context),
            intent=str(payload.get("intent", "review_intent")),
        )
        return AnnotationEvent(
            sequence=int(row["sequence"]),
            event_id=str(row["event_id"]),
            request_id=str(row["request_id"]),
            thread_id=str(row["thread_id"]),
            event_type=str(row["event_type"]),
            created_at=str(row["created_at"]),
            snapshot=snapshot,
        )


def _validate_thread_id(thread_id: str) -> str:
    normalized = thread_id.strip()
    if not _THREAD_ID.fullmatch(normalized):
        raise AnnotationStoreError(
            "thread_id must contain only letters, numbers, dot, underscore, or dash"
        )
    return normalized


def _request_id(request_id: str | None) -> str:
    if request_id is None:
        return f"annotation_request_{uuid.uuid4().hex}"
    normalized = request_id.strip()
    if not normalized or len(normalized) > 200:
        raise AnnotationStoreError("request_id must contain between 1 and 200 characters")
    return normalized


def _contract_json(
    marks: Sequence[AnnotationMark],
    context: AnnotationContext,
    hidden: bool,
) -> str:
    return _json(
        {
            "hidden": bool(hidden),
            "marks": [mark.as_dict() for mark in marks],
            "context": context.as_dict(),
            "intent": "review_intent",
        }
    )


def _json(payload: Mapping[str, Any]) -> str:
    try:
        return json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise AnnotationStoreError("annotation payload must be finite JSON data") from error
