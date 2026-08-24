from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from flow_cad.measurement.extractor import extract_step_features
from flow_cad.registry import sync_project
from flow_cad.sdk import (
    ArtifactSpec,
    ManifestPart,
    PartRole,
    PartStatus,
    ProjectManifest,
    dump_manifest,
)
from flow_cad.viewer.api import create_workbench_app


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PART_UUID = "11111111-1111-4111-8111-111111111111"


def _step_project(tmp_path: Path) -> tuple[Path, Path, str]:
    from build123d import Box, export_step

    root = tmp_path / "exact_project"
    step_path = root / "exports" / "step" / "panel.step"
    step_path.parent.mkdir(parents=True)
    export_step(Box(10, 20, 30), step_path)
    digest = hashlib.sha256(step_path.read_bytes()).hexdigest()
    _write_manifest(root, digest, step_path.stat().st_size)
    sync_project(root)
    return root, step_path, digest


def _write_manifest(root: Path, digest: str, byte_count: int) -> None:
    manifest = ProjectManifest(
        schema_version=1,
        project_id="exact_project",
        python_package="exact_project",
        parts=(
            ManifestPart(
                uuid=UUID(PART_UUID),
                key="panel",
                aliases=(),
                generator="exact_project.parts:make_panel",
                role=PartRole.PRINTABLE,
                status=PartStatus.ACTIVE,
                artifacts=(
                    ArtifactSpec(
                        kind="step",
                        path="exports/step/panel.step",
                        sha256=digest,
                        byte_count=byte_count,
                    ),
                ),
            ),
        ),
        assemblies=(),
    )
    (root / "flowcad.project.yaml").write_text(dump_manifest(manifest), encoding="utf-8")


def test_measurement_api_import_does_not_load_cad_kernel(tmp_path: Path) -> None:
    environment = dict(os.environ)
    source_root = str(REPOSITORY_ROOT / "src")
    environment["PYTHONPATH"] = source_root
    command = [
        sys.executable,
        "-c",
        (
            "import sys; import flow_cad.measurement; "
            "import flow_cad.viewer.api.measurement_routes; "
            "blocked = [name for name in sys.modules "
            "if name == 'build123d' or name.startswith('build123d.') "
            "or name == 'OCP' or name.startswith('OCP.')]; "
            "assert not blocked, blocked"
        ),
    ]

    subprocess.run(
        command,
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )


def test_step_extractor_returns_exact_vertices_edges_midpoints_and_circle_centers(
    tmp_path: Path,
) -> None:
    from build123d import Box, Cylinder, export_step

    box_path = tmp_path / "box.step"
    export_step(Box(10, 20, 30), box_path)
    box_revision = hashlib.sha256(box_path.read_bytes()).hexdigest()
    box = extract_step_features(
        box_path,
        part_uuid=PART_UUID,
        artifact_revision=box_revision,
    )

    assert box["quality"] == "exact"
    assert box["geometry_authority"] == "step_kernel"
    assert box["units"] == "mm"
    assert box["feature_counts"] == {
        "vertex": 8,
        "line_edge": 12,
        "edge_midpoint": 12,
        "circle_center": 0,
    }
    line_edges = [feature for feature in box["features"] if feature["kind"] == "line_edge"]
    midpoints = [
        feature for feature in box["features"] if feature["kind"] == "edge_midpoint"
    ]
    assert sorted({round(feature["length_mm"], 6) for feature in line_edges}) == [
        10.0,
        20.0,
        30.0,
    ]
    assert {feature["edge_feature_id"] for feature in midpoints} == {
        feature["id"] for feature in line_edges
    }

    cylinder_path = tmp_path / "cylinder.step"
    export_step(Cylinder(5, 10), cylinder_path)
    cylinder_revision = hashlib.sha256(cylinder_path.read_bytes()).hexdigest()
    cylinder = extract_step_features(
        cylinder_path,
        part_uuid=PART_UUID,
        artifact_revision=cylinder_revision,
    )
    centers = [
        feature for feature in cylinder["features"] if feature["kind"] == "circle_center"
    ]
    assert len(centers) == 2
    assert {tuple(feature["point_mm"]) for feature in centers} == {
        (0.0, 0.0, -5.0),
        (0.0, 0.0, 5.0),
    }
    assert all(feature["radius_mm"] == pytest.approx(5.0) for feature in centers)
    assert all(feature["edge_length_mm"] == pytest.approx(10 * 3.141592653589793) for feature in centers)


def test_cold_query_is_immediate_and_job_publishes_revision_cache(tmp_path: Path) -> None:
    root, step_path, revision = _step_project(tmp_path)
    original_bytes = step_path.read_bytes()
    original_mtime = step_path.stat().st_mtime_ns
    app = create_workbench_app(root)
    client = TestClient(app)

    started = time.perf_counter()
    cold = client.get(
        f"/api/parts/{PART_UUID}/exact-features",
        params={"artifact_revision": revision},
    )
    elapsed = time.perf_counter() - started

    assert cold.status_code == 202
    assert elapsed < 0.250
    assert cold.json()["status"] == "job_required"
    assert cold.json()["job_request"]["kind"] == "exact-feature-extraction"
    assert cold.json()["job_request"]["requires_request_id"] is True

    queued = client.post(
        f"/api/parts/{PART_UUID}/exact-features/jobs",
        json={"request_id": "exact-panel-revision-1", "artifact_revision": revision},
    )
    assert queued.status_code == 202
    assert queued.json()["job"]["kind"] == "exact-feature-extraction"
    job_id = queued.json()["job"]["job_id"]
    assert queued.json()["job_url"] == f"/api/workbench/v1/jobs/{job_id}"
    assert queued.json()["events_url"] == f"/api/workbench/v1/jobs/{job_id}/stream"
    assert queued.json()["cancel_url"] == f"/api/workbench/v1/jobs/{job_id}/cancel"
    complete = app.state.job_service.wait(job_id, timeout=10)
    assert complete.state.value == "succeeded"
    assert client.get(f"/api/workbench/v1/jobs/{job_id}").json()["state"] == "succeeded"

    ready = client.get(
        f"/api/parts/{PART_UUID}/exact-features",
        params={"artifact_revision": revision},
    )
    assert ready.status_code == 200
    payload = ready.json()
    assert payload["status"] == "ready"
    assert payload["cache_hit"] is True
    assert payload["artifact_revision"] == revision
    assert payload["feature_counts"]["vertex"] == 8
    assert payload["feature_counts"]["line_edge"] == 12
    assert payload["feature_counts"]["edge_midpoint"] == 12
    assert step_path.read_bytes() == original_bytes
    assert step_path.stat().st_mtime_ns == original_mtime
    cache_files = list((root / ".flow" / "cache" / "exact-features").rglob("*.json"))
    assert len(cache_files) == 1
    assert not cache_files[0].is_relative_to(root / "exports")

    replacement = step_path.with_suffix(".replacement")
    replacement.write_bytes(original_bytes)
    os.replace(replacement, step_path)
    rebuilt_same_revision = client.get(
        f"/api/parts/{PART_UUID}/exact-features",
        params={"artifact_revision": revision},
    )
    assert rebuilt_same_revision.status_code == 200
    assert rebuilt_same_revision.json()["source_file_identity"]["inode"] == step_path.stat().st_ino

    step_path.write_bytes(original_bytes + b"\nchanged")
    stale_cache = client.get(
        f"/api/parts/{PART_UUID}/exact-features",
        params={"artifact_revision": revision},
    )
    assert stale_cache.status_code == 202
    assert stale_cache.json()["status"] == "job_required"
    app.state.job_service.shutdown()


def test_revision_mismatch_marks_requested_measurement_facts_stale(tmp_path: Path) -> None:
    root, _step_path, current_revision = _step_project(tmp_path)
    app = create_workbench_app(root)
    client = TestClient(app)
    old_revision = "0" * 64

    response = client.get(
        f"/api/parts/{PART_UUID}/exact-features",
        params={"artifact_revision": old_revision},
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail == {
        "code": "artifact_revision_mismatch",
        "message": (
            "artifact revision mismatch: "
            f"requested {old_revision}, current {current_revision}"
        ),
        "stale": True,
        "requested_revision": old_revision,
        "current_revision": current_revision,
    }
    app.state.job_service.shutdown()


def test_changed_step_bytes_fail_worker_without_publishing_cache(tmp_path: Path) -> None:
    root, step_path, revision = _step_project(tmp_path)
    step_path.write_bytes(step_path.read_bytes() + b"\nchanged")
    app = create_workbench_app(root)
    client = TestClient(app)

    queued = client.post(
        f"/api/parts/{PART_UUID}/exact-features/jobs",
        json={"request_id": "corrupt-step", "artifact_revision": revision},
    )

    assert queued.status_code == 202
    complete = app.state.job_service.wait(queued.json()["job"]["job_id"], timeout=5)
    assert complete.state.value == "failed"
    assert "STEP byte count changed" in (complete.error or "")
    assert not list((root / ".flow" / "cache" / "exact-features").rglob("*.json"))
    app.state.job_service.shutdown()
