from __future__ import annotations

from pathlib import Path
from typing import Any

from build123d import export_step, export_stl

from flow_cad.profiler import FlowCadProfiler

from ..step_io import normalize_step_file


class Exporter:
    def __init__(
        self,
        project_root: Path,
        params: Any,
        enable_snapshots: bool = True,
        snapshots_only: bool = False,
        exports_dir: Path | None = None,
        reports_dir: Path | None = None,
    ):
        self.project_root = project_root
        self.params = params
        project_id = getattr(params, "project_id", "flow")
        export_root = exports_dir or project_root / project_id / "exports"
        self.step_dir = export_root / "step"
        self.stl_dir = export_root / "stl"
        self.report_dir = reports_dir or project_root / project_id / "reports"
        self.snapshot_dir = export_root / "snapshots"
        self.enable_snapshots = enable_snapshots
        self.snapshots_only = snapshots_only
        self.snapshot_count = 0
        self.step_dir.mkdir(parents=True, exist_ok=True)
        self.stl_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        if self.enable_snapshots:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def export(
        self,
        shape,
        filename: str,
        module_id: str | Path | None = None,
        is_printable: bool = True,
        *,
        profiler: FlowCadProfiler | None = None,
        part_id: str | None = None,
    ) -> Path:
        if module_id:
            dest_dir = self.step_dir / module_id
            stl_dest_dir = self.stl_dir / module_id
        else:
            dest_dir = self.step_dir
            stl_dest_dir = self.stl_dir
        path = dest_dir / filename

        if not self.snapshots_only:
            dest_dir.mkdir(parents=True, exist_ok=True)
            step_metadata = {
                "path": str(path),
                "module_id": str(module_id or ""),
                "artifact_cache_status": "rebuilt",
                "artifact_cache_reason": "full_build",
            }
            if profiler is None:
                ok = export_step(shape, path)
            else:
                with profiler.measure("step_export", filename, part_id=part_id, metadata=step_metadata):
                    ok = export_step(shape, path)
            if not ok:
                raise RuntimeError(f"STEP export failed: {path}")
            if profiler is None:
                normalize_step_file(path)
            else:
                with profiler.measure("step_normalize", filename, part_id=part_id, metadata={"path": str(path)}):
                    normalize_step_file(path)

            stl_path = stl_dest_dir / filename.replace(".step", ".stl")
            stl_dest_dir.mkdir(parents=True, exist_ok=True)
            stl_metadata = {
                "path": str(stl_path),
                "module_id": str(module_id or ""),
                "artifact_cache_status": "rebuilt",
                "artifact_cache_reason": "full_build",
            }
            if profiler is None:
                ok = export_stl(shape, stl_path)
            else:
                with profiler.measure("stl_export", stl_path.name, part_id=part_id, metadata=stl_metadata):
                    ok = export_stl(shape, stl_path)
            if not ok:
                raise RuntimeError(f"STL export failed: {stl_path}")
        elif profiler is not None:
            profiler.record_skip(
                "step_export",
                filename,
                part_id=part_id,
                reason="snapshots_only",
                metadata={"path": str(path), "module_id": str(module_id or "")},
            )
            profiler.record_skip(
                "stl_export",
                filename.replace(".step", ".stl"),
                part_id=part_id,
                reason="snapshots_only",
                metadata={"module_id": str(module_id or "")},
            )

        if self.enable_snapshots and is_printable:
            snap_dest = self.snapshot_dir / module_id if module_id else self.snapshot_dir
            snapshot_part_id = Path(filename).stem
            from .snapshots import export_part_snapshots

            project_id = getattr(self.params, "project_id", "flow")
            snapshot_metadata = {"path": str(snap_dest), "module_id": str(module_id or "")}
            if profiler is None:
                snap_paths = export_part_snapshots(shape, snapshot_part_id, snap_dest, metadata={"Project": project_id})
            else:
                with profiler.measure(
                    "snapshot_export",
                    filename,
                    part_id=part_id,
                    metadata=snapshot_metadata,
                ):
                    snap_paths = export_part_snapshots(shape, snapshot_part_id, snap_dest, metadata={"Project": project_id})
            self.snapshot_count += len(snap_paths)
        elif profiler is not None and is_printable:
            profiler.record_skip("snapshot_export", filename, part_id=part_id, reason="snapshots_disabled")

        return path

    def clear(self, *, profiler: FlowCadProfiler | None = None):
        def _clear() -> None:
            for directory, suffixes in (
                (self.step_dir, {".step", ".glb"}),
                (self.stl_dir, {".stl"}),
                (self.snapshot_dir, {".svg"}),
            ):
                if not directory.exists():
                    continue
                for path in directory.rglob("*"):
                    if path.is_file() and path.suffix in suffixes:
                        path.unlink()
                for path in sorted((p for p in directory.rglob("*") if p.is_dir()), reverse=True):
                    try:
                        path.rmdir()
                    except OSError:
                        pass

        if profiler is None:
            _clear()
            return
        with profiler.measure("export_cleanup", "clear previous exports"):
            _clear()


def bbox_dims(shape) -> tuple[float, float, float]:
    bb = shape.bounding_box()
    return (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
