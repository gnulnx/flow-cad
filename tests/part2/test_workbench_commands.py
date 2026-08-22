from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from flow_cad.bootstrap import init_project
from flow_cad.registry import sync_project
from flow_cad.viewer.api import create_workbench_app


def test_reload_is_fast_and_idempotent_when_manifest_is_unchanged(tmp_path: Path) -> None:
    init_project(tmp_path, project_id="command_fixture")
    initial = sync_project(tmp_path)
    client = TestClient(create_workbench_app(tmp_path))

    first = client.post("/api/reload")
    second = client.post("/api/reload")

    assert first.status_code == second.status_code == 200
    assert first.json()["revision"] == second.json()["revision"] == initial.revision
    assert first.json()["changed"] is second.json()["changed"] is False
    assert first.json()["artifact_revisions"] == {}


def test_refresh_returns_clear_missing_part_error(tmp_path: Path) -> None:
    init_project(tmp_path, project_id="command_fixture")
    sync_project(tmp_path)
    client = TestClient(create_workbench_app(tmp_path))

    response = client.post(
        "/api/refresh",
        json={"part_id": "missing", "force_model_refetch": True},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "part not found: missing"
