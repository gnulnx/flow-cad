from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from flow_cad.annotations import AnnotationStore
from flow_cad.viewer.api.annotation_routes import create_annotation_router


def _client(project_root: Path) -> TestClient:
    app = FastAPI()
    app.include_router(create_annotation_router(AnnotationStore(project_root)))
    return TestClient(app)


def _request(*, request_id: str = "annotation-1") -> dict[str, object]:
    return {
        "request_id": request_id,
        "hidden": False,
        "marks": [
            {
                "mark_id": "circle-1",
                "kind": "circle",
                "points": [[0.25, 0.25], [0.45, 0.5]],
                "color": "#f0c983",
                "stroke_width": 2,
                "intent": "review_intent",
            },
            {
                "mark_id": "text-1",
                "kind": "text",
                "points": [[0.5, 0.2]],
                "color": "#ffffff",
                "stroke_width": 1,
                "text": "Mounting center",
            },
        ],
        "context": {
            "camera": {"position": [1, 2, 3], "target": [0, 0, 0], "up": [0, 0, 1]},
            "viewport": {
                "width": 1280,
                "height": 720,
                "render_context": "viewport-canvas",
            },
            "artifact_revision": "a" * 64,
            "visible_occurrence_ids": ["guard-main", "motor-left"],
            "viewer_revision": "12",
        },
    }


def test_save_latest_and_incremental_events_preserve_context(tmp_path: Path) -> None:
    client = _client(tmp_path)
    empty = client.get("/api/annotations/threads/default/latest")
    assert empty.status_code == 204

    saved = client.post("/api/annotations/threads/default/snapshots", json=_request())
    assert saved.status_code == 201
    payload = saved.json()
    assert payload["created"] is True
    snapshot = payload["event"]["snapshot"]
    assert snapshot["intent"] == "review_intent"
    assert snapshot["context"]["artifact_revision"] == "a" * 64
    assert snapshot["context"]["visible_occurrence_ids"] == ["guard-main", "motor-left"]
    assert snapshot["marks"][0]["points"] == [[0.25, 0.25], [0.45, 0.5]]

    latest = client.get("/api/annotations/threads/default/latest")
    assert latest.status_code == 200
    assert latest.json()["snapshot_id"] == snapshot["snapshot_id"]

    events = client.get("/api/annotations/threads/default/events?after_sequence=0")
    assert events.status_code == 200
    assert events.json()["count"] == 1
    after = events.json()["events"][0]["sequence"]
    assert (
        client.get(f"/api/annotations/threads/default/events?after_sequence={after}").json()[
            "count"
        ]
        == 0
    )


def test_save_is_idempotent_and_invalid_review_data_is_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    first = client.post("/api/annotations/threads/default/snapshots", json=_request())
    repeated = client.post("/api/annotations/threads/default/snapshots", json=_request())
    assert first.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert repeated.json()["event"]["event_id"] == first.json()["event"]["event_id"]

    changed = _request()
    changed["marks"] = []
    conflict = client.post("/api/annotations/threads/default/snapshots", json=changed)
    assert conflict.status_code == 409

    out_of_range = _request(request_id="out-of-range")
    assert isinstance(out_of_range["marks"], list)
    out_of_range["marks"][0]["points"] = [[-0.1, 0.2], [0.4, 0.5]]
    invalid = client.post("/api/annotations/threads/default/snapshots", json=out_of_range)
    assert invalid.status_code == 400
    assert "normalized" in invalid.json()["detail"]

    topology = _request(request_id="topology")
    assert isinstance(topology["marks"], list)
    topology["marks"][0]["intent"] = "cad_topology"
    assert (
        client.post("/api/annotations/threads/default/snapshots", json=topology).status_code
        == 422
    )
