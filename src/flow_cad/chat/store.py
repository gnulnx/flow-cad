"""Durable append-only chat event storage with explicit schema migrations."""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Mapping

from .models import ChatEvent, ChatThread, ContextPacket


CHAT_SCHEMA_VERSION = 1
DEFAULT_THREAD_ID = "default"
DEFAULT_THREAD_TITLE = "Design conversation"


class ChatStoreError(RuntimeError):
    pass


class ThreadNotFoundError(ChatStoreError):
    pass


class UnsupportedChatSchemaError(ChatStoreError):
    pass


class ChatStore:
    """Append durable events without making the disposable registry authoritative."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.path = self.project_root / ".flow" / "chat.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()
        self.ensure_default_thread()

    def ensure_default_thread(self) -> ChatThread:
        with self._transaction() as connection:
            if not self._thread_exists(connection, DEFAULT_THREAD_ID):
                self._append(
                    connection,
                    thread_id=DEFAULT_THREAD_ID,
                    turn_id=None,
                    event_type="thread_created",
                    payload={"title": DEFAULT_THREAD_TITLE},
                )
        return self.get_thread(DEFAULT_THREAD_ID)

    def create_thread(self, title: str) -> ChatThread:
        normalized_title = title.strip()
        if not normalized_title:
            raise ChatStoreError("thread title must not be empty")
        thread_id = f"thread_{uuid.uuid4().hex}"
        with self._transaction() as connection:
            self._append(
                connection,
                thread_id=thread_id,
                turn_id=None,
                event_type="thread_created",
                payload={"title": normalized_title},
            )
        return self.get_thread(thread_id)

    def list_threads(self) -> tuple[ChatThread, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT thread_id, MIN(sequence) AS first_sequence
                FROM chat_events
                WHERE event_type = 'thread_created'
                GROUP BY thread_id
                ORDER BY first_sequence
                """
            ).fetchall()
        return tuple(self.get_thread(str(row["thread_id"])) for row in rows)

    def get_thread(self, thread_id: str) -> ChatThread:
        events = self.events(thread_id)
        created = next((event for event in events if event.event_type == "thread_created"), None)
        if created is None:
            raise ThreadNotFoundError(f"chat thread not found: {thread_id}")
        title = str(created.payload.get("title") or DEFAULT_THREAD_TITLE)
        return ChatThread(
            thread_id=thread_id,
            title=title,
            created_at=created.created_at,
            updated_at=events[-1].created_at,
            events=events,
        )

    def events(self, thread_id: str, *, after_sequence: int = 0) -> tuple[ChatEvent, ...]:
        with closing(self._connect()) as connection:
            if not self._thread_exists(connection, thread_id):
                raise ThreadNotFoundError(f"chat thread not found: {thread_id}")
            rows = connection.execute(
                """
                SELECT sequence, event_id, thread_id, turn_id, event_type, created_at, payload_json
                FROM chat_events
                WHERE thread_id = ? AND sequence > ?
                ORDER BY sequence
                """,
                (thread_id, after_sequence),
            ).fetchall()
        return tuple(self._event_from_row(row) for row in rows)

    def begin_turn(
        self,
        thread_id: str,
        content: str,
        context: ContextPacket,
        *,
        request_id: str | None = None,
    ) -> tuple[ChatEvent, ChatEvent]:
        """Persist user context and an optimistic assistant row in one transaction."""

        normalized_content = content.strip()
        if not normalized_content:
            raise ChatStoreError("message content must not be empty")
        durable_request_id = request_id.strip() if request_id else f"request_{uuid.uuid4().hex}"
        if not durable_request_id:
            raise ChatStoreError("request_id must not be empty")
        turn_id = f"turn_{uuid.uuid4().hex}"
        with self._transaction() as connection:
            if not self._thread_exists(connection, thread_id):
                raise ThreadNotFoundError(f"chat thread not found: {thread_id}")
            existing = connection.execute(
                """
                SELECT sequence, event_id, thread_id, turn_id, event_type, created_at, payload_json
                FROM chat_events
                WHERE request_id = ?
                ORDER BY sequence
                """,
                (durable_request_id,),
            ).fetchall()
            if existing:
                if len(existing) != 2:
                    raise ChatStoreError(f"incomplete idempotent turn: {durable_request_id}")
                return self._event_from_row(existing[0]), self._event_from_row(existing[1])
            user = self._append(
                connection,
                thread_id=thread_id,
                turn_id=turn_id,
                event_type="user_message",
                payload={"content": normalized_content, "context": context.as_dict()},
                request_id=durable_request_id,
            )
            assistant = self._append(
                connection,
                thread_id=thread_id,
                turn_id=turn_id,
                event_type="assistant_created",
                payload={"status": "queued", "content": ""},
                request_id=durable_request_id,
            )
        return user, assistant

    def append_turn_event(
        self,
        thread_id: str,
        turn_id: str,
        event_type: str,
        payload: Mapping[str, Any],
    ) -> ChatEvent:
        allowed = {
            "assistant_delta",
            "assistant_progress",
            "assistant_evidence",
            "assistant_completed",
            "assistant_failed",
            "turn_cancelled",
            "turn_retry_requested",
        }
        if event_type not in allowed:
            raise ChatStoreError(f"unsupported turn event: {event_type}")
        with self._transaction() as connection:
            if not self._turn_exists(connection, thread_id, turn_id):
                raise ChatStoreError(f"chat turn not found: {turn_id}")
            return self._append(
                connection,
                thread_id=thread_id,
                turn_id=turn_id,
                event_type=event_type,
                payload=dict(payload),
            )

    def _migrate(self) -> None:
        with self._transaction() as connection:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current > CHAT_SCHEMA_VERSION:
                raise UnsupportedChatSchemaError(
                    f"chat schema {current} is newer than supported schema {CHAT_SCHEMA_VERSION}"
                )
            if current < 1:
                connection.executescript(
                    """
                    CREATE TABLE chat_events (
                        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL UNIQUE,
                        thread_id TEXT NOT NULL,
                        turn_id TEXT,
                        request_id TEXT,
                        event_type TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    );
                    CREATE INDEX idx_chat_events_thread_sequence
                        ON chat_events(thread_id, sequence);
                    CREATE INDEX idx_chat_events_turn_sequence
                        ON chat_events(turn_id, sequence);
                    CREATE INDEX idx_chat_events_request
                        ON chat_events(request_id) WHERE request_id IS NOT NULL;
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
    def _thread_exists(connection: sqlite3.Connection, thread_id: str) -> bool:
        row = connection.execute(
            """
            SELECT 1 FROM chat_events
            WHERE thread_id = ? AND event_type = 'thread_created'
            LIMIT 1
            """,
            (thread_id,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _turn_exists(connection: sqlite3.Connection, thread_id: str, turn_id: str) -> bool:
        row = connection.execute(
            """
            SELECT 1 FROM chat_events
            WHERE thread_id = ? AND turn_id = ? AND event_type = 'user_message'
            LIMIT 1
            """,
            (thread_id, turn_id),
        ).fetchone()
        return row is not None

    @staticmethod
    def _append(
        connection: sqlite3.Connection,
        *,
        thread_id: str,
        turn_id: str | None,
        event_type: str,
        payload: Mapping[str, Any],
        request_id: str | None = None,
    ) -> ChatEvent:
        event_id = f"event_{uuid.uuid4().hex}"
        created_at = datetime.now(UTC).isoformat()
        payload_json = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"))
        cursor = connection.execute(
            """
            INSERT INTO chat_events(
                event_id, thread_id, turn_id, request_id, event_type, created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_id, thread_id, turn_id, request_id, event_type, created_at, payload_json),
        )
        return ChatEvent(
            sequence=int(cursor.lastrowid),
            event_id=event_id,
            thread_id=thread_id,
            turn_id=turn_id,
            event_type=event_type,
            created_at=created_at,
            payload=dict(payload),
        )

    @staticmethod
    def _event_from_row(row: sqlite3.Row) -> ChatEvent:
        return ChatEvent(
            sequence=int(row["sequence"]),
            event_id=str(row["event_id"]),
            thread_id=str(row["thread_id"]),
            turn_id=str(row["turn_id"]) if row["turn_id"] is not None else None,
            event_type=str(row["event_type"]),
            created_at=str(row["created_at"]),
            payload=json.loads(str(row["payload_json"])),
        )
