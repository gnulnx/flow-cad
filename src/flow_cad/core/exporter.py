from __future__ import annotations

from pathlib import Path
from typing import Any

from build123d import export_step, export_stl

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

    def export(self, shape, filename: str, module_id: str | None = None, is_printable: bool = True) -> Path:
        if module_id:
            dest_dir = self.step_dir / module_id
            stl_dest_dir = self.stl_dir / module_id
        else:
            dest_dir = self.step_dir
            stl_dest_dir = self.stl_dir
        path = dest_dir / filename

        if not self.snapshots_only:
            dest_dir.mkdir(parents=True, exist_ok=True)
            ok = export_step(shape, path)
            if not ok:
                raise RuntimeError(f"STEP export failed: {path}")
            normalize_step_file(path)

            stl_path = stl_dest_dir / filename.replace(".step", ".stl")
            stl_dest_dir.mkdir(parents=True, exist_ok=True)
            ok = export_stl(shape, stl_path)
            if not ok:
                raise RuntimeError(f"STL export failed: {stl_path}")

        if self.enable_snapshots and is_printable:
            snap_dest = self.snapshot_dir / module_id if module_id else self.snapshot_dir
            part_id = Path(filename).stem
            from .snapshots import export_part_snapshots

            project_id = getattr(self.params, "project_id", "flow")
            snap_paths = export_part_snapshots(shape, part_id, snap_dest, metadata={"Project": project_id})
            self.snapshot_count += len(snap_paths)

        return path

    def clear(self):
        if self.step_dir.exists():
            for path in self.step_dir.rglob("*.step"):
                if path.is_file():
                    path.unlink()
        if self.stl_dir.exists():
            for path in self.stl_dir.rglob("*.stl"):
                if path.is_file():
                    path.unlink()


def bbox_dims(shape) -> tuple[float, float, float]:
    bb = shape.bounding_box()
    return (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
