from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from flow_cad.bootstrap import init_project
from flow_cad.registry import sync_project
from flow_cad.sdk import (
    ArtifactSpec,
    AssemblyOccurrence,
    AssemblySpec,
    ManifestPart,
    PartRole,
    PartStatus,
    ProjectManifest,
    dump_manifest,
)
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
    assert client.get("/api/project").json()["view_state_revision"] == "none"

    response = client.post(
        "/api/refresh",
        json={"part_id": "missing", "force_model_refetch": True},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "part not found: missing"


def test_refresh_places_disposable_preview_at_target_occurrence_without_manifest_edit(tmp_path: Path) -> None:
    target_uuid = UUID("11111111-1111-4111-8111-111111111111")
    preview_uuid = UUID("22222222-2222-4222-8222-222222222222")
    for key in ("target", "preview"):
        step = tmp_path / "exports" / f"{key}.step"
        stl = tmp_path / "exports" / f"{key}.stl"
        step.parent.mkdir(parents=True, exist_ok=True)
        step.write_text(f"ISO-10303-21; {key}\n", encoding="utf-8")
        stl.write_text(f"solid {key}\nendsolid {key}\n", encoding="utf-8")
    manifest = ProjectManifest(
        schema_version=1,
        project_id="preview_fixture",
        python_package="preview_fixture",
        parts=(
            ManifestPart(
                uuid=target_uuid,
                key="target",
                aliases=(),
                generator="preview_fixture.parts:target",
                role=PartRole.PRINTABLE,
                status=PartStatus.ACTIVE,
                material="PETG",
                artifacts=(
                    ArtifactSpec(kind="step", path="exports/target.step"),
                    ArtifactSpec(kind="stl", path="exports/target.stl"),
                ),
            ),
            ManifestPart(
                uuid=preview_uuid,
                key="preview",
                aliases=(),
                generator=".flow/drafts/preview.py:gen_step",
                role=PartRole.INSPECTION,
                status=PartStatus.INSPECTION,
                material="PETG",
                artifacts=(
                    ArtifactSpec(kind="step", path="exports/preview.step"),
                    ArtifactSpec(kind="stl", path="exports/preview.stl"),
                ),
            ),
        ),
        assemblies=(
            AssemblySpec(
                key="active",
                occurrences=(
                    AssemblyOccurrence(
                        id="target_main",
                        part_uuid=target_uuid,
                        translation_mm=(10.0, 20.0, 30.0),
                        rotation_deg=(0.0, 0.0, 90.0),
                    ),
                ),
            ),
        ),
    )
    (tmp_path / "flowcad.project.yaml").write_text(dump_manifest(manifest), encoding="utf-8")
    sync_project(tmp_path)
    client = TestClient(create_workbench_app(tmp_path))

    activated = client.post(
        "/api/refresh",
        json={"part_id": "preview", "replace_part_id": "target"},
    )

    assert activated.status_code == 200
    assert activated.json()["preview_placement"]["target_part_key"] == "target"
    assert client.get("/api/project").json()["view_state_revision"] != "none"
    repeated = client.post(
        "/api/refresh",
        json={"part_id": "preview", "replace_part_id": "target"},
    )
    assert repeated.status_code == 200
    inventory = client.get("/api/parts").json()
    by_key = {part["key"]: part for part in inventory["parts"]}
    assert by_key["target"]["occurrences"] == []
    assert by_key["preview"]["preview_of_uuid"] == str(target_uuid)
    assert by_key["preview"]["occurrences"] == [
        {
            "assembly_key": "active",
            "id": "target_main",
            "translation_mm": [10.0, 20.0, 30.0],
            "rotation_deg": [0.0, 0.0, 90.0],
        }
    ]

    cleared = client.post("/api/refresh", json={"clear_preview": True})

    assert cleared.status_code == 200
    assert cleared.json()["preview_cleared"] is True
    assert client.get("/api/project").json()["view_state_revision"] == "none"
    restored = {part["key"]: part for part in client.get("/api/parts").json()["parts"]}
    assert restored["preview"]["occurrences"] == []
    assert restored["target"]["occurrences"][0]["id"] == "target_main"
