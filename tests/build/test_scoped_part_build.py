from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

from flow_cad.build import (
    PartBuildService,
    PartNotBuildableError,
    plan_scoped_part_build,
)
from flow_cad.jobs import JobService, JobState
from flow_cad.registry import sync_project
from flow_cad.sdk import (
    ArtifactSpec,
    ManifestPart,
    PartRole,
    PartStatus,
    ProjectManifest,
    dump_manifest,
)


PART_UUID = UUID("11111111-1111-4111-8111-111111111111")


def test_metadata_only_build_planning_does_not_import_project_or_geometry(
    tmp_path: Path,
) -> None:
    root = _project_root(tmp_path, "metadata_only_build")
    marker = root / "imported.txt"
    _write_package(
        root,
        "metadata_only_build",
        params_source=f"from pathlib import Path\nPath({str(marker)!r}).write_text('params')\n",
        parts_source=f"from pathlib import Path\nPath({str(marker)!r}).write_text('parts')\n",
    )
    manifest = _manifest("metadata_only_build", stl=False)
    (root / "flowcad.project.yaml").write_text(dump_manifest(manifest), encoding="utf-8")
    source_root = Path(__file__).resolve().parents[2] / "src"
    script = """
import sys
from pathlib import Path
from flow_cad.build import PartBuildService
from flow_cad.jobs import JobService

root = Path(sys.argv[1])
with JobService(root, recover_interrupted=False) as jobs:
    plan = PartBuildService(root, jobs).plan("panel")
assert plan.part_key == "panel"
assert "build123d" not in sys.modules
assert not any(name == "OCP" or name.startswith("OCP.") for name in sys.modules)
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.fspath(source_root)

    completed = subprocess.run(
        [sys.executable, "-c", script, os.fspath(root)],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    assert not marker.exists()


def test_scoped_build_writes_fresh_step_and_stl_with_hashes_and_phase_timings(
    tmp_path: Path,
) -> None:
    pytest.importorskip("build123d")
    root = _project_root(tmp_path, "scoped_build_fixture")
    _write_package(
        root,
        "scoped_build_fixture",
        params_source="""
from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class Params:
    width_mm: float = 4.0
    depth_mm: float = 5.0
    height_mm: float = 6.0

def provide_params():
    return Params()
""",
        parts_source="""
from build123d import Box

def make_panel(params):
    return Box(params.width_mm, params.depth_mm, params.height_mm)
""",
    )
    manifest = _manifest("scoped_build_fixture", stl=True)
    (root / "flowcad.project.yaml").write_text(dump_manifest(manifest), encoding="utf-8")
    initial_revision = sync_project(root).revision
    step_path = root / "exports" / "step" / "panel.step"
    stl_path = root / "exports" / "stl" / "panel.stl"
    step_path.parent.mkdir(parents=True)
    stl_path.parent.mkdir(parents=True)
    step_path.write_bytes(b"old-step")
    stl_path.write_bytes(b"old-stl")

    with JobService(root, max_concurrency=1, recover_interrupted=False) as jobs:
        service = PartBuildService(root, jobs)
        submission = service.submit(request_id="build-panel-1", part_key_or_uuid="panel")
        completed = jobs.wait(submission.job.job_id, timeout=20.0)
        events = jobs.events(job_id=submission.job.job_id, limit=100)
        repeated_submission = service.submit(
            request_id="build-panel-2",
            part_key_or_uuid="panel",
        )
        repeated = jobs.wait(repeated_submission.job.job_id, timeout=20.0)

    assert completed.state is JobState.SUCCEEDED
    assert completed.result is not None
    assert completed.result["viewer_revision"] == initial_revision + 1
    assert completed.result["artifact_changed"] is True
    assert repeated.state is JobState.SUCCEEDED
    assert repeated.result is not None
    assert repeated.result["artifacts"] == completed.result["artifacts"]
    assert repeated.result["viewer_revision"] == completed.result["viewer_revision"]
    assert repeated.result["artifact_changed"] is False
    artifacts = completed.result["artifacts"]
    assert isinstance(artifacts, list)
    assert [artifact["kind"] for artifact in artifacts] == ["step", "stl"]
    for artifact in artifacts:
        output = root / artifact["path"]
        content = output.read_bytes()
        assert content
        assert artifact["byte_count"] == len(content)
        assert artifact["sha256"] == hashlib.sha256(content).hexdigest()
    assert step_path.read_bytes() != b"old-step"
    assert stl_path.read_bytes() != b"old-stl"
    timings = completed.result["phase_timings_ms"]
    assert isinstance(timings, dict)
    assert {
        "import_project",
        "load_parameters",
        "generate_geometry",
        "export_step",
        "export_stl",
        "hash_artifacts",
        "publish",
        "total",
    } <= timings.keys()
    phases = {event.phase for event in events}
    assert {"resolve", "parameters", "generate", "export_step", "export_stl", "hash", "publish"} <= phases
    assert not any((root / ".flow" / "build-work").iterdir())


def test_plan_keeps_step_only_build_optional_and_rejects_migration_baseline(
    tmp_path: Path,
) -> None:
    root = _project_root(tmp_path, "step_only_fixture")
    manifest = _manifest("step_only_fixture", stl=False)

    plan = plan_scoped_part_build(root, manifest, manifest.parts[0])

    assert [(artifact.kind, artifact.relative_path) for artifact in plan.artifacts] == [
        ("step", "exports/step/panel.step")
    ]

    baseline = root / "migration" / "authority" / "panel.step"
    baseline.parent.mkdir(parents=True)
    baseline.write_bytes(b"immutable-baseline")
    historical_part = _part(
        generator="step_only_fixture.parts:make_panel",
        artifacts=(ArtifactSpec(kind="step", path="migration/authority/panel.step"),),
    )
    historical_manifest = ProjectManifest(
        schema_version=1,
        project_id="step_only_fixture",
        python_package="step_only_fixture",
        parts=(historical_part,),
        assemblies=(),
        parameter_provider="step_only_fixture.params:provide_params",
    )

    with pytest.raises(PartNotBuildableError, match="under project exports"):
        plan_scoped_part_build(root, historical_manifest, historical_part)
    assert baseline.read_bytes() == b"immutable-baseline"


def test_plan_rejects_outputs_shared_between_parts(tmp_path: Path) -> None:
    root = _project_root(tmp_path, "shared_output_fixture")
    first = _part(generator="shared_output_fixture.parts:make_panel")
    second = ManifestPart(
        uuid=UUID("22222222-2222-4222-8222-222222222222"),
        key="other_panel",
        aliases=(),
        generator="shared_output_fixture.parts:make_other_panel",
        role=PartRole.PRINTABLE,
        status=PartStatus.ACTIVE,
        artifacts=(ArtifactSpec(kind="step", path="exports/step/panel.step"),),
    )
    manifest = ProjectManifest(
        schema_version=1,
        project_id="shared_output_fixture",
        python_package="shared_output_fixture",
        parts=(first, second),
        assemblies=(),
        parameter_provider="shared_output_fixture.params:provide_params",
    )

    with pytest.raises(PartNotBuildableError, match="shared by parts"):
        plan_scoped_part_build(root, manifest, first)


def test_failed_generation_leaves_existing_output_untouched(tmp_path: Path) -> None:
    root = _project_root(tmp_path, "failed_build_fixture")
    _write_package(
        root,
        "failed_build_fixture",
        params_source="def provide_params():\n    return object()\n",
        parts_source="def make_panel(_params):\n    raise RuntimeError('fixture failure')\n",
    )
    manifest = _manifest("failed_build_fixture", stl=False)
    (root / "flowcad.project.yaml").write_text(dump_manifest(manifest), encoding="utf-8")
    sync_project(root)
    output = root / "exports" / "step" / "panel.step"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"known-good")

    with JobService(root, max_concurrency=1, recover_interrupted=False) as jobs:
        service = PartBuildService(root, jobs)
        submission = service.submit(request_id="failed-build", part_key_or_uuid="panel")
        completed = jobs.wait(submission.job.job_id, timeout=10.0)

    assert completed.state is JobState.FAILED
    assert completed.error is not None and "fixture failure" in completed.error
    assert output.read_bytes() == b"known-good"


def _project_root(tmp_path: Path, package: str) -> Path:
    root = tmp_path / package
    root.mkdir()
    return root


def _write_package(
    root: Path,
    package: str,
    *,
    params_source: str,
    parts_source: str,
) -> None:
    package_root = root / package
    package_root.mkdir()
    (package_root / "__init__.py").write_text("", encoding="utf-8")
    (package_root / "params.py").write_text(params_source, encoding="utf-8")
    (package_root / "parts.py").write_text(parts_source, encoding="utf-8")


def _part(
    *,
    generator: str,
    artifacts: tuple[ArtifactSpec, ...] | None = None,
) -> ManifestPart:
    return ManifestPart(
        uuid=PART_UUID,
        key="panel",
        aliases=("old_panel",),
        generator=generator,
        role=PartRole.PRINTABLE,
        status=PartStatus.ACTIVE,
        artifacts=artifacts
        or (
            ArtifactSpec(kind="step", path="exports/step/panel.step"),
        ),
    )


def _manifest(package: str, *, stl: bool) -> ProjectManifest:
    artifacts = [ArtifactSpec(kind="step", path="exports/step/panel.step")]
    if stl:
        artifacts.append(ArtifactSpec(kind="stl", path="exports/stl/panel.stl"))
    return ProjectManifest(
        schema_version=1,
        project_id=package,
        python_package=package,
        parts=(
            _part(
                generator=f"{package}.parts:make_panel",
                artifacts=tuple(artifacts),
            ),
        ),
        assemblies=(),
        parameter_provider=f"{package}.params:provide_params",
    )
