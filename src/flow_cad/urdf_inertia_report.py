from __future__ import annotations

import argparse
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


PITCH_AXIS_FLOW_INDEX = 0
PERPENDICULAR_TO_PITCH_FLOW_INDICES = (1, 2)


def _is_wheel_link_contribution(contribution: dict[str, Any]) -> bool:
    part_id = str(contribution.get("part_id", ""))
    return "wheel" in part_id and "reference" in part_id


def _float_list(value: Any, *, count: int, context: str) -> list[float]:
    if not isinstance(value, list | tuple) or len(value) != count:
        raise ValueError(f"{context} must contain {count} values.")
    return [float(item) for item in value]


def _chassis_box_size_m(report: dict[str, Any], report_path: Path) -> list[float]:
    raw = report.get("chassis_box_size_m")
    if raw is not None:
        return _float_list(raw, count=3, context="chassis_box_size_m")

    output_path = Path(str(report.get("output_path", ""))).expanduser()
    if not output_path.is_absolute():
        output_path = report_path.parent / output_path
    if not output_path.exists():
        raise ValueError("Report has no chassis_box_size_m and output_path does not exist.")
    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    chassis = root.find(".//link[@name='chassis_link']/flow_cad_chassis_box")
    if chassis is None:
        raise ValueError("No chassis_box_size_m or chassis_link/flow_cad_chassis_box found.")
    size_raw = chassis.attrib.get("size", "")
    parts = [float(part) for part in size_raw.split()]
    if len(parts) != 3:
        raise ValueError(f"Expected 3 chassis box size values, got {size_raw!r}.")
    return parts


def _default_chassis_mass_kg(report: dict[str, Any]) -> float:
    if report.get("recommended_chassis_mass_kg") is not None:
        return float(report["recommended_chassis_mass_kg"])
    choices = (
        report.get("recommended_dojo_config", {})
        .get("randomization", {})
        .get("urdf_chassis_mass_choices")
    )
    if isinstance(choices, list) and choices:
        return float(choices[0])
    raise ValueError("Report does not include recommended_chassis_mass_kg or urdf_chassis_mass_choices.")


def _box_pitch_inertia_kg_m2(*, mass_kg: float, flow_size_mm: list[float]) -> float:
    # URDF pitch is +Y, which maps to Flow CAD +X for the Dojo balance-bot export.
    perpendicular_sizes_m = [
        flow_size_mm[index] / 1000.0
        for index in PERPENDICULAR_TO_PITCH_FLOW_INDICES
    ]
    return mass_kg / 12.0 * sum(size * size for size in perpendicular_sizes_m)


def _urdf_box_iyy_kg_m2(*, mass_kg: float, size_m: list[float]) -> float:
    x_m, _y_m, z_m = size_m
    return mass_kg / 12.0 * (x_m * x_m + z_m * z_m)


def _wheel_center_z_mm(contributions: list[dict[str, Any]]) -> float:
    wheels = [
        contribution
        for contribution in contributions
        if _is_wheel_link_contribution(contribution)
    ]
    if not wheels:
        return 0.0
    return sum(float(item["assembly_center_of_mass_mm"][2]) for item in wheels) / len(wheels)


def compute_chassis_pitch_inertia_report(
    report: dict[str, Any],
    *,
    report_path: Path | None = None,
    chassis_mass_kg: float | None = None,
    multiplier: float = 9.0,
) -> dict[str, Any]:
    report_path = report_path or Path(".")
    mass_properties = report.get("mass_properties", {})
    contributions = list(mass_properties.get("contributions", []))
    occurrences = {
        str(item.get("occurrence_name")): item
        for item in report.get("chassis_collision_geometry", {}).get("occurrences", [])
    }
    included: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for contribution in contributions:
        occurrence_name = str(contribution.get("occurrence_name", ""))
        if _is_wheel_link_contribution(contribution):
            skipped.append({"occurrence_name": occurrence_name, "reason": "wheel_link"})
            continue
        occurrence = occurrences.get(occurrence_name)
        if occurrence is None:
            skipped.append({"occurrence_name": occurrence_name, "reason": "missing_occurrence_bounds"})
            continue
        included.append(contribution)

    total_mass_kg = sum(float(item["mass_kg"]) for item in included)
    if total_mass_kg <= 0.0:
        raise ValueError("No non-wheel chassis contributions with mass and occurrence bounds were found.")

    composite_com_flow_mm = [
        sum(float(item["mass_kg"]) * float(item["assembly_center_of_mass_mm"][index]) for item in included)
        / total_mass_kg
        for index in range(3)
    ]
    wheel_z_mm = _wheel_center_z_mm(contributions)
    chassis_joint_xyz_m = _float_list(
        report.get("chassis_joint_xyz_m", [0.0, 0.0, 0.0]),
        count=3,
        context="chassis_joint_xyz_m",
    )
    composite_com_chassis_link_m = {
        "x": composite_com_flow_mm[1] / 1000.0 - chassis_joint_xyz_m[0],
        "y": composite_com_flow_mm[0] / 1000.0 - chassis_joint_xyz_m[1],
        "z": (composite_com_flow_mm[2] - wheel_z_mm) / 1000.0 - chassis_joint_xyz_m[2],
    }

    rows: list[dict[str, Any]] = []
    local_total = 0.0
    parallel_axis_total = 0.0
    for contribution in included:
        occurrence_name = str(contribution["occurrence_name"])
        occurrence = occurrences[occurrence_name]
        mass_kg = float(contribution["mass_kg"])
        component_com_mm = _float_list(
            contribution["assembly_center_of_mass_mm"],
            count=3,
            context=f"{occurrence_name}.assembly_center_of_mass_mm",
        )
        flow_size_mm = _float_list(
            occurrence["flow_size_mm"],
            count=3,
            context=f"{occurrence_name}.flow_size_mm",
        )
        local_iyy = _box_pitch_inertia_kg_m2(mass_kg=mass_kg, flow_size_mm=flow_size_mm)
        d2 = sum(
            ((component_com_mm[index] - composite_com_flow_mm[index]) / 1000.0) ** 2
            for index in PERPENDICULAR_TO_PITCH_FLOW_INDICES
        )
        parallel_axis = mass_kg * d2
        local_total += local_iyy
        parallel_axis_total += parallel_axis
        rows.append(
            {
                "occurrence_name": occurrence_name,
                "part_id": contribution["part_id"],
                "mass_kg": mass_kg,
                "component_com_flow_mm": component_com_mm,
                "component_com_chassis_link_m": {
                    "x": component_com_mm[1] / 1000.0 - chassis_joint_xyz_m[0],
                    "y": component_com_mm[0] / 1000.0 - chassis_joint_xyz_m[1],
                    "z": (component_com_mm[2] - wheel_z_mm) / 1000.0 - chassis_joint_xyz_m[2],
                },
                "flow_size_mm": flow_size_mm,
                "local_iyy_kg_m2": local_iyy,
                "parallel_axis_iyy_kg_m2": parallel_axis,
                "total_iyy_kg_m2": local_iyy + parallel_axis,
                "local_inertia_source": "placed_axis_aligned_box_estimate",
                "mass_source": contribution.get("mass_source", ""),
                "metadata_status": contribution.get("metadata_status", ""),
            }
        )

    exported_mass_kg = float(chassis_mass_kg) if chassis_mass_kg is not None else _default_chassis_mass_kg(report)
    exported_iyy = _urdf_box_iyy_kg_m2(
        mass_kg=exported_mass_kg,
        size_m=_chassis_box_size_m(report, report_path),
    )
    composite_iyy = local_total + parallel_axis_total
    dojo_iyy = exported_iyy * multiplier

    return {
        "project_id": report.get("project_id"),
        "target_name": report.get("target", {}).get("name"),
        "output_path": report.get("output_path"),
        "component_local_inertia_note": (
            "Component local Iyy is estimated from each placed occurrence's world-axis-aligned bounding box "
            "because explicit per-part inertia tensors are mostly absent from current metadata."
        ),
        "component_count": len(rows),
        "skipped_contributions": skipped,
        "component_total_mass_kg": total_mass_kg,
        "component_com_flow_mm": composite_com_flow_mm,
        "component_com_chassis_link_m": composite_com_chassis_link_m,
        "exported_chassis_mass_kg": exported_mass_kg,
        "exported_chassis_com_m": report.get("nominal_chassis_com_m"),
        "exported_chassis_box_iyy_kg_m2": exported_iyy,
        "dojo_multiplier": multiplier,
        "dojo_multiplied_iyy_kg_m2": dojo_iyy,
        "component_local_iyy_sum_kg_m2": local_total,
        "component_parallel_axis_iyy_sum_kg_m2": parallel_axis_total,
        "component_composite_iyy_kg_m2": composite_iyy,
        "ratio_component_to_exported_iyy": composite_iyy / exported_iyy if exported_iyy else math.inf,
        "ratio_dojo_multiplied_to_exported_iyy": dojo_iyy / exported_iyy if exported_iyy else math.inf,
        "components": sorted(rows, key=lambda item: item["total_iyy_kg_m2"], reverse=True),
    }


def format_chassis_pitch_inertia_report(report: dict[str, Any], *, max_components: int | None = None) -> str:
    lines = [
        f"project: {report.get('project_id')}",
        f"target: {report.get('target_name')}",
        f"component_count: {report['component_count']}",
        f"component_total_mass_kg: {report['component_total_mass_kg']:.9g}",
        "component_com_chassis_link_m: "
        f"x={report['component_com_chassis_link_m']['x']:.9g} "
        f"y={report['component_com_chassis_link_m']['y']:.9g} "
        f"z={report['component_com_chassis_link_m']['z']:.9g}",
        f"exported_chassis_mass_kg: {report['exported_chassis_mass_kg']:.9g}",
        f"exported_chassis_com_m: {report.get('exported_chassis_com_m')}",
        f"exported_chassis_box_iyy_kg_m2: {report['exported_chassis_box_iyy_kg_m2']:.9g}",
        f"dojo_multiplier: {report['dojo_multiplier']:.9g}",
        f"dojo_multiplied_iyy_kg_m2: {report['dojo_multiplied_iyy_kg_m2']:.9g}",
        f"component_local_iyy_sum_kg_m2: {report['component_local_iyy_sum_kg_m2']:.9g}",
        f"component_parallel_axis_iyy_sum_kg_m2: {report['component_parallel_axis_iyy_sum_kg_m2']:.9g}",
        f"component_composite_iyy_kg_m2: {report['component_composite_iyy_kg_m2']:.9g}",
        f"ratio_component_to_exported_iyy: {report['ratio_component_to_exported_iyy']:.9g}",
        f"ratio_dojo_multiplied_to_exported_iyy: {report['ratio_dojo_multiplied_to_exported_iyy']:.9g}",
        "",
        report["component_local_inertia_note"],
        "",
        "components:",
        "occurrence, part, mass_kg, com_chassis_m[x,y,z], local_iyy, parallel_axis_iyy, total_iyy, source",
    ]
    components = report["components"]
    if max_components is not None:
        components = components[:max_components]
    for item in components:
        com = item["component_com_chassis_link_m"]
        lines.append(
            f"{item['occurrence_name']}, {item['part_id']}, {item['mass_kg']:.9g}, "
            f"[{com['x']:.9g}, {com['y']:.9g}, {com['z']:.9g}], "
            f"{item['local_iyy_kg_m2']:.9g}, {item['parallel_axis_iyy_kg_m2']:.9g}, "
            f"{item['total_iyy_kg_m2']:.9g}, {item['local_inertia_source']}"
        )
    if report["skipped_contributions"]:
        lines.extend(["", "skipped_contributions:"])
        for item in report["skipped_contributions"]:
            lines.append(f"{item['occurrence_name']}: {item['reason']}")
    return "\n".join(lines)


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report component-summed chassis pitch inertia from a Flow CAD URDF report.")
    parser.add_argument("report", type=Path, help="Path to an exported .urdf.report.json file.")
    parser.add_argument("--chassis-mass-kg", type=float, default=None, help="Override the mass used for the exported box Iyy.")
    parser.add_argument("--multiplier", type=float, default=9.0, help="Dojo chassis_pitch_inertia_multiplier to compare.")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--max-components", type=int, default=None, help="Limit text output to the top N component Iyy contributors.")
    args = parser.parse_args(argv)

    payload = load_report(args.report)
    result = compute_chassis_pitch_inertia_report(
        payload,
        report_path=args.report,
        chassis_mass_kg=args.chassis_mass_kg,
        multiplier=args.multiplier,
    )
    if args.format == "json":
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(format_chassis_pitch_inertia_report(result, max_components=args.max_components))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
