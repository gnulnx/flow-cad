"""CAD-importing worker for one isolated replacement part build."""

from __future__ import annotations

import hashlib
import importlib
import os
import shutil
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from flow_cad.jobs import JobContext
from flow_cad.jobs.service import JobWork

from .service import BuildArtifactTarget, ScopedPartBuildPlan


_PROJECT_IMPORT_LOCK = threading.RLock()


class PartBuildWorkerError(RuntimeError):
    """A scoped worker failed before publishing fresh artifacts."""


def scoped_part_build_work(plan: ScopedPartBuildPlan) -> JobWork:
    """Return a job closure; importing this module never imports CAD libraries."""

    def work(context: JobContext) -> dict[str, object]:
        return _run_scoped_part_build(plan, context)

    return work


def _run_scoped_part_build(
    plan: ScopedPartBuildPlan,
    context: JobContext,
) -> dict[str, object]:
    started = time.perf_counter()
    timings: dict[str, float] = {}
    staging_parent = plan.project_root / ".flow" / "build-work"
    staging_parent.mkdir(parents=True, exist_ok=True)
    work_dir = Path(
        tempfile.mkdtemp(
            prefix=f"{plan.part_uuid}-",
            dir=staging_parent,
        )
    )
    try:
        context.report("resolve", 0.05, f"Resolved {plan.part_key}")
        phase_started = time.perf_counter()
        parameter_provider, generator = _import_project_symbols(plan)
        timings["import_project"] = _elapsed_ms(phase_started)
        context.report(
            "import",
            0.10,
            f"Imported project symbols in {timings['import_project']:.1f} ms",
        )
        context.checkpoint()

        phase_started = time.perf_counter()
        parameters = parameter_provider()
        timings["load_parameters"] = _elapsed_ms(phase_started)
        context.report(
            "parameters",
            0.15,
            f"Loaded project parameters in {timings['load_parameters']:.1f} ms",
        )
        context.checkpoint()

        phase_started = time.perf_counter()
        shape = generator(parameters)
        timings["generate_geometry"] = _elapsed_ms(phase_started)
        if shape is None:
            raise PartBuildWorkerError(f"generator returned no geometry: {plan.generator}")
        context.report(
            "generate",
            0.50,
            f"Generated part geometry in {timings['generate_geometry']:.1f} ms",
        )
        context.checkpoint()

        phase_started = time.perf_counter()
        build123d = importlib.import_module("build123d")
        export_step = _required_callable(build123d, "export_step")
        export_stl = _required_callable(build123d, "export_stl")
        timings["import_exporters"] = _elapsed_ms(phase_started)

        staged: list[tuple[BuildArtifactTarget, Path]] = []
        for index, target in enumerate(plan.artifacts):
            context.checkpoint()
            phase_started = time.perf_counter()
            staged_path = work_dir / f"artifact-{index}{target.destination.suffix.lower()}"
            exporter = export_step if target.kind == "step" else export_stl
            if exporter(shape, staged_path) is not True:
                raise PartBuildWorkerError(
                    f"{target.kind.upper()} exporter reported failure for {target.relative_path}"
                )
            _require_fresh_file(staged_path, target)
            timings[f"export_{target.kind}"] = _elapsed_ms(phase_started)
            staged.append((target, staged_path))
            progress = 0.70 if target.kind == "step" else 0.82
            context.report(
                f"export_{target.kind}",
                progress,
                f"Staged {target.kind.upper()} artifact in "
                f"{timings[f'export_{target.kind}']:.1f} ms",
            )

        context.checkpoint()
        phase_started = time.perf_counter()
        artifacts = [
            {
                "kind": target.kind,
                "path": target.relative_path,
                "sha256": _sha256(staged_path),
                "byte_count": staged_path.stat().st_size,
            }
            for target, staged_path in staged
        ]
        timings["hash_artifacts"] = _elapsed_ms(phase_started)
        context.report(
            "hash",
            0.92,
            f"Verified staged artifact identities in {timings['hash_artifacts']:.1f} ms",
        )

        context.checkpoint()
        phase_started = time.perf_counter()
        _publish_all(plan.project_root, staged)
        timings["publish"] = _elapsed_ms(phase_started)
        context.report(
            "publish",
            0.99,
            f"Published fresh artifacts atomically in {timings['publish']:.1f} ms",
        )

        elapsed_ms = _elapsed_ms(started)
        timings["total"] = elapsed_ms
        return {
            "project_id": plan.project_id,
            "part_uuid": str(plan.part_uuid),
            "part_key": plan.part_key,
            "generator": plan.generator,
            "parameter_provider": plan.parameter_provider,
            "artifacts": artifacts,
            "phase_timings_ms": timings,
            "elapsed_ms": elapsed_ms,
        }
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def _import_project_symbols(
    plan: ScopedPartBuildPlan,
) -> tuple[Callable[[], Any], Callable[[Any], Any]]:
    with _PROJECT_IMPORT_LOCK:
        root_text = os.fspath(plan.project_root)
        sys.path.insert(0, root_text)
        importlib.invalidate_caches()
        try:
            provider = _import_symbol(plan.parameter_provider)
            generator = _import_symbol(plan.generator)
        finally:
            try:
                sys.path.remove(root_text)
            except ValueError:
                pass
    if not callable(provider):
        raise PartBuildWorkerError(
            f"parameter provider is not callable: {plan.parameter_provider}"
        )
    if not callable(generator):
        raise PartBuildWorkerError(f"part generator is not callable: {plan.generator}")
    return provider, generator


def _import_symbol(reference: str) -> Any:
    module_name, _, symbol_path = reference.partition(":")
    try:
        value: Any = importlib.import_module(module_name)
        for segment in symbol_path.split("."):
            value = getattr(value, segment)
    except (ImportError, AttributeError) as exc:
        raise PartBuildWorkerError(f"could not import {reference}: {exc}") from exc
    return value


def _required_callable(module: Any, name: str) -> Callable[..., Any]:
    value = getattr(module, name, None)
    if not callable(value):
        raise PartBuildWorkerError(f"build123d does not expose callable {name}")
    return value


def _require_fresh_file(path: Path, target: BuildArtifactTarget) -> None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise PartBuildWorkerError(
            f"{target.kind.upper()} exporter did not create {target.relative_path}"
        ) from exc
    if size <= 0:
        raise PartBuildWorkerError(
            f"{target.kind.upper()} exporter created an empty artifact: {target.relative_path}"
        )


def _publish_all(
    project_root: Path,
    staged: list[tuple[BuildArtifactTarget, Path]],
) -> None:
    for target, _ in staged:
        resolved_parent = target.destination.parent.resolve()
        try:
            resolved_parent.relative_to(project_root)
        except ValueError as exc:
            raise PartBuildWorkerError(
                f"artifact directory now resolves outside the project: {target.relative_path}"
            ) from exc
        target.destination.parent.mkdir(parents=True, exist_ok=True)
        resolved_destination = target.destination.resolve()
        try:
            resolved_destination.relative_to(project_root)
        except ValueError as exc:
            raise PartBuildWorkerError(
                f"artifact output now resolves outside the project: {target.relative_path}"
            ) from exc
    for target, staged_path in staged:
        _fsync_file(staged_path)
        os.replace(staged_path, target.destination)
        _fsync_directory(target.destination.parent)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fsync_file(path: Path) -> None:
    with path.open("rb") as handle:
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0
