#!/usr/bin/env python3
from __future__ import annotations

import itertools
import json
import inspect
import subprocess
import sys
from collections.abc import Iterable
import rich_click as click
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

from flow_cad.core.exporter import Exporter
from flow_cad.core.cache import latest_build_metadata, list_component_cache, params_as_json, write_active_cache
from flow_cad.core.metadata import definition_export_subdir
from flow_cad.core.report import write_report
from flow_cad.core.bundler import create_bundle
from flow_cad.project import _call_with_supported_kwargs, load_project
from flow_cad.urdf_export import UrdfExportError, UrdfExportService
from flow_cad.validation.contracts import GeometryAuthority, ValidatorMetadata, coerce_validator_result
from flow_cad.validation.facts import ValidationFactProvider
from flow_cad.viewer.service import ConversionUnavailableError, ViewerService
from flow_cad.profiler import (
    FlowCadProfiler,
    format_profile_summary,
    latest_build_profile_path,
    load_latest_build_profile,
    write_build_profile,
)

def assert_printable(name: str, shape) -> None:
    bb = shape.bounding_box()
    dims = (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
    if any(dim > 256.05 for dim in dims):
        rounded = tuple(round(d, 2) for d in dims)
        raise ValueError(f"{name} exceeds 256 mm build volume: {rounded}")


def _context_command(ctx: click.Context) -> str:
    names: list[str] = []
    current: click.Context | None = ctx
    while current is not None:
        if current.info_name:
            names.append(current.info_name)
        current = current.parent
    return " ".join(reversed(names))


def _definition_metadata(definition) -> dict[str, str]:
    return {
        "module_id": str(getattr(definition, "module_id", "")),
        "role": str(getattr(definition, "role", "")),
        "filename": str(getattr(definition, "filename", "")),
        "version": str(getattr(definition, "version", "") or ""),
        "family": str(getattr(definition, "family", "") or ""),
    }


def _build_parts_for_definitions(params, definitions, profiler: FlowCadProfiler) -> dict[str, object]:
    parts: dict[str, object] = {}
    for definition in definitions:
        with profiler.measure(
            "part_generation",
            definition.id,
            part_id=definition.id,
            metadata=_definition_metadata(definition),
        ):
            parts[definition.id] = definition.factory(params)
    return parts


def _find_part_definition(project, part_id: str | None):
    if not part_id:
        return None
    for definition in project.iter_part_definitions():
        if definition.id == part_id:
            return definition
    return None


def _definition_source_paths(definition, project) -> tuple[Path, ...]:
    sources: list[Path] = []
    raw_source = inspect.getsourcefile(getattr(definition, "factory", None))
    if raw_source:
        sources.append(Path(raw_source).resolve())
    for wrapper in getattr(project, "source_wrapper_files", ()):
        sources.append(Path(wrapper).resolve())
    return tuple(sorted({path for path in sources if path.exists()}))


def _definition_changed_since(definition, project, compiled_at: float | None) -> bool:
    if compiled_at is None:
        return True
    source_paths = _definition_source_paths(definition, project)
    if not source_paths:
        return True
    for source_path in source_paths:
        try:
            if source_path.stat().st_mtime > compiled_at:
                return True
        except OSError:
            return True
    return False


def _params_changed_since(params, latest_metadata: object | None) -> bool:
    if latest_metadata is None:
        return True
    try:
        return str(getattr(latest_metadata, "parameters_json", "")) != params_as_json(params)
    except Exception:
        return True


def _expected_artifact_paths(exporter: Exporter, definition) -> tuple[Path, Path]:
    module_id = definition_export_subdir(definition)
    step_path = exporter.step_dir / module_id / definition.filename
    stl_path = exporter.stl_dir / module_id / f"{Path(definition.filename).stem}.stl"
    return step_path, stl_path


def _artifact_cache_reason(
    definition,
    project,
    exporter: Exporter,
    *,
    build_mode: str,
    artifact: str,
    previous_compiled_at: float | None,
    cached_row: object | None,
    params_changed: bool,
) -> str:
    if build_mode != "changed":
        return "full_build"
    if cached_row is None:
        return "not_in_active_cache"
    if previous_compiled_at is None:
        return "no_previous_build"
    if artifact not in {"step", "stl"}:
        return "invalid_artifact"

    step_path, stl_path = _expected_artifact_paths(exporter, definition)
    artifact_path = step_path if artifact == "step" else stl_path
    if not artifact_path.exists():
        return "artifact_missing"
    try:
        artifact_mtime = artifact_path.stat().st_mtime
    except OSError:
        return "artifact_source_unknown"

    if artifact == "stl":
        try:
            if step_path.stat().st_mtime > artifact_path.stat().st_mtime:
                return "artifact_stale"
        except OSError:
            return "artifact_source_unknown"

    if params_changed:
        return "params_changed"

    if _definition_changed_since(definition, project, previous_compiled_at):
        return "source_changed"

    for source_path in _definition_source_paths(definition, project):
        try:
            if artifact_mtime < source_path.stat().st_mtime:
                return "artifact_stale"
        except OSError:
            return "artifact_source_unknown"

    return "cache_hit"


def _changed_definition_cache_reasons(
    definition,
    project,
    exporter: Exporter,
    *,
    previous_compiled_at: float | None,
    cached_row: object | None,
    params_changed: bool,
) -> tuple[str, str]:
    step_reason = _artifact_cache_reason(
        definition,
        project,
        exporter,
        build_mode="changed",
        artifact="step",
        previous_compiled_at=previous_compiled_at,
        cached_row=cached_row,
        params_changed=params_changed,
    )
    stl_reason = _artifact_cache_reason(
        definition,
        project,
        exporter,
        build_mode="changed",
        artifact="stl",
        previous_compiled_at=previous_compiled_at,
        cached_row=cached_row,
        params_changed=params_changed,
    )
    return step_reason, stl_reason


def _changed_definition_needs_rebuild(step_reason: str, stl_reason: str, *, effective_stl: bool) -> bool:
    if step_reason != "cache_hit":
        return True
    return effective_stl and stl_reason != "cache_hit"


def _bounds_overlap(a, b) -> bool:
    return not (
        a.max.X < b.min.X
        or a.min.X > b.max.X
        or a.max.Y < b.min.Y
        or a.min.Y > b.max.Y
        or a.max.Z < b.min.Z
        or a.min.Z > b.max.Z
    )


def _bbox_overlaps(shape_a, shape_b) -> bool:
    try:
        a = shape_a.bounding_box()
        b = shape_b.bounding_box()
    except Exception:
        return False
    return _bounds_overlap(a, b)


def _part_cache_events_for_skipped_definition(
    profiler: FlowCadProfiler,
    exporter: Exporter,
    definition,
    step_cache_reason: str,
    stl_cache_reason: str,
    *,
    effective_stl: bool,
) -> None:
    filename = definition.filename
    metadata = {
        "path": str(_expected_artifact_paths(exporter, definition)[0]),
        "module_id": str(definition_export_subdir(definition)),
        "artifact_cache_status": "hit",
        "artifact_cache_reason": step_cache_reason,
    }
    profiler.record_skip(
        "step_export",
        filename,
        part_id=definition.id,
        reason=step_cache_reason,
        metadata=metadata,
    )
    if effective_stl:
        metadata = {
            "path": str(_expected_artifact_paths(exporter, definition)[1]),
            "module_id": str(definition_export_subdir(definition)),
            "artifact_cache_status": "hit",
            "artifact_cache_reason": stl_cache_reason,
        }
        profiler.record_skip(
            "stl_export",
            filename.replace(".step", ".stl"),
            part_id=definition.id,
            reason=stl_cache_reason,
            metadata=metadata,
        )
    else:
        metadata = {
            "path": str(_expected_artifact_paths(exporter, definition)[1]),
            "module_id": str(definition_export_subdir(definition)),
            "artifact_cache_status": "skipped",
            "artifact_cache_reason": "stl_disabled",
        }
        profiler.record_skip(
            "stl_export",
            filename.replace(".step", ".stl"),
            part_id=definition.id,
            reason="stl_disabled",
            metadata=metadata,
        )


def _refresh_viewer_cache(
    project,
    params,
    profiler: FlowCadProfiler,
    definitions: Iterable[object],
) -> None:
    definitions = list(definitions)
    if not definitions:
        profiler.record_skip("viewer_cache_update", "viewer cache", reason="no_parts")
        return

    metadata = {
        "requested_parts": len(definitions),
        "model_cache_refreshed": 0,
        "missing_parts": 0,
        "failed_parts": 0,
    }
    with profiler.measure(
        "viewer_cache_update",
        "refresh viewer cache",
        metadata=metadata,
    ):
        service = ViewerService(project=project, params=params)
        refreshed = 0
        missing = 0
        failed = 0
        for definition in definitions:
            part_id = definition.id
            try:
                service.model_path(part_id)
                service.snap_features(part_id)
                refreshed += 1
            except ConversionUnavailableError:
                failed += 1
                continue
            except FileNotFoundError:
                missing += 1
                continue
            except Exception:
                failed += 1
                continue
        metadata["model_cache_refreshed"] = refreshed
        metadata["missing_parts"] = missing
        metadata["failed_parts"] = failed
        if missing:
            metadata["reason"] = "parts_missing"
        elif failed:
            metadata["reason"] = "cache_conversion_failed"


def _run_interference_check(parts: dict[str, object], profiler: FlowCadProfiler) -> None:
    if len(parts) < 2:
        profiler.record_skip(
            "interference_check",
            "aabb pairs",
            reason="insufficient_parts",
            metadata={"part_count": len(parts)},
        )
        return

    metadata = {
        "part_count": len(parts),
        "pair_count": 0,
        "overlapping_pair_count": 0,
        "interfering_pairs": [],
        "bounding_box_failure_count": 0,
    }
    with profiler.measure(
        "interference_check",
        "part pairs",
        metadata=metadata,
    ):
        pair_count = 0
        overlap_count = 0
        pair_names: list[str] = []
        ids = sorted(parts.keys())
        bounding_boxes: dict[str, object] = {}
        for part_id in ids:
            try:
                bounding_boxes[part_id] = parts[part_id].bounding_box()
            except Exception:
                continue
        for first, second in itertools.combinations(ids, 2):
            pair_count += 1
            first_box = bounding_boxes.get(first)
            second_box = bounding_boxes.get(second)
            if first_box is not None and second_box is not None and _bounds_overlap(first_box, second_box):
                overlap_count += 1
                pair_names.append(f"{first}↔{second}")
        metadata["pair_count"] = pair_count
        metadata["overlapping_pair_count"] = overlap_count
        metadata["interfering_pairs"] = pair_names[:20]
        metadata["bounding_box_failure_count"] = len(parts) - len(bounding_boxes)


def _run_project_validators(
    project,
    profiler: FlowCadProfiler,
    params,
    parts: dict[str, object],
    report_definitions: list[object],
    build_mode: str,
) -> None:
    validators = list(project.iter_validators())
    if not validators:
        profiler.record_skip(
            "validator",
            "project validators",
            reason="no_validators",
            metadata={"build_mode": build_mode},
        )
        return

    for name, validator in validators:
        validator_metadata = ValidatorMetadata.from_any(getattr(validator, "validator_metadata", None), default_id=name)
        event_metadata = {
            "build_mode": build_mode,
            "part_count": len(parts),
            "validator_count": len(validators),
            "validator_id": validator_metadata.id,
            "family": validator_metadata.family,
            "mode": validator_metadata.mode,
            "budget_ms": validator_metadata.budget_ms,
        }
        with profiler.measure(
            "validator",
            name,
            part_id=name,
            metadata=event_metadata,
        ):
            validator_result = _call_with_supported_kwargs(
                validator,
                _project=project,
                project=project,
                params=params,
                parts=parts,
                definitions=report_definitions,
                facts=ValidationFactProvider(project, params=params),
            )
            report = coerce_validator_result(
                validator_result,
                validator_metadata,
                default_family=validator_metadata.family,
                default_geometry_authority=GeometryAuthority.UNKNOWN,
            )
            event_metadata.update(report.profile_metadata(part_id=name))
            if not report.ok:
                raise click.ClickException(f"Validator {name!r} reported {report.error_count} error(s).")


def _run_project_tests(project, profiler: FlowCadProfiler, *, run_tests: bool) -> None:
    test_path = project.root / "tests"
    if not run_tests:
        profiler.record_skip("project_tests", "pytest", reason="not_requested")
        return
    if not test_path.exists():
        profiler.record_skip("project_tests", "pytest", reason="tests_missing")
        return
    test_files = [
        path
        for pattern in ("test_*.py", "*_test.py")
        for path in test_path.rglob(pattern)
        if path.is_file()
    ]
    if not test_files:
        profiler.record_skip("project_tests", "pytest", reason="tests_missing")
        return

    command = [sys.executable, "-m", "pytest", str(test_path)]
    with profiler.measure("project_tests", "pytest", metadata={"command": " ".join(command)}):
        result = subprocess.run(command, cwd=project.root)
    if result.returncode != 0:
        raise click.ClickException("Project tests failed.")


def _build_profile_parts(project, profile: str, include_references: bool) -> list:
    return list(project.iter_part_definitions_for_profile(profile, include_references=include_references))


def _resolve_build_mode(
    *,
    handoff: bool,
    part: str | None,
    changed: bool,
    assembly_preview: bool,
) -> str:
    if sum((bool(part), bool(changed), bool(assembly_preview), bool(handoff))) > 1:
        raise click.ClickException(
            "Choose one build profile mode only: --part, --changed, --assembly-preview, or --handoff."
        )
    if handoff:
        return "handoff"
    if part:
        return "part"
    if changed:
        return "changed"
    if assembly_preview:
        return "assembly-preview"
    return "default"


def _replacement_project_root(start: Path) -> Path | None:
    """Return a strict SDK-manifest root while leaving legacy manifests alone."""

    from flow_cad.registry import find_manifest
    from flow_cad.sdk import ManifestError, load_manifest

    try:
        manifest_path = find_manifest(start)
        load_manifest(manifest_path)
    except (ManifestError, OSError, RuntimeError):
        return None
    return manifest_path.parent


def _run_replacement_part_build(
    project_root: Path,
    *,
    part: str,
    request_id: str | None,
) -> None:
    """Run the replacement job with visible phase progress for CLI callers."""

    import time
    import uuid

    from flow_cad.build import BuildContractError, PartBuildService
    from flow_cad.jobs import JobService, JobState, JobStoreError
    from flow_cad.registry import sync_project

    resolved_request_id = request_id or f"cli-part-build-{uuid.uuid4().hex}"
    try:
        sync_project(project_root)
        with JobService(
            project_root,
            max_concurrency=1,
            recover_interrupted=False,
        ) as jobs:
            submission = PartBuildService(project_root, jobs).submit(
                request_id=resolved_request_id,
                part_key_or_uuid=part,
            )
            click.echo(
                f"{'Submitted' if submission.created else 'Reused'} build job "
                f"{submission.job.job_id} request_id={resolved_request_id}"
            )
            cursor = 0
            while True:
                for event in jobs.events(
                    job_id=submission.job.job_id,
                    after_sequence=cursor,
                    limit=100,
                ):
                    cursor = event.sequence
                    if event.message:
                        click.echo(
                            f"[{event.phase}] {event.progress * 100:.0f}% {event.message}"
                        )
                record = jobs.get(submission.job.job_id)
                if record.state.terminal:
                    break
                time.sleep(0.05)
    except (BuildContractError, JobStoreError) as error:
        raise click.ClickException(str(error)) from error

    if record.state is JobState.FAILED:
        raise click.ClickException(record.error or "scoped part build failed")
    if record.state is JobState.CANCELLED:
        raise click.ClickException("scoped part build was cancelled")
    result = record.result or {}
    click.echo(
        f"Built {result.get('part_key', part)} at viewer revision "
        f"{result.get('viewer_revision')} elapsed_ms={float(result.get('elapsed_ms', 0.0)):.3f}"
    )
    artifacts = result.get("artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if isinstance(artifact, dict):
                click.echo(
                    f"artifact {artifact.get('kind')} {artifact.get('path')} "
                    f"bytes={artifact.get('byte_count')} sha256={artifact.get('sha256')}"
                )


def _run_replacement_project_build(
    project_root: Path,
    *,
    mode: str,
    request_id: str | None,
    create_report: bool,
    create_bundle: bool,
    generate_stl: bool,
) -> None:
    """Run a strict active-project build with durable, visible progress."""

    import time
    import uuid

    from flow_cad.build import BuildContractError, ProjectBuildService
    from flow_cad.jobs import JobService, JobState, JobStoreError
    from flow_cad.registry import sync_project

    resolved_request_id = request_id or f"cli-{mode}-build-{uuid.uuid4().hex}"
    try:
        sync_project(project_root)
        with JobService(
            project_root,
            max_concurrency=1,
            recover_interrupted=False,
        ) as jobs:
            submission = ProjectBuildService(project_root, jobs).submit(
                request_id=resolved_request_id,
                mode=mode,
                create_report=create_report,
                create_bundle=create_bundle,
                generate_stl=generate_stl,
            )
            click.echo(
                f"{'Submitted' if submission.created else 'Reused'} project build job "
                f"{submission.job.job_id} request_id={resolved_request_id}"
            )
            cursor = 0
            while True:
                for event in jobs.events(
                    job_id=submission.job.job_id,
                    after_sequence=cursor,
                    limit=200,
                ):
                    cursor = event.sequence
                    if event.message and (
                        event.phase in {"plan", "assembly-preview", "report", "bundle", "publish"}
                        or event.phase.endswith(":publish")
                    ):
                        click.echo(
                            f"[{event.phase}] {event.progress * 100:.0f}% {event.message}"
                        )
                record = jobs.get(submission.job.job_id)
                if record.state.terminal:
                    break
                time.sleep(0.05)
    except (BuildContractError, JobStoreError) as error:
        raise click.ClickException(str(error)) from error

    if record.state is JobState.FAILED:
        raise click.ClickException(record.error or "project build failed")
    if record.state is JobState.CANCELLED:
        raise click.ClickException("project build was cancelled")
    result = record.result or {}
    click.echo(
        f"Built {int(result.get('part_count', 0))} active parts at viewer revision "
        f"{result.get('viewer_revision')} elapsed_ms={float(result.get('elapsed_ms', 0.0)):.3f}"
    )
    if result.get("report_path"):
        click.echo(f"Wrote build report: {result['report_path']}")
    if result.get("bundle_path"):
        click.echo(f"Created exports handoff bundle: {result['bundle_path']}")

@click.group()
def cli():
    """Flow CAD package CLI."""
    pass

@cli.command()
@click.option("--bundle/--no-bundle", default=True, help="Automatically create a tar.gz bundle of exports.")
@click.option("--cache/--no-cache", default=True, help="Update the generated SQLite active cache.")
@click.option("--snapshots/--no-snapshots", default=True, help="Automatically generate 2D SVG snapshots of each part.")
@click.option("--stl/--no-stl", "generate_stl", default=True, help="Generate STL meshes after STEP export.")
@click.option("--reports/--no-reports", "generate_reports", default=True, help="Write a CAD report after export.")
@click.option("--snapshots-only", is_flag=True, default=False, help="Only regenerate SVG snapshots without rebuilding STEP geometry.")
@click.option("--run-tests", is_flag=True, default=False, help="Run project pytest after build.")
@click.option("--part", default=None, help="Build one part and its direct facts.")
@click.option("--request-id", default=None, help="Idempotency key for a replacement build job.")
@click.option("--changed", is_flag=True, default=False, help="Rebuild parts whose source changed since the last cached build.")
@click.option("--assembly-preview", is_flag=True, default=False, help="Rebuild placement data for an updated viewer cache without handoff packaging.")
@click.option("--profile", default="all", show_default=True, help="Export profile: all, active, or a project version such as b3_v2.")
@click.option("--handoff", is_flag=True, default=False, help="Run full cache/report/assembly/hand off build for release review.")
@click.pass_context
def build(
    ctx,
    bundle,
    cache,
    snapshots,
    generate_stl,
    generate_reports,
    snapshots_only,
    run_tests,
    part,
    request_id,
    changed,
    assembly_preview,
    profile,
    handoff,
):
    """Build parts and exports from the active project."""
    build_mode = _resolve_build_mode(
        handoff=bool(handoff),
        part=part,
        changed=bool(changed),
        assembly_preview=bool(assembly_preview),
    )
    replacement_root = _replacement_project_root(Path.cwd())
    if replacement_root is not None:
        if profile not in {"all", "active"}:
            raise click.ClickException(
                "Strict-manifest builds support --profile all or --profile active."
            )
        if snapshots_only:
            raise click.ClickException(
                "Strict-manifest projects do not support --snapshots-only; build a part or project first."
            )
        if build_mode == "part":
            _run_replacement_part_build(
                replacement_root,
                part=part,
                request_id=request_id,
            )
        else:
            _run_replacement_project_build(
                replacement_root,
                mode=build_mode,
                request_id=request_id,
                create_report=bool(generate_reports),
                create_bundle=bool(bundle),
                generate_stl=bool(generate_stl),
            )
        return

    project = load_project(Path.cwd())
    build_profile = (profile or "all").strip() or "all"
    profiler = FlowCadProfiler(
        project_id=project.project_id,
        project_root=project.root,
        command=_context_command(ctx),
        build_profile=build_profile,
    )
    try:
        with profiler.measure(
            "build_total",
            "flow cad build",
            metadata={
                "build_mode": build_mode,
                "bundle": str(bool(bundle)),
                "cache": str(bool(cache)),
                "snapshots": str(bool(snapshots)),
                "snapshots_only": str(bool(snapshots_only)),
                "stl": str(bool(generate_stl)),
                "reports": str(bool(generate_reports)),
                "run_tests": str(bool(run_tests)),
                "part": str(part or ""),
                "build_profile": build_profile,
            },
        ):
            allowed_profiles = {"all", "active", *project.available_versions()}
            if build_profile not in allowed_profiles:
                allowed = ", ".join(sorted(allowed_profiles))
                raise click.ClickException(
                    f"Unknown build profile {build_profile!r}. Available profiles: {allowed}"
                )
            with profiler.measure("params_load", "project params"):
                params = project.make_params()
            if hasattr(params, "validate_params"):
                with profiler.measure("params_validation", "project params"):
                    params.validate_params()
            else:
                profiler.record_skip("params_validation", "project params", reason="no_validate_params")

            if build_mode == "handoff":
                effective_bundle = True
                effective_cache = True
                effective_snapshots = True
                effective_stl = True
                effective_reports = True
                should_clear_exports = True
            elif build_mode in {"part", "changed", "assembly-preview"}:
                effective_bundle = False
                effective_cache = False
                effective_snapshots = snapshots
                effective_stl = generate_stl
                effective_reports = generate_reports
                should_clear_exports = False
            else:
                effective_bundle = bool(bundle)
                effective_cache = bool(cache)
                effective_snapshots = bool(snapshots)
                effective_stl = bool(generate_stl)
                effective_reports = bool(generate_reports)
                should_clear_exports = True

            no_changed_definitions = False
            include_references = build_mode in {"default", "handoff", "assembly-preview", "changed"}
            if build_mode == "part":
                target_definition = _find_part_definition(project, part)
                if target_definition is None:
                    raise click.ClickException(f"Part {part!r} not found in registry for project {project.project_id}.")
                all_profile_definitions = [target_definition]
                export_definitions = all_profile_definitions
                active_cache_rows = {}
                compiled_at = None
            elif build_mode == "changed":
                latest_metadata = latest_build_metadata(project.paths.cache)
                compiled_at = latest_metadata.compiled_at.timestamp() if latest_metadata else None
                params_changed = _params_changed_since(params, latest_metadata)
                active_cache_rows = {row.id: row for row in list_component_cache(project.paths.cache)}
                all_profile_definitions = _build_profile_parts(
                    project,
                    build_profile,
                    include_references=True,
                )
                export_definitions = list(all_profile_definitions)
            else:
                all_profile_definitions = _build_profile_parts(
                    project,
                    build_profile,
                    include_references=include_references,
                )
                export_definitions = list(all_profile_definitions)
                active_cache_rows = {}
                compiled_at = None

            if not export_definitions:
                raise click.ClickException(f"Build profile {build_profile!r} did not match any registered parts")

            exporter = Exporter(
                project.root,
                params,
                enable_snapshots=effective_snapshots,
                enable_stl=effective_stl,
                snapshots_only=snapshots_only,
                exports_dir=project.paths.exports,
                reports_dir=project.paths.reports,
            )

            if build_mode == "changed":
                changed_reasons: dict[str, tuple[str, str]] = {}
                unchanged_reasons: dict[str, tuple[str, str]] = {}
                for definition in all_profile_definitions:
                    step_reason, stl_reason = _changed_definition_cache_reasons(
                        definition,
                        project,
                        exporter,
                        previous_compiled_at=compiled_at,
                        cached_row=active_cache_rows.get(definition.id),
                        params_changed=params_changed,
                    )
                    if _changed_definition_needs_rebuild(step_reason, stl_reason, effective_stl=effective_stl):
                        changed_reasons[definition.id] = (step_reason, stl_reason)
                    else:
                        unchanged_reasons[definition.id] = (step_reason, stl_reason)

                export_definitions = [
                    definition
                    for definition in all_profile_definitions
                    if definition.id in changed_reasons
                ]
                no_changed_definitions = not export_definitions
            if not snapshots_only and should_clear_exports:
                exporter.clear(profiler=profiler)
            elif snapshots_only:
                profiler.record_skip("export_cleanup", "clear previous exports", reason="snapshots_only")
            else:
                profiler.record_skip(
                    "export_cleanup",
                    "clear previous exports",
                    reason="partial_profile",
                )

            if build_mode == "changed":
                unchanged_definitions = [definition for definition in all_profile_definitions if definition.id not in changed_reasons]
                for definition in unchanged_definitions:
                    step_reason, stl_reason = unchanged_reasons[definition.id]
                    _part_cache_events_for_skipped_definition(
                        profiler,
                        exporter,
                        definition=definition,
                        step_cache_reason=step_reason,
                        stl_cache_reason=stl_reason,
                        effective_stl=effective_stl,
                    )

            if no_changed_definitions:
                profiler.record_skip("part_generation", "project parts", reason="no_changed_definitions")
            parts = _build_parts_for_definitions(params, export_definitions, profiler)

            for definition in export_definitions:
                if definition.is_printable:
                    with profiler.measure(
                        "printability_check",
                        definition.id,
                        part_id=definition.id,
                        metadata=_definition_metadata(definition),
                    ):
                        assert_printable(definition.id, parts[definition.id])
                else:
                    profiler.record_skip(
                        "printability_check",
                        definition.id,
                        part_id=definition.id,
                        reason="not_printable",
                        metadata=_definition_metadata(definition),
                    )

            exported = []
            cache_components = []
            report_definitions = []
            for definition in export_definitions:
                if build_mode == "changed":
                    step_reason, stl_reason = changed_reasons[definition.id]
                    artifact_cache = {
                        "step_status": "rebuilt",
                        "step_reason": step_reason,
                        "stl_status": "rebuilt",
                        "stl_reason": stl_reason,
                    }
                else:
                    artifact_cache = {
                        "step_status": "rebuilt",
                        "step_reason": "full_build",
                        "stl_status": "rebuilt",
                        "stl_reason": "full_build",
                    }
                path = exporter.export(
                    parts[definition.id],
                    definition.filename,
                    module_id=definition_export_subdir(definition),
                    is_printable=definition.is_printable,
                    profiler=profiler,
                    part_id=definition.id,
                    artifact_cache=artifact_cache,
                )
                exported.append(path)
                cache_components.append((definition, parts[definition.id], path))
                report_definitions.append(definition)

            assembly_definition = project.assembly_definition
            assembly_required = build_mode in {"default", "handoff", "assembly-preview"}
            if assembly_required and project.definition_matches_profile(assembly_definition, build_profile):
                with profiler.measure(
                    "assembly_generation",
                    assembly_definition.id,
                    part_id=assembly_definition.id,
                    metadata={
                        **_definition_metadata(assembly_definition),
                        "include_references": str(build_profile == "all"),
                        "assembly_id": str(project.active_assembly_id or ""),
                    },
                ):
                    parts["assembly"] = project.make_assembly(
                        params,
                        parts,
                        include_references=build_profile == "all",
                        assembly_id=project.active_assembly_id,
                    )
                assembly_path = exporter.export(
                    parts["assembly"],
                    assembly_definition.filename,
                    module_id=definition_export_subdir(assembly_definition),
                    is_printable=assembly_definition.is_printable,
                    profiler=profiler,
                    part_id=assembly_definition.id,
                )
                exported.append(assembly_path)
                cache_components.append((assembly_definition, parts["assembly"], assembly_path))
                report_definitions.append(assembly_definition)
            else:
                profiler.record_skip(
                    "assembly_generation",
                    assembly_definition.id,
                    part_id=assembly_definition.id,
                    reason="profile_excluded",
                    metadata=_definition_metadata(assembly_definition),
                )

            printable_occurrences = []
            report_path = None
            if build_mode in {"default", "assembly-preview", "handoff"}:
                if build_profile in {"all", "active", project.active_version}:
                    with profiler.measure(
                        "assembly_placement",
                        "printable report occurrences",
                        metadata={"include_references": "false"},
                    ):
                        printable_occurrences = project.get_assembly_occurrences(
                            params,
                            parts,
                            include_references=False,
                        )
                else:
                    profiler.record_skip(
                        "assembly_placement",
                        "printable report occurrences",
                        reason="profile_excluded",
                    )
            else:
                profiler.record_skip(
                    "assembly_placement",
                    "printable report occurrences",
                    reason="mode_skipped",
                )

            if no_changed_definitions:
                profiler.record_skip("report_generation", "CAD report", reason="no_changed_definitions")
            elif not effective_reports:
                profiler.record_skip("report_generation", "CAD report", reason="reports_disabled")

            if effective_reports and not no_changed_definitions:
                with profiler.measure("report_generation", "CAD report", metadata={"reports_dir": str(exporter.report_dir)}):
                    report_path = write_report(
                        params,
                        parts,
                        exported,
                        exporter.report_dir,
                        project.root,
                        printable_occurrences=printable_occurrences,
                        component_definitions=report_definitions,
                    )

            if effective_cache:
                db_path = project.paths.cache
                with profiler.measure("active_cache_write", "registry cache", metadata={"db_path": str(db_path)}):
                    build_id = write_active_cache(
                        db_path,
                        project_root=project.root,
                        params=params,
                        components=cache_components,
                    )
                click.echo(click.style(f"Updated active cache {db_path} for build {build_id}", fg="green"))
            else:
                profiler.record_skip("active_cache_write", "registry cache", reason="cache_disabled")

            _run_interference_check(parts, profiler=profiler)

            if build_mode == "handoff":
                _run_project_validators(
                    project=project,
                    profiler=profiler,
                    params=params,
                    parts=parts,
                    report_definitions=report_definitions,
                    build_mode=build_mode,
                )
            else:
                profiler.record_skip(
                    "validator",
                    "project validators",
                    reason="not_requested",
                    metadata={"build_mode": build_mode},
                )

            _run_project_tests(
                project=project,
                profiler=profiler,
                run_tests=run_tests or build_mode == "handoff",
            )

            if build_mode in {"default", "assembly-preview", "handoff"}:
                viewer_cache_definitions = list(export_definitions)
                if "assembly" in parts:
                    viewer_cache_definitions.append(assembly_definition)
                _refresh_viewer_cache(
                    project=project,
                    params=params,
                    profiler=profiler,
                    definitions=viewer_cache_definitions,
                )
            else:
                profiler.record_skip(
                    "viewer_cache_update",
                    "refresh viewer cache",
                    reason="mode_skipped",
                    metadata={"build_mode": build_mode},
                )

            if not snapshots_only:
                click.echo(
                    click.style(
                        f"Exported {len(exported)} STEP files to {exporter.step_dir} using profile {build_profile}",
                        fg="green",
                    )
                )
                if effective_stl:
                    click.echo(
                        click.style(
                            f"Exported {len(exported)} STL files to {exporter.stl_dir} using profile {build_profile}",
                            fg="green",
                        )
                    )
            if exporter.enable_snapshots:
                click.echo(
                    click.style(
                        f"Generated {exporter.snapshot_count} visual SVG snapshots to {exporter.snapshot_dir}",
                        fg="green",
                    )
                )
            if report_path is not None:
                click.echo(click.style(f"Wrote report to {report_path}", fg="green"))

            if effective_bundle:
                handoff_dir = project.root / "handoff"
                bundle_profile = "active" if build_profile == "all" else build_profile
                with profiler.measure(
                    "handoff_bundle",
                    "exports.tar.gz",
                    metadata={"handoff_dir": str(handoff_dir), "bundle_profile": bundle_profile},
                ):
                    bundle_path = create_bundle(
                        exporter.step_dir.parent,
                        handoff_dir,
                        "exports.tar.gz",
                        active_export_paths=project.expected_printable_export_relative_paths(bundle_profile),
                    )
                click.echo(click.style(f"Created exports handoff bundle: {bundle_path}", fg="cyan", bold=True))
            else:
                profiler.record_skip("handoff_bundle", "exports.tar.gz", reason="bundle_disabled")
    except Exception:
        profiler.finish("failed")
        write_build_profile(profiler, project.paths.local_state)
        raise
    else:
        profiler.finish("ok")
        profile_paths = write_build_profile(profiler, project.paths.local_state)
        click.echo(click.style(f"Wrote build profile to {profile_paths.latest_path}", fg="blue"))


@cli.command("urdf")
@click.option("--target", required=True, help="URDF export target name, such as b2_v2.")
@click.option("--profile", default=None, help="Export profile override. Defaults to the target profile.")
@click.option("--output", "output_path", type=click.Path(path_type=Path), default=None, help="Output .urdf path.")
@click.option("--overwrite", is_flag=True, default=False, help="Overwrite an existing .urdf file.")
@click.option("--json", "json_output", is_flag=True, default=False, help="Print the export result as JSON.")
def urdf(target: str, profile: str | None, output_path: Path | None, overwrite: bool, json_output: bool) -> None:
    """Export a project URDF target."""
    project = load_project(Path.cwd(), fallback_to_bundled=False)
    service = UrdfExportService(project)
    try:
        result = service.export(
            target_name=target,
            profile=profile,
            output_path=output_path,
            overwrite=overwrite,
        )
    except UrdfExportError as exc:
        raise click.ClickException(str(exc)) from exc

    if json_output:
        click.echo(json.dumps(result, indent=2, sort_keys=True))
        return
    click.echo(click.style(f"Wrote URDF to {result['output_path']}", fg="green"))
    click.echo(click.style(f"Wrote URDF report to {result['report_path']}", fg="blue"))


@cli.command("profile")
@click.option("--last", is_flag=True, default=False, help="Show the latest build profile.")
@click.option("--json", "json_output", is_flag=True, default=False, help="Print the raw profile JSON.")
@click.option("--limit", default=5, show_default=True, type=int, help="Number of slow operations to show.")
def profile_command(last, json_output, limit):
    """Show the most recent Flow CAD build profile."""
    _ = last
    project = load_project(Path.cwd())
    profile_data = load_latest_build_profile(project.paths.local_state)
    if profile_data is None:
        raise click.ClickException(f"No build profile found at {latest_build_profile_path(project.paths.local_state)}")
    if json_output:
        click.echo(json.dumps(profile_data, indent=2, sort_keys=True))
        return
    click.echo(format_profile_summary(profile_data, limit=limit))

if __name__ == "__main__":
    cli()
