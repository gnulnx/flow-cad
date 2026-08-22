from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient

from flow_cad.registry import sync_project
from flow_cad.registry.db import database_path
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


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _project(
    tmp_path: Path,
    *,
    corrupt_after_sync: bool = False,
) -> tuple[Path, bytes, str, bytes, str]:
    root = tmp_path / "workbench_project"
    artifact = root / "exports" / "step" / "panel.step"
    artifact.parent.mkdir(parents=True)
    content = b"ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n"
    artifact.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    display = root / "exports" / "stl" / "panel.stl"
    display.parent.mkdir(parents=True)
    display_content = b"solid panel\nendsolid panel\n"
    display.write_bytes(display_content)
    display_digest = hashlib.sha256(display_content).hexdigest()
    manifest = ProjectManifest(
        schema_version=1,
        project_id="workbench_project",
        python_package="workbench_project",
        parts=(
            ManifestPart(
                uuid=UUID("11111111-1111-4111-8111-111111111111"),
                key="panel",
                aliases=("original_panel",),
                generator="workbench_project.parts:make_panel",
                role=PartRole.PRINTABLE,
                status=PartStatus.ACTIVE,
                material="PETG",
                artifacts=(
                    ArtifactSpec(
                        kind="step",
                        path="exports/step/panel.step",
                        sha256=digest,
                        byte_count=len(content),
                    ),
                    ArtifactSpec(
                        kind="stl",
                        path="exports/stl/panel.stl",
                        sha256=display_digest,
                        byte_count=len(display_content),
                    ),
                ),
            ),
        ),
        assemblies=(
            AssemblySpec(
                key="active",
                occurrences=(
                    AssemblyOccurrence(
                        id="panel_main",
                        part_uuid=UUID("11111111-1111-4111-8111-111111111111"),
                        translation_mm=(1.0, 2.0, 3.0),
                        rotation_deg=(0.0, 90.0, 0.0),
                    ),
                ),
            ),
        ),
    )
    (root / "flowcad.project.yaml").write_text(dump_manifest(manifest), encoding="utf-8")
    sync_project(root)
    if corrupt_after_sync:
        artifact.write_bytes(content.replace(b"HEADER", b"BROKEN"))
    return root, content, digest, display_content, display_digest


def test_workbench_api_import_does_not_load_project_or_cad_kernel() -> None:
    environment = dict(os.environ)
    source_root = str(REPOSITORY_ROOT / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        f"{source_root}{os.pathsep}{existing}" if existing else source_root
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import flow_cad.viewer.api; "
                "print(any(name == 'build123d' or name.startswith('OCP') "
                "for name in sys.modules))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.stdout.strip() == "False"


def test_inventory_is_sqlite_only_and_reports_content_identity(tmp_path: Path) -> None:
    root, _content, digest, _display_content, display_digest = _project(tmp_path)
    index_path = database_path(root)
    before_mtime = index_path.stat().st_mtime_ns
    client = TestClient(create_workbench_app(root))

    project = client.get("/api/project")
    response = client.get("/api/parts", params={"search": "original_panel"})

    assert project.status_code == 200
    assert project.json()["project_id"] == "workbench_project"
    assert project.json()["part_count"] == 1
    assert response.status_code == 200
    payload = response.json()
    assert payload["revision"] == 1
    assert payload["occurrence_count"] == 1
    assert len(payload["manifest_sha256"]) == 64
    part = payload["parts"][0]
    assert part["uuid"] == "11111111-1111-4111-8111-111111111111"
    assert part["aliases"] == ["original_panel"]
    assert part["geometry_authority"] == "step_kernel"
    assert part["quality_label"] == "exact"
    assert part["capabilities"]["exact_measurement"] is True
    assert part["artifact_revision"] == digest
    assert part["authority_url"] == f"/api/models/{digest}"
    assert part["display_revision"] == display_digest
    assert part["model_url"] == f"/api/models/{display_digest}"
    assert part["occurrences"] == [
        {
            "assembly_key": "active",
            "id": "panel_main",
            "translation_mm": [1.0, 2.0, 3.0],
            "rotation_deg": [0.0, 90.0, 0.0],
        }
    ]
    assert index_path.stat().st_mtime_ns == before_mtime
    assert "workbench_project.parts" not in sys.modules


def test_model_endpoint_verifies_and_immutably_serves_exact_step(tmp_path: Path) -> None:
    root, content, digest, display_content, display_digest = _project(tmp_path)
    client = TestClient(create_workbench_app(root))

    response = client.get(f"/api/models/{digest}")

    assert response.status_code == 200
    assert response.content == content
    assert response.headers["content-type"].startswith("model/step")
    assert response.headers["etag"] == f'"{digest}"'
    assert response.headers["x-content-sha256"] == digest
    assert response.headers["x-flow-cad-geometry-authority"] == "step_kernel"
    assert response.headers["x-flow-cad-artifact-kind"] == "step"
    assert "immutable" in response.headers["cache-control"]

    display_response = client.get(f"/api/models/{display_digest}")
    assert display_response.status_code == 200
    assert display_response.content == display_content
    assert display_response.headers["content-type"].startswith("model/stl")
    assert display_response.headers["x-flow-cad-geometry-authority"] == "mesh"
    assert display_response.headers["x-flow-cad-artifact-kind"] == "stl"

    unchanged = client.get(
        f"/api/models/{digest}",
        headers={"If-None-Match": f'W/"{digest}"'},
    )
    assert unchanged.status_code == 304
    assert unchanged.content == b""


def test_model_endpoint_refuses_changed_bytes(tmp_path: Path) -> None:
    root, _content, digest, _display_content, _display_digest = _project(
        tmp_path, corrupt_after_sync=True
    )
    client = TestClient(create_workbench_app(root))

    response = client.get(f"/api/models/{digest}")

    assert response.status_code == 409
    assert "artifact SHA-256 changed" in response.json()["detail"]


def test_health_is_available_before_sync(tmp_path: Path) -> None:
    client = TestClient(create_workbench_app(tmp_path))

    health = client.get("/api/health")
    inventory = client.get("/api/parts")

    assert health.status_code == 200
    assert health.json() == {"status": "needs_sync", "registry_available": False}
    assert inventory.status_code == 503


def test_inventory_http_gate_for_one_thousand_parts(tmp_path: Path) -> None:
    root = tmp_path / "large_workbench"
    root.mkdir()
    parts = tuple(
        ManifestPart(
            uuid=UUID(int=index + 1),
            key=f"part_{index:04d}",
            aliases=(),
            generator=f"large_workbench.parts:make_{index:04d}",
            role=PartRole.PRINTABLE,
            status=PartStatus.ACTIVE,
            artifacts=(
                ArtifactSpec(kind="step", path=f"exports/step/part_{index:04d}.step"),
            ),
        )
        for index in range(1000)
    )
    manifest = ProjectManifest(
        schema_version=1,
        project_id="large_workbench",
        python_package="large_workbench",
        parts=parts,
        assemblies=(),
    )
    (root / "flowcad.project.yaml").write_text(dump_manifest(manifest), encoding="utf-8")
    sync_project(root)
    client = TestClient(create_workbench_app(root))

    started = time.perf_counter()
    response = client.get("/api/parts")
    elapsed = time.perf_counter() - started

    assert response.status_code == 200
    assert len(response.json()["parts"]) == 1000
    assert elapsed < 0.250
