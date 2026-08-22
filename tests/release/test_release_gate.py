from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path
from uuid import UUID

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from flow_cad.cli import flow
from flow_cad.sdk import (
    ArtifactSpec,
    ManifestPart,
    PartRole,
    PartStatus,
    ProjectManifest,
    ReleaseHookKind,
    ReleaseHookSpec,
    dump_manifest,
)
from flow_cad.viewer.api import create_workbench_app


PART_UUID = UUID("11111111-1111-4111-8111-111111111111")


def test_release_endpoint_submits_idempotently_and_cancels_killable_phase(
    tmp_path: Path,
) -> None:
    root = _write_project(tmp_path, "release_cancel", slow_symbol_import=True)

    with TestClient(
        create_workbench_app(root, enable_default_chat_provider=False)
    ) as client:
        started = time.perf_counter()
        submitted = client.post(
            "/api/workbench/v1/release/gate",
            json={"request_id": "release-cancel-1"},
        )
        duplicate = client.post(
            "/api/workbench/v1/release/gate",
            json={"request_id": "release-cancel-1"},
        )

        assert submitted.status_code == duplicate.status_code == 202
        assert time.perf_counter() - started < 0.75
        assert submitted.json()["created"] is True
        assert duplicate.json()["created"] is False
        job_id = submitted.json()["job"]["job_id"]
        assert duplicate.json()["job"]["job_id"] == job_id
        _wait_for_phase(client, job_id, "symbols")

        cancelled = client.post(f"/api/workbench/v1/jobs/{job_id}/cancel")
        completed = _wait_for_job(client, job_id, timeout=6.0)
        events = client.get(f"/api/workbench/v1/jobs/{job_id}/events").json()["events"]

    assert cancelled.status_code == 202
    assert completed["state"] == "cancelled"
    assert {event["phase"] for event in events} >= {
        "manifest_registry",
        "ownership",
        "symbols",
    }
    report = json.loads((root / ".flow/release/latest.json").read_text(encoding="utf-8"))
    assert report["status"] == "cancelled"
    assert report["failed_phase"] == "symbols"


def test_release_failure_report_attributes_strict_manifest_phase(tmp_path: Path) -> None:
    root = _write_project(tmp_path, "release_invalid")
    manifest_path = root / "flowcad.project.yaml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            "parameter_provider: release_invalid.params:provide_params\n",
            "",
        ),
        encoding="utf-8",
    )

    with TestClient(
        create_workbench_app(root, enable_default_chat_provider=False)
    ) as client:
        submitted = client.post(
            "/api/workbench/v1/release/gate",
            json={"request_id": "release-invalid-1"},
        )
        completed = _wait_for_job(client, submitted.json()["job"]["job_id"])

    assert submitted.status_code == 202
    assert completed["state"] == "failed"
    assert "strict manifest must declare parameter_provider" in completed["error"]
    report = json.loads((root / ".flow/release/latest.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["failed_phase"] == "manifest_registry"


@pytest.mark.integration
def test_flow_release_gate_builds_all_active_artifacts_and_writes_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("build123d")
    root = _write_project(tmp_path, "release_real", release_hooks=True, initialize_git=True)
    manifest_path = root / "flowcad.project.yaml"
    manifest_before = manifest_path.read_bytes()
    baseline = root / "migration/authority/panel.step"
    baseline_before = baseline.read_bytes()
    monkeypatch.chdir(root)

    started = time.perf_counter()
    result = CliRunner().invoke(
        flow,
        ["release", "gate", "--request-id", "release-real-1"],
        catch_exceptions=False,
    )
    elapsed = time.perf_counter() - started

    assert result.exit_code == 0, result.output
    assert elapsed < 30.0
    assert "Submitted release gate job" in result.output
    assert "[manifest_registry]" in result.output
    assert "[build:panel:generate]" in result.output
    assert "[hook:validator:focused]" in result.output
    assert "Release gate passed" in result.output

    report_path = root / ".flow/release/latest.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["over_target"] is False
    assert report["hard_timeout_seconds"] == 180.0
    assert report["target_seconds"] == 120.0
    assert report["scoped_part_hard_seconds"] == 15.0
    assert report["project_tests"]["test_file_count"] == 1
    assert [hook["kind"] for hook in report["hooks"]] == [
        "validator",
        "interference",
        "print_manifest",
    ]
    phase_keys = {phase["key"] for phase in report["phases"]}
    assert phase_keys >= {
        "manifest_registry",
        "ownership",
        "symbols",
        "build_active",
        "viewer_index",
        "artifact_manifest",
        "hook:validator:focused",
        "hook:interference:assembly_clearance",
        "hook:print_manifest:print_manifest",
        "project_tests",
        "benchmarks",
        "git_clean",
    }

    artifact_manifest = root / ".flow/release/artifact-manifest.sha256"
    lines = artifact_manifest.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    for artifact in report["artifacts"]:
        output = root / artifact["path"]
        assert artifact["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
        assert artifact["byte_count"] == output.stat().st_size
        assert f"{artifact['sha256']}  {artifact['path']}" in lines
    assert (root / ".flow/release/print-hook.json").is_file()
    assert manifest_path.read_bytes() == manifest_before
    assert baseline.read_bytes() == baseline_before
    assert _git(root, "status", "--porcelain", "--untracked-files=all").stdout == ""

    reused = CliRunner().invoke(
        flow,
        ["release", "gate", "--request-id", "release-real-1", "--json-output"],
        catch_exceptions=False,
    )
    assert reused.exit_code == 0
    assert json.loads(reused.output)["result"]["report_path"] == ".flow/release/latest.json"


@pytest.mark.integration
def test_release_hook_timeout_is_phase_attributed(tmp_path: Path) -> None:
    pytest.importorskip("build123d")
    root = _write_project(
        tmp_path,
        "release_timeout",
        hook_timeout=True,
        initialize_git=True,
    )

    with TestClient(
        create_workbench_app(root, enable_default_chat_provider=False)
    ) as client:
        submitted = client.post(
            "/api/workbench/v1/release/gate",
            json={"request_id": "release-timeout-1"},
        )
        completed = _wait_for_job(client, submitted.json()["job"]["job_id"], timeout=30.0)

    assert completed["state"] == "failed"
    assert "hook:interference:assembly_clearance" in completed["error"]
    assert "exceeded 0.1s timeout" in completed["error"]
    report = json.loads((root / ".flow/release/latest.json").read_text(encoding="utf-8"))
    assert report["status"] == "failed"
    assert report["failed_phase"] == "hook:interference:assembly_clearance"
    hook_phase = next(
        phase
        for phase in report["phases"]
        if phase["key"] == "hook:interference:assembly_clearance"
    )
    assert hook_phase["status"] == "failed"
    assert "ReleaseGateTimeoutError" in hook_phase["error"]


def _write_project(
    tmp_path: Path,
    package: str,
    *,
    slow_symbol_import: bool = False,
    release_hooks: bool = False,
    hook_timeout: bool = False,
    initialize_git: bool = False,
) -> Path:
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
    slow_import = "import time\ntime.sleep(30)\n" if slow_symbol_import else ""
    (package_root / "parts.py").write_text(
        (
            slow_import
            + """
from build123d import Box

def make_panel(params):
    return Box(params.width_mm, 5.0, 6.0)
""".lstrip()
        ),
        encoding="utf-8",
    )
    hooks = ()
    if release_hooks or hook_timeout:
        timeout_source = "import time; time.sleep(30)" if hook_timeout else "return True"
        (package_root / "release_checks.py").write_text(
            f"""
import json
from pathlib import Path

from flow_cad.sdk import ReleaseHookResult

def validate_focused(context):
    return ReleaseHookResult(ok=len(context.artifacts) == 2, summary="fresh artifacts")

def validate_interference(_context):
    {timeout_source}

def write_print_manifest(context):
    path = Path(context.project_root) / ".flow/release/print-hook.json"
    path.write_text(json.dumps({{"artifact_count": len(context.artifacts)}}), encoding="utf-8")
    return {{"ok": True, "summary": "print manifest generated", "details": {{"path": str(path)}}}}
""".lstrip(),
            encoding="utf-8",
        )
        hooks = (
            ReleaseHookSpec(
                key="focused",
                kind=ReleaseHookKind.VALIDATOR,
                provider=f"{package}.release_checks:validate_focused",
            ),
            ReleaseHookSpec(
                key="assembly_clearance",
                kind=ReleaseHookKind.INTERFERENCE,
                provider=f"{package}.release_checks:validate_interference",
                timeout_seconds=0.1 if hook_timeout else 5.0,
            ),
            ReleaseHookSpec(
                key="print_manifest",
                kind=ReleaseHookKind.PRINT_MANIFEST,
                provider=f"{package}.release_checks:write_print_manifest",
            ),
        )
    manifest = ProjectManifest(
        schema_version=1,
        project_id=package,
        python_package=package,
        parts=(
            ManifestPart(
                uuid=PART_UUID,
                key="panel",
                aliases=(),
                generator=f"{package}.parts:make_panel",
                role=PartRole.PRINTABLE,
                status=PartStatus.ACTIVE,
                artifacts=(
                    ArtifactSpec(kind="step", path="exports/step/panel.step"),
                    ArtifactSpec(kind="stl", path="exports/stl/panel.stl"),
                ),
            ),
        ),
        assemblies=(),
        parameter_provider=f"{package}.params:provide_params",
        release_hooks=hooks,
    )
    (root / "flowcad.project.yaml").write_text(dump_manifest(manifest), encoding="utf-8")
    tests_root = root / "tests"
    tests_root.mkdir()
    (tests_root / "test_project.py").write_text(
        f"from {package}.params import provide_params\n\n"
        "def test_parameters_are_positive():\n"
        "    assert provide_params().width_mm > 0\n",
        encoding="utf-8",
    )
    (root / ".gitignore").write_text(
        ".flow/\nexports/\n.pytest_cache/\n__pycache__/\n*.pyc\n",
        encoding="utf-8",
    )
    baseline = root / "migration/authority/panel.step"
    baseline.parent.mkdir(parents=True)
    baseline.write_bytes(b"immutable-migration-baseline")
    if initialize_git:
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "flow-cad-tests@example.invalid")
        _git(root, "config", "user.name", "Flow CAD Tests")
        _git(root, "add", ".")
        _git(root, "commit", "-qm", "fixture baseline")
    return root


def _wait_for_phase(client: TestClient, job_id: str, phase: str) -> dict[str, object]:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        payload = client.get(f"/api/workbench/v1/jobs/{job_id}").json()
        if payload["phase"] == phase:
            return payload
        if payload["state"] in {"succeeded", "failed", "cancelled"}:
            raise AssertionError(f"job became terminal before {phase}: {payload}")
        time.sleep(0.02)
    raise AssertionError(f"job did not reach phase {phase}: {job_id}")


def _wait_for_job(
    client: TestClient,
    job_id: str,
    *,
    timeout: float = 10.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        payload = client.get(f"/api/workbench/v1/jobs/{job_id}").json()
        if payload["state"] in {"succeeded", "failed", "cancelled"}:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"job did not complete: {job_id}")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
