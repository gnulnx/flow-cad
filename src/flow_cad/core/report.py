from __future__ import annotations
from collections.abc import Iterable
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
    component_definitions: Iterable[Any] | None = None,
) -> Path:
    assembly_dims = bbox_dims(parts["assembly"]) if "assembly" in parts else None
    if printable_occurrences is None:
        printable_occurrences = [
            {"shape": shape}
            for name, shape in parts.items()
            if name != "assembly"
        ]
    printable_assembly_dims = None
    if printable_occurrences:
        printable_assembly = Compound(children=[occurrence["shape"] for occurrence in printable_occurrences])
        printable_assembly_dims = bbox_dims(printable_assembly)

    project_id = getattr(params, "project_id", "flow")
    report_path = report_dir / f"{project_id}_cad_report.txt"
    lines = [
        f"{project_id} CAD report",
        "====================",
        "",
        "Final outer dimensions:",
        "- Full assembly bbox: "
        + (
            f"{assembly_dims[0]:.1f} W x {assembly_dims[1]:.1f} D x {assembly_dims[2]:.1f} H mm"
            if assembly_dims is not None
            else "not exported for this profile"
        ),
        "- Printable assembly bbox: "
        + (
            f"{printable_assembly_dims[0]:.1f} W x {printable_assembly_dims[1]:.1f} D x {printable_assembly_dims[2]:.1f} H mm"
            if printable_assembly_dims is not None
            else "not exported for this profile"
        ),
        "",
        "Exported STEP files:",
    ]
    for path in sorted(exported, key=lambda p: p.name):
        lines.append(f"- {path.relative_to(project_root)}")

    if component_definitions is not None:
        lines.extend(["", "Version mass summary:"])
        definitions = list(component_definitions)
        versions = sorted({str(getattr(definition, "version", "") or "unversioned") for definition in definitions})
        for version in versions:
            version_definitions = [
                definition
                for definition in definitions
                if str(getattr(definition, "version", "") or "unversioned") == version
            ]
            known_masses = [
                float(getattr(definition, "mass_kg"))
                for definition in version_definitions
                if getattr(definition, "mass_kg", None) is not None
            ]
            missing_inertial = [
                definition.id
                for definition in version_definitions
                if (
                    getattr(definition, "mass_kg", None) is None
                    or getattr(definition, "center_of_mass_mm", None) is None
                    or getattr(definition, "inertia_kg_m2", None) is None
                )
            ]
            lines.append(f"- {version}: {sum(known_masses):.4f} kg known mass across {len(known_masses)} parts")
            if missing_inertial:
                lines.append(f"  Missing inertial metadata: {', '.join(sorted(missing_inertial))}")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path
