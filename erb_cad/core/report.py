from __future__ import annotations
from pathlib import Path
from ..params import ChassisParams
from .assembly import bbox_dims, get_assembly_occurrences
from build123d import Compound

def write_report(params: ChassisParams, parts: dict[str, object], exported: list[Path], report_dir: Path, project_root: Path) -> Path:
    report_path = report_dir / "stage1_lower_chassis_report.txt"
    
    assembly_dims = bbox_dims(parts["assembly"])
    printable_occurrences = get_assembly_occurrences(params, parts, include_references=False)
    printable_assembly = Compound(children=[occurrence["shape"] for occurrence in printable_occurrences])
    printable_assembly_dims = bbox_dims(printable_assembly)
    
    center_box_dims = (params.center_box_outer_width, params.box_depth, params.box_height)
    wheel_center_x = params.wheel_overall_width / 2.0 - params.wheel_width / 2.0
    wheel_inner_face_x = wheel_center_x - params.wheel_width / 2.0

    SIDE_SCREW_Z_LEVELS = (220.0,)
    
    # Just a mock for now to match the monolith report structure
    lines = [
        "Erb Stage 1 lower chassis CAD report (MODULAR)",
        "==============================================",
        "",
        "Final outer dimensions:",
        f"- Center structural box: {center_box_dims[0]:.1f} W x {center_box_dims[1]:.1f} D x {center_box_dims[2]:.1f} H mm",
        f"- Printable chassis assembly bbox: {printable_assembly_dims[0]:.1f} W x {printable_assembly_dims[1]:.1f} D x {printable_assembly_dims[2]:.1f} H mm",
        "",
        "Exported STEP files:",
    ]
    for path in sorted(exported, key=lambda p: p.name):
        lines.append(f"- {path.relative_to(project_root)}")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path
