from __future__ import annotations

import hashlib
import time
from pathlib import Path
from uuid import UUID

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from flow_cad.cli import flow
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
from flow_cad.viewer.services import InventoryService


def test_part_build_command_is_observable_idempotent_and_publishes_viewer_hashes(
    tmp_path: Path,
) -> None:
    pytest.importorskip("build123d")
    root = _write_project(tmp_path, "api_build_fixture", include_failure=True)
    manifest_path = root / "flowcad.project.yaml"
    manifest_before = manifest_path.read_bytes()
    baseline = root / "migration" / "authority" / "panel.step"
    baseline.parent.mkdir(parents=True)
    baseline.write_bytes(b"immutable-migration-baseline")
    initial_revision = sync_project(root).revision

    with TestClient(
        create_workbench_app(root, enable_default_chat_provider=False)
    ) as client:
        submit_started = time.perf_counter()
        submitted = client.post(
            "/api/workbench/v1/parts/panel/build",
            json={"request_id": "api-panel-1"},
        )
        submit_elapsed = time.perf_counter() - submit_started
        duplicate = client.post(
            "/api/workbench/v1/parts/panel/build",
            json={"request_id": "api-panel-1"},
        )

        assert submitted.status_code == duplicate.status_code == 202
        assert submit_elapsed < 0.250
        assert submitted.json()["created"] is True
        assert duplicate.json()["created"] is False
        job_id = submitted.json()["job"]["job_id"]
        assert duplicate.json()["job"]["job_id"] == job_id
        completed = _wait_for_job(client, job_id)

        events = client.get(
            f"/api/workbench/v1/jobs/{job_id}/events"
        ).json()["events"]
        inventory = client.get("/api/parts").json()
        panel = next(part for part in inventory["parts"] if part["key"] == "panel")

        assert completed["state"] == "succeeded"
        assert completed["result"]["viewer_revision"] == initial_revision + 1
        assert {event["phase"] for event in events} >= {
            "queued",
            "running",
            "resolve",
            "import",
            "parameters",
            "generate",
            "export_step",
            "export_stl",
            "hash",
            "publish",
            "complete",
        }
        artifacts = {
            artifact["kind"]: artifact
            for artifact in completed["result"]["artifacts"]
        }
        assert inventory["revision"] == initial_revision + 1
        assert panel["artifact_revision"] == artifacts["step"]["sha256"]
        assert panel["display_revision"] == artifacts["stl"]["sha256"]
        assert client.get(panel["authority_url"]).content == (
            root / artifacts["step"]["path"]
        ).read_bytes()
        assert client.get(panel["model_url"]).content == (
            root / artifacts["stl"]["path"]
        ).read_bytes()

        repeated = client.post(
            "/api/workbench/v1/parts/panel/build",
            json={"request_id": "api-panel-2"},
        )
        repeated_job = _wait_for_job(client, repeated.json()["job"]["job_id"])
        assert repeated_job["result"]["artifacts"] == completed["result"]["artifacts"]
        assert repeated_job["result"]["artifact_changed"] is False
        assert repeated_job["result"]["viewer_revision"] == initial_revision + 1

        conflict = client.post(
            "/api/workbench/v1/parts/broken/build",
            json={"request_id": "api-panel-1"},
        )
        failed_submission = client.post(
            "/api/workbench/v1/parts/broken/build",
            json={"request_id": "api-broken-1"},
        )
        failed = _wait_for_job(
            client,
            failed_submission.json()["job"]["job_id"],
        )
        missing = client.post(
            "/api/workbench/v1/parts/missing/build",
            json={"request_id": "api-missing-1"},
        )

        assert conflict.status_code == 409
        assert failed_submission.status_code == 202
        assert failed["state"] == "failed"
        assert "intentional fixture failure" in failed["error"]
        assert missing.status_code == 404

    assert manifest_path.read_bytes() == manifest_before
    assert baseline.read_bytes() == b"immutable-migration-baseline"


def test_flow_cad_build_part_uses_replacement_job_and_reuses_request_id(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pytest.importorskip("build123d")
    root = _write_project(tmp_path, "cli_build_fixture", include_failure=False)
    manifest_path = root / "flowcad.project.yaml"
    manifest_before = manifest_path.read_bytes()
    monkeypatch.chdir(root)
    runner = CliRunner()

    first = runner.invoke(
        flow,
        ["cad", "build", "--part", "panel", "--request-id", "cli-panel-1"],
        catch_exceptions=False,
    )
    first_inventory = InventoryService(root).inventory()
    repeated = runner.invoke(
        flow,
        ["cad", "build", "--part", "panel", "--request-id", "cli-panel-1"],
        catch_exceptions=False,
    )
    repeated_inventory = InventoryService(root).inventory()

    assert first.exit_code == repeated.exit_code == 0
    assert "Submitted build job" in first.output
    assert "[generate]" in first.output
    assert "artifact step exports/step/panel.step" in first.output
    assert "artifact stl exports/stl/panel.stl" in first.output
    assert "Reused build job" in repeated.output
    assert first_inventory["revision"] == repeated_inventory["revision"]
    panel = first_inventory["parts"][0]
    assert panel["artifact_revision"] == _sha256(root / "exports/step/panel.step")
    assert panel["display_revision"] == _sha256(root / "exports/stl/panel.stl")
    assert manifest_path.read_bytes() == manifest_before


def test_default_and_handoff_cli_builds_use_strict_project_builder(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pytest.importorskip("build123d")
    root = _write_project(tmp_path, "cli_project_build_fixture", include_failure=False)
    manifest_before = (root / "flowcad.project.yaml").read_bytes()
    monkeypatch.chdir(root)
    runner = CliRunner()

    default = runner.invoke(
        flow,
        ["cad", "build", "--request-id", "cli-project-default"],
        catch_exceptions=False,
    )
    handoff = runner.invoke(
        flow,
        ["cad", "build", "--handoff", "--request-id", "cli-project-handoff"],
        catch_exceptions=False,
    )

    assert default.exit_code == handoff.exit_code == 0
    assert "Submitted project build job" in default.output
    assert "Built 1 active parts" in default.output
    assert "Wrote build report: reports/builds/latest.json" in default.output
    assert "Created exports handoff bundle: handoff/exports.tar.gz" in default.output
    assert "Built 1 active parts" in handoff.output
    assert "Created exports handoff bundle: handoff/exports.tar.gz" in handoff.output
    assert (root / "reports/builds/latest.json").is_file()
    assert (root / "handoff/exports.tar.gz").is_file()
    assert (root / "flowcad.project.yaml").read_bytes() == manifest_before


def test_project_build_api_submits_observable_active_robot_build(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    root = _write_project(tmp_path, "api_project_build_fixture", include_failure=False)
    sync_project(root)

    with TestClient(
        create_workbench_app(root, enable_default_chat_provider=False)
    ) as client:
        submitted = client.post(
            "/api/workbench/v1/build",
            json={
                "request_id": "api-project-1",
                "mode": "default",
                "create_report": True,
                "create_bundle": False,
            },
        )

        assert submitted.status_code == 202
        completed = _wait_for_job(client, submitted.json()["job"]["job_id"])
        assert completed["state"] == "succeeded"
        assert completed["result"]["part_keys"] == ["panel"]
        assert completed["result"]["report_path"] == "reports/builds/latest.json"
        assert completed["result"]["bundle_path"] is None


def _wait_for_job(client: TestClient, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        response = client.get(f"/api/workbench/v1/jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["state"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"job did not complete: {job_id}")


def _write_project(tmp_path: Path, package: str, *, include_failure: bool) -> Path:
    root = tmp_path / package
    root.mkdir()
    package_root = root / package
    package_root.mkdir()
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "params.py").write_text(
        """
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Params:
    width_mm: float = 4.0

def provide_params():
    return Params()
""".lstrip(),
        encoding="utf-8",
    )
    (package_root / "parts.py").write_text(
        """
from build123d import Box

def make_panel(params):
    return Box(params.width_mm, 5.0, 6.0)

def make_broken(_params):
    raise RuntimeError("intentional fixture failure")
""".lstrip(),
        encoding="utf-8",
    )
    parts = [
        ManifestPart(
            uuid=UUID("11111111-1111-4111-8111-111111111111"),
            key="panel",
            aliases=("old_panel",),
            generator=f"{package}.parts:make_panel",
            role=PartRole.PRINTABLE,
            status=PartStatus.ACTIVE,
            artifacts=(
                ArtifactSpec(kind="step", path="exports/step/panel.step"),
                ArtifactSpec(kind="stl", path="exports/stl/panel.stl"),
            ),
        )
    ]
    if include_failure:
        parts.append(
            ManifestPart(
                uuid=UUID("22222222-2222-4222-8222-222222222222"),
                key="broken",
                aliases=(),
                generator=f"{package}.parts:make_broken",
                role=PartRole.PRINTABLE,
                status=PartStatus.ACTIVE,
                artifacts=(
                    ArtifactSpec(kind="step", path="exports/step/broken.step"),
                ),
            )
        )
    manifest = ProjectManifest(
        schema_version=1,
        project_id=package,
        python_package=package,
        parts=tuple(parts),
        assemblies=(),
        parameter_provider=f"{package}.params:provide_params",
    )
    (root / "flowcad.project.yaml").write_text(
        dump_manifest(manifest),
        encoding="utf-8",
    )
    return root


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
