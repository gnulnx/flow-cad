from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from flow_cad.annotations import AnnotationStore
from flow_cad.viewer.api import create_workbench_app


def test_workbench_mounts_project_local_annotation_store_and_routes(tmp_path: Path) -> None:
    app = create_workbench_app(tmp_path)
    client = TestClient(app)

    assert isinstance(app.state.annotation_store, AnnotationStore)
    assert app.state.annotation_store.project_root == tmp_path.resolve()
    assert client.get("/api/annotations/threads/default/latest").status_code == 204

    saved = client.post(
        "/api/annotations/threads/default/snapshots",
        json={
            "request_id": "integrated-annotation-1",
            "hidden": False,
            "marks": [
                {
                    "mark_id": "arrow-1",
                    "kind": "arrow",
                    "points": [[0.1, 0.2], [0.8, 0.7]],
                    "color": "#79cbd1",
                    "stroke_width": 2,
                    "intent": "review_intent",
                }
            ],
            "context": {
                "camera": {
                    "position": [120, 80, 60],
                    "up": [0, 0, 1],
                    "quaternion": [0, 0, 0, 1],
                },
                "viewport": {
                    "width": 1280,
                    "height": 720,
                    "render_context": "viewport-canvas",
                },
                "artifact_revision": "step-sha",
                "visible_occurrence_ids": ["guard-main"],
                "viewer_revision": "9",
            },
        },
    )

    assert saved.status_code == 201
    snapshot = saved.json()["event"]["snapshot"]
    assert snapshot["thread_id"] == "default"
    assert snapshot["context"]["viewer_revision"] == "9"
    assert (tmp_path / ".flow" / "annotations.sqlite3").is_file()
