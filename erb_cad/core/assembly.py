from __future__ import annotations
from build123d import Location, Compound, export_step
from pathlib import Path
from ..params import ChassisParams
from ..step_io import normalize_step_file

class Exporter:
    def __init__(self, project_root: Path, params: ChassisParams):
        self.project_root = project_root
        self.params = params
        self.step_dir = project_root / "b3" / "exports" / "step"
        self.report_dir = project_root / "b3" / "reports"
        self.step_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def export(self, shape, filename: str, module_id: str | None = None) -> Path:
        if module_id:
            dest_dir = self.step_dir / module_id
            dest_dir.mkdir(parents=True, exist_ok=True)
        else:
            dest_dir = self.step_dir
        path = dest_dir / filename
        ok = export_step(shape, path)
        if not ok:
            raise RuntimeError(f"STEP export failed: {path}")
        normalize_step_file(path)
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
        (
            "upper_wide_center_adapter_deck",
            "upper_wide_center_adapter_deck",
            (0.0, 0.0, params.upper_adapter_deck_z),
        ),
        (
            "upper_wide_center_compute_bay",
            "upper_wide_center_compute_bay",
            (0.0, 0.0, params.upper_module_bottom_z),
        ),
        (
            "upper_wide_left_overwheel_pod",
            "upper_wide_left_overwheel_pod",
            (
                -(params.upper_module_center_width + (params.upper_module_overall_width - params.upper_module_center_width) / 2.0) / 2.0,
                0.0,
                params.upper_adapter_deck_z + params.upper_adapter_deck_thickness,
            ),
        ),
        (
            "upper_wide_right_overwheel_pod",
            "upper_wide_right_overwheel_pod",
            (
                (params.upper_module_center_width + (params.upper_module_overall_width - params.upper_module_center_width) / 2.0) / 2.0,
                0.0,
                params.upper_adapter_deck_z + params.upper_adapter_deck_thickness,
            ),
        ),
        (
            "upper_perception_pod",
            "upper_perception_pod",
            (0.0, -34.0, params.perception_pod_base_z),
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
    return Compound(children=children, label="b3_lower_chassis_assembly")
