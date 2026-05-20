from __future__ import annotations
from build123d import Location, Compound, export_step
from pathlib import Path
from ..params import ChassisParams
from ..step_io import normalize_step_file

class Exporter:
    def __init__(self, project_root: Path, params: ChassisParams, enable_snapshots: bool = True, snapshots_only: bool = False):
        self.project_root = project_root
        self.params = params
        self.step_dir = project_root / params.project_id / "exports" / "step"
        self.report_dir = project_root / params.project_id / "reports"
        self.snapshot_dir = project_root / params.project_id / "exports" / "snapshots"
        self.enable_snapshots = enable_snapshots
        self.snapshots_only = snapshots_only
        self.snapshot_count = 0
        self.step_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        if self.enable_snapshots:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def export(self, shape, filename: str, module_id: str | None = None, is_printable: bool = True) -> Path:
        if module_id:
            dest_dir = self.step_dir / module_id
        else:
            dest_dir = self.step_dir
        path = dest_dir / filename

        if not self.snapshots_only:
            dest_dir.mkdir(parents=True, exist_ok=True)
            ok = export_step(shape, path)
            if not ok:
                raise RuntimeError(f"STEP export failed: {path}")
            normalize_step_file(path)

        if self.enable_snapshots and is_printable:
            if module_id:
                snap_dest = self.snapshot_dir / module_id
            else:
                snap_dest = self.snapshot_dir
            part_id = Path(filename).stem
            from .snapshots import export_part_snapshots
            snap_paths = export_part_snapshots(shape, part_id, snap_dest, metadata={"Project": self.params.project_id})
            self.snapshot_count += len(snap_paths)

        return path

    def clear(self):
        if self.step_dir.exists():
            for path in self.step_dir.rglob("*.step"):
                if path.is_file():
                    path.unlink()

def bbox_dims(shape) -> tuple[float, float, float]:
    bb = shape.bounding_box()
    return (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)

def get_assembly_occurrences(params: ChassisParams, parts: dict[str, object], include_references: bool = False):
    UPPER_SHELF_TOP_Z = params.shelf_z_levels[1] + params.shelf_thickness
    THIRD_SHELF_Z = UPPER_SHELF_TOP_Z + params.shelf_spacer_block_height

    placements = [
        ("left_side_plate", "left_side_plate", (-params.center_box_outer_width / 2.0, 0.0, 0.0)),
        ("right_side_plate", "right_side_plate", (params.center_box_outer_width / 2.0, 0.0, 0.0)),
        ("front_panel", "front_panel", (0.0, -params.box_depth / 2.0, 0.0)),
        ("rear_panel", "rear_panel", (0.0, params.box_depth / 2.0, 0.0)),
        ("bottom_tray", "bottom_tray", (0.0, 0.0, 0.0)),
        ("lower_equipment_shelf", "equipment_shelf_service_fit", (0.0, 0.0, params.shelf_z_levels[0])),
        ("upper_equipment_shelf", "equipment_shelf_service_fit", (0.0, 0.0, params.shelf_z_levels[1])),
        ("third_equipment_shelf", "equipment_shelf_service_fit", (0.0, 0.0, THIRD_SHELF_Z)),
        (
            "left_axle_insert_medium",
            "axle_insert_medium",
            (-params.center_box_outer_width / 2.0, 0.0, params.axle_center_height_from_bottom),
        ),
        (
            "right_axle_insert_medium",
            "axle_insert_medium",
            (params.center_box_outer_width / 2.0, 0.0, params.axle_center_height_from_bottom),
            (0.0, 0.0, 180.0),
        ),
    ]

    if include_references:
        placements.extend([
            ("reference_wheel_pair", "reference_wheel_pair", (0.0, 0.0, 0.0)),
            ("reference_axle_pair", "reference_axle_pair", (0.0, 0.0, 0.0)),
        ])

    occurrences = []
    for placement in placements:
        name, part_key, location = placement[:3]
        rotation = placement[3] if len(placement) > 3 else (0.0, 0.0, 0.0)
        placed_shape = parts[part_key].moved(Location(location, rotation))
        occurrences.append({
            "name": name,
            "part_key": part_key,
            "location": location,
            "rotation": rotation,
            "shape": placed_shape,
        })
    return occurrences

def make_assembly(params: ChassisParams, parts: dict[str, object], include_references: bool = True):
    children = [occ["shape"] for occ in get_assembly_occurrences(params, parts, include_references)]
    return Compound(children=children, label=f"{params.project_id}_lower_chassis_assembly")
