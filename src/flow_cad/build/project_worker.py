"""Cancellable strict-manifest worker for the active production set."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from flow_cad.core.bundler import create_bundle
from flow_cad.jobs import JobContext
from flow_cad.jobs.service import JobWork

from .service import ProjectBuildPlan
from .worker import run_scoped_part_build


BUILD_REPORT = Path(".flow/reports/project-build-latest.json")
HANDOFF_BUNDLE = Path(".flow/handoff/exports.tar.gz")


class _PartProgressContext:
    def __init__(
        self,
        parent: JobContext,
        *,
        part_key: str,
        part_index: int,
        part_count: int,
    ) -> None:
        self.parent = parent
        self.job_id = parent.job_id
        self.part_key = part_key
        self.part_index = part_index
        self.part_count = part_count

    @property
    def cancellation_requested(self) -> bool:
        return self.parent.cancellation_requested

    def checkpoint(self) -> None:
        self.parent.checkpoint()

    def report(self, phase: str, progress: float, message: str | None = None) -> None:
        span = 0.86 / max(self.part_count, 1)
        scaled = 0.03 + self.part_index * span + progress * span
        self.parent.report(
            f"part:{self.part_key}:{phase}",
            min(scaled, 0.89),
            message,
        )


def project_build_work(plan: ProjectBuildPlan) -> JobWork:
    def work(context: JobContext) -> dict[str, object]:
        return run_project_build(plan, context)

    return work


def run_project_build(plan: ProjectBuildPlan, context: JobContext) -> dict[str, object]:
    started = time.perf_counter()
    context.report(
        "plan",
        0.02,
        f"Planned {len(plan.parts)} active part build(s) for {plan.project_id}",
    )
    results: list[dict[str, object]] = []
    for index, part in enumerate(plan.parts):
        context.checkpoint()
        result = run_scoped_part_build(
            part,
            _PartProgressContext(
                context,
                part_key=part.part_key,
                part_index=index,
                part_count=len(plan.parts),
            ),
        )
        results.append(result)

    if not plan.parts:
        context.report(
            "assembly-preview",
            0.89,
            "Assembly metadata is current; no production geometry rebuild was required",
        )

    artifacts = [
        artifact
        for result in results
        for artifact in result.get("artifacts", [])
        if isinstance(artifact, dict)
    ]
    snapshots = [
        snapshot
        for result in results
        for snapshot in result.get("snapshots", [])
        if isinstance(snapshot, dict)
    ]
    report_path: Path | None = None
    if plan.create_report:
        context.report("report", 0.92, "Writing project build report")
        report_path = plan.project_root / BUILD_REPORT
        _write_json_atomic(
            report_path,
            {
                "schema_version": 1,
                "project_id": plan.project_id,
                "mode": plan.mode,
                "part_count": len(results),
                "parts": results,
                "artifacts": artifacts,
                "snapshots": snapshots,
            },
        )

    bundle_path: Path | None = None
    if plan.create_bundle:
        context.checkpoint()
        context.report("bundle", 0.95, "Creating active exports handoff bundle")
        active_paths = {
            Path(str(artifact["path"])).relative_to("exports")
            for artifact in [*artifacts, *snapshots]
            if str(artifact.get("path", "")).startswith("exports/")
        }
        bundle_path = create_bundle(
            plan.project_root / "exports",
            plan.project_root / HANDOFF_BUNDLE.parent,
            HANDOFF_BUNDLE.name,
            active_export_paths=active_paths,
        )

    context.report(
        "publish",
        0.99,
        f"Published {len(artifacts)} artifact(s) for {len(results)} part(s)",
    )
    viewer_revision = max(
        (int(result.get("viewer_revision", 0)) for result in results),
        default=_viewer_revision(plan.project_root),
    )
    return {
        "project_id": plan.project_id,
        "mode": plan.mode,
        "part_count": len(results),
        "part_keys": [result.get("part_key") for result in results],
        "parts": results,
        "artifacts": artifacts,
        "snapshots": snapshots,
        "viewer_revision": viewer_revision,
        "report_path": report_path.relative_to(plan.project_root).as_posix()
        if report_path is not None
        else None,
        "bundle_path": bundle_path.relative_to(plan.project_root).as_posix()
        if bundle_path is not None
        else None,
        "elapsed_ms": (time.perf_counter() - started) * 1000.0,
    }


def _viewer_revision(project_root: Path) -> int:
    from contextlib import closing

    from flow_cad.registry.db import connect_readonly, database_path

    with closing(connect_readonly(database_path(project_root))) as connection:
        row = connection.execute("SELECT revision FROM projects LIMIT 1").fetchone()
    return int(row["revision"]) if row is not None else 0


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
