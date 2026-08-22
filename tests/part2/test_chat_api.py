from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from flow_cad.chat import ChatStore
from flow_cad.chat.api import create_chat_command_router, create_chat_query_router


def _client(project_root: Path) -> TestClient:
    store = ChatStore(project_root)
    app = FastAPI()
    app.include_router(create_chat_query_router(store))
    app.include_router(create_chat_command_router(store))
    return TestClient(app)


def test_default_thread_and_incremental_event_query(tmp_path: Path) -> None:
    client = _client(tmp_path)
    listing = client.get("/api/chat/threads")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["threads"][0]["thread_id"] == "default"

    turn = client.post(
        "/api/chat/threads/default/turns",
        json={
            "content": "Inspect this part",
            "request_id": "request-1",
            "context": {
                "selected_part_uuid": "part-1",
                "visible_occurrence_ids": ["part-1-primary"],
                "artifact_hashes": {"part-1": "a" * 64},
                "camera": {"position": [1, 2, 3]},
                "measurements": [{"distance_mm": 2.5}],
                "annotations": [{"kind": "arrow"}],
                "viewport_attachment": {"capture_id": "capture-1"},
                "viewer_revision": "3",
            },
        },
    )
    assert turn.status_code == 202
    payload = turn.json()
    assert [event["event_type"] for event in payload["events"]] == [
        "user_message",
        "assistant_created",
    ]
    assert payload["events"][0]["payload"]["context"]["selected_part_uuid"] == "part-1"

    incremental = client.get("/api/chat/threads/default?after_sequence=1")
    assert incremental.status_code == 200
    assert [event["event_type"] for event in incremental.json()["events"]] == [
        "user_message",
        "assistant_created",
    ]


def test_turn_submission_is_idempotent_and_cancel_is_durable(tmp_path: Path) -> None:
    client = _client(tmp_path)
    request = {"content": "Inspect this part", "request_id": "stable-request"}
    first = client.post("/api/chat/threads/default/turns", json=request)
    repeated = client.post("/api/chat/threads/default/turns", json=request)
    assert first.status_code == repeated.status_code == 202
    assert [event["event_id"] for event in first.json()["events"]] == [
        event["event_id"] for event in repeated.json()["events"]
    ]

    turn_id = first.json()["turn_id"]
    cancelled = client.post(f"/api/chat/threads/default/turns/{turn_id}/cancel")
    assert cancelled.status_code == 202
    assert cancelled.json()["event"]["event_type"] == "turn_cancelled"

    reopened = _client(tmp_path)
    events = reopened.get("/api/chat/threads/default").json()["events"]
    assert events[-1]["event_type"] == "turn_cancelled"


def test_chat_routes_return_clear_not_found_errors(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.get("/api/chat/threads/missing").status_code == 404
    assert (
        client.post(
            "/api/chat/threads/missing/turns",
            json={"content": "hello"},
        ).status_code
        == 404
    )
