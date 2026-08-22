from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from flow_cad.chat import ChatStore, ChatStoreError, ContextPacket


def test_default_thread_is_immediate_and_survives_restart(tmp_path: Path) -> None:
    started = time.perf_counter()
    store = ChatStore(tmp_path)
    elapsed_ms = (time.perf_counter() - started) * 1000

    default = store.get_thread("default")
    assert elapsed_ms < 250
    assert default.title == "Design conversation"
    assert [event.event_type for event in default.events] == ["thread_created"]

    reopened = ChatStore(tmp_path)
    assert len(reopened.list_threads()) == 1
    assert len(reopened.get_thread("default").events) == 1


def test_begin_turn_atomically_records_context_and_optimistic_assistant(tmp_path: Path) -> None:
    store = ChatStore(tmp_path)
    context = ContextPacket(
        selected_part_uuid="part-uuid",
        visible_occurrence_ids=("guard", "motor"),
        artifact_hashes={"part-uuid": "a" * 64},
        camera={"position": [1, 2, 3], "target": [0, 0, 0]},
        measurements=({"id": "m1", "distance_mm": 12.5},),
        annotations=({"id": "a1", "kind": "arrow"},),
        viewport_attachment={"capture_id": "capture-1"},
        viewer_revision="7",
    )

    started = time.perf_counter()
    user, assistant = store.begin_turn(
        "default", "Inspect this clearance", context, request_id="request-1"
    )
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert elapsed_ms < 250
    assert user.turn_id == assistant.turn_id
    assert user.payload["context"] == context.as_dict()
    assert assistant.event_type == "assistant_created"
    assert assistant.payload["status"] == "queued"

    repeated = store.begin_turn(
        "default", "ignored duplicate", ContextPacket(), request_id="request-1"
    )
    assert [event.event_id for event in repeated] == [user.event_id, assistant.event_id]


def test_progress_evidence_failure_and_retry_are_durable_append_only_events(tmp_path: Path) -> None:
    store = ChatStore(tmp_path)
    _, assistant = store.begin_turn("default", "Change the guard", ContextPacket())
    assert assistant.turn_id is not None
    turn_id = assistant.turn_id

    store.append_turn_event(
        "default", turn_id, "assistant_progress", {"phase": "inspect", "elapsed_ms": 4}
    )
    store.append_turn_event(
        "default",
        turn_id,
        "assistant_evidence",
        {
            "commit_id": None,
            "changed_files": [],
            "build_job_id": "build-1",
            "artifact_hashes": {"part-uuid": "b" * 64},
            "viewer_revision": "8",
        },
    )
    store.append_turn_event(
        "default", turn_id, "assistant_failed", {"error": "provider unavailable", "retryable": True}
    )
    store.append_turn_event(
        "default", turn_id, "turn_retry_requested", {"reason": "user"}
    )

    reopened = ChatStore(tmp_path)
    events = reopened.get_thread("default").events
    assert [event.event_type for event in events[-4:]] == [
        "assistant_progress",
        "assistant_evidence",
        "assistant_failed",
        "turn_retry_requested",
    ]
    assert [event.sequence for event in events] == sorted(event.sequence for event in events)

    with sqlite3.connect(reopened.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1


def test_store_rejects_unknown_threads_and_unregistered_events(tmp_path: Path) -> None:
    store = ChatStore(tmp_path)
    with pytest.raises(ChatStoreError, match="not found"):
        store.begin_turn("missing", "hello", ContextPacket())

    _, assistant = store.begin_turn("default", "hello", ContextPacket())
    assert assistant.turn_id is not None
    with pytest.raises(ChatStoreError, match="unsupported"):
        store.append_turn_event("default", assistant.turn_id, "shell_transcript", {})
