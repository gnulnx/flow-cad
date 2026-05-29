from __future__ import annotations
from typing import Any
from pathlib import Path
from .exporter import bbox_dims
from build123d import Compound

def write_report(
    params: Any,
    parts: dict[str, object],
    exported: list[Path],
    report_dir: Path,
    project_root: Path,
    *,
    printable_occurrences: list[dict[str, Any]] | None = None,
) -> Path:
    assembly_dims = bbox_dims(parts["assembly"])
    if printable_occurrences is None:
        printable_occurrences = [
            {"shape": shape}
            for name, shape in parts.items()
            if name != "assembly"
        ]
    printable_assembly = Compound(children=[occurrence["shape"] for occurrence in printable_occurrences])
    printable_assembly_dims = bbox_dims(printable_assembly)

    project_id = getattr(params, "project_id", "flow")
    report_path = report_dir / f"{project_id}_cad_report.txt"
    lines = [
        f"{project_id} CAD report",
        "====================",
        "",
        "Final outer dimensions:",
        f"- Full assembly bbox: {assembly_dims[0]:.1f} W x {assembly_dims[1]:.1f} D x {assembly_dims[2]:.1f} H mm",
        f"- Printable assembly bbox: {printable_assembly_dims[0]:.1f} W x {printable_assembly_dims[1]:.1f} D x {printable_assembly_dims[2]:.1f} H mm",
        "",
        "Exported STEP files:",
    ]
    for path in sorted(exported, key=lambda p: p.name):
        lines.append(f"- {path.relative_to(project_root)}")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path
