from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from flow_cad.project import FlowCadProject


class UrdfExportError(RuntimeError):
    status_code = 400


class UrdfTargetNotFoundError(UrdfExportError):
    status_code = 404


class UrdfOutputExistsError(UrdfExportError):
    status_code = 409


@dataclass(frozen=True)
class UrdfExportTarget:
    name: str
    label: str = ""
    description: str = ""
    profile: str = "active"
    default_output_path: str | Path | None = None
    kind: str = "dojo_balance_bot"
    include_references: bool = True
    assembly_id: str | None = None
    robot_name: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def resolved_default_output_path(self, project: FlowCadProject) -> Path:
        if self.default_output_path is not None:
            value = Path(self.default_output_path).expanduser()
            return value if value.is_absolute() else project.root / value
        return project.paths.exports / "urdf" / f"{self.name}.urdf"

    def to_payload(self, project: FlowCadProject) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label or self.name,
            "description": self.description,
            "profile": self.profile,
            "kind": self.kind,
            "include_references": self.include_references,
            "assembly_id": self.assembly_id,
            "robot_name": self.robot_name or self.name,
            "default_output_path": str(self.resolved_default_output_path(project)),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class MassContribution:
    occurrence_name: str
    part_id: str
    mass_kg: float
    local_center_of_mass_mm: tuple[float, float, float]
    assembly_center_of_mass_mm: tuple[float, float, float]
    inertia_kg_m2: tuple[float, ...] | None
    center_source: str
    mass_source: str
    role: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "occurrence_name": self.occurrence_name,
            "part_id": self.part_id,
            "mass_kg": self.mass_kg,
            "local_center_of_mass_mm": list(self.local_center_of_mass_mm),
            "assembly_center_of_mass_mm": list(self.assembly_center_of_mass_mm),
            "inertia_kg_m2": list(self.inertia_kg_m2) if self.inertia_kg_m2 is not None else None,
            "center_source": self.center_source,
            "mass_source": self.mass_source,
            "role": self.role,
        }


@dataclass(frozen=True)
class AssemblyMassProperties:
    profile: str
    assembly_id: str | None
    total_mass_kg: float
    center_of_mass_mm: tuple[float, float, float] | None
    known_mass_occurrence_count: int
    total_occurrence_count: int
    missing_mass_occurrences: tuple[str, ...]
    missing_com_occurrences: tuple[str, ...]
    missing_inertia_occurrences: tuple[str, ...]
    contributions: tuple[MassContribution, ...]

    @property
    def mass_complete(self) -> bool:
        return not self.missing_mass_occurrences

    @property
    def center_of_mass_complete(self) -> bool:
        return bool(self.contributions) and not self.missing_mass_occurrences and not self.missing_com_occurrences

    def to_payload(self, *, include_contributions: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "profile": self.profile,
            "assembly_id": self.assembly_id,
            "total_mass_kg": self.total_mass_kg,
            "center_of_mass_mm": list(self.center_of_mass_mm) if self.center_of_mass_mm is not None else None,
            "known_mass_occurrence_count": self.known_mass_occurrence_count,
            "total_occurrence_count": self.total_occurrence_count,
            "missing_mass_occurrences": list(self.missing_mass_occurrences),
            "missing_com_occurrences": list(self.missing_com_occurrences),
            "missing_inertia_occurrences": list(self.missing_inertia_occurrences),
            "mass_complete": self.mass_complete,
            "center_of_mass_complete": self.center_of_mass_complete,
        }
        if include_contributions:
            payload["contributions"] = [contribution.to_payload() for contribution in self.contributions]
        return payload


PART_METADATA_OVERRIDE_FIELDS = {
    "material",
    "display_color",
    "mass_kg",
    "center_of_mass_mm",
    "inertia_kg_m2",
    "mass_source",
    "metadata_status",
    "metadata_notes",
}


DOJO_BALANCE_BOT_DESIGN_LEDGER = {
    "target_consumers": ["DojoV2 BalanceBotSimAdapter", "PyBullet"],
    "units": "URDF meters/kilograms/radians; Flow CAD source dimensions are millimeters.",
    "frames": {
        "flow_cad": "+X lateral, +Y fore/aft, +Z up",
        "urdf": "+X fore/aft, +Y lateral, +Z up",
    },
    "links": {
        "base_link": "Root frame at wheel axle midpoint. It carries a simple axle cylinder.",
        "chassis_link": "Simplified chassis/body box fixed above base_link. Inertial mass/COM/inertia stay as Dojo placeholders.",
        "left_wheel/right_wheel": "Primitive cylinders centered at the wheel joints.",
    },
    "joints": {
        "chassis_joint": "Fixed transform from wheel axle midpoint to simplified chassis box center.",
        "left_wheel_joint/right_wheel_joint": "Continuous wheel joints. Axis is +Y in each joint frame to match existing Dojo adapter names.",
    },
    "assumptions": [
        "Collision geometry is intentionally primitive for training stability.",
        "Dojo randomization fills CHASSIS_MASS, COM_X, COM_Z, IXX, IYY, and IZZ at runtime.",
        "Nominal assembly COM is reported as recommended config data, not baked into the placeholder template.",
    ],
}


def load_part_metadata_overrides(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    parts = payload.get("parts") if isinstance(payload, dict) else None
    if not isinstance(parts, dict):
        return {}
    return {
        str(part_id): {
            key: value
            for key, value in override.items()
            if key in PART_METADATA_OVERRIDE_FIELDS
        }
        for part_id, override in parts.items()
        if isinstance(override, dict)
    }


def _coerce_target(target: Any) -> UrdfExportTarget:
    if isinstance(target, UrdfExportTarget):
        return target
    if isinstance(target, Mapping):
        return UrdfExportTarget(
            name=str(target["name"]),
            label=str(target.get("label") or ""),
            description=str(target.get("description") or ""),
            profile=str(target.get("profile") or "active"),
            default_output_path=target.get("default_output_path"),
            kind=str(target.get("kind") or "dojo_balance_bot"),
            include_references=bool(target.get("include_references", True)),
            assembly_id=str(target["assembly_id"]) if target.get("assembly_id") else None,
            robot_name=str(target.get("robot_name") or ""),
            metadata=dict(target.get("metadata") or {}),
        )
    raise UrdfExportError(f"Invalid URDF export target: {target!r}")


def _target_map(project: FlowCadProject, params: Any) -> dict[str, UrdfExportTarget]:
    targets = [
        _coerce_target(target)
        for target in project.iter_urdf_targets(params=params)
    ]
    return {target.name: target for target in targets}


def _metadata_value(definition: Any, overrides: Mapping[str, Mapping[str, Any]], field: str, default: Any = None) -> Any:
    override = overrides.get(str(getattr(definition, "id", "")), {})
    if field in override:
        return override[field]
    return getattr(definition, field, default)


def _float_tuple(value: Any, size: int) -> tuple[float, ...] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != size:
        return None
    try:
        return tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None


def _shape_center_mm(shape: Any) -> tuple[float, float, float]:
    from build123d import CenterOf

    center = shape.center(CenterOf.MASS)
    return (float(center.X), float(center.Y), float(center.Z))


def _rotate_point_xyz(point: tuple[float, float, float], rotation_deg: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = point
    rx, ry, rz = (math.radians(value) for value in rotation_deg)

    cos_x, sin_x = math.cos(rx), math.sin(rx)
    y, z = y * cos_x - z * sin_x, y * sin_x + z * cos_x

    cos_y, sin_y = math.cos(ry), math.sin(ry)
    x, z = x * cos_y + z * sin_y, -x * sin_y + z * cos_y

    cos_z, sin_z = math.cos(rz), math.sin(rz)
    x, y = x * cos_z - y * sin_z, x * sin_z + y * cos_z
    return (x, y, z)


def _transform_point(
    point: tuple[float, float, float],
    location: tuple[float, float, float],
    rotation: tuple[float, float, float],
) -> tuple[float, float, float]:
    rx, ry, rz = _rotate_point_xyz(point, rotation)
    return (rx + location[0], ry + location[1], rz + location[2])


def compute_assembly_mass_properties(
    project: FlowCadProject,
    params: Any,
    *,
    profile: str = "active",
    assembly_id: str | None = None,
    include_references: bool = True,
    metadata_overrides: Mapping[str, Mapping[str, Any]] | None = None,
) -> AssemblyMassProperties:
    resolved_assembly_id = assembly_id or project.active_assembly_id
    overrides = metadata_overrides or {}
    definitions = {
        str(definition.id): definition
        for definition in project.iter_part_definitions_for_profile(profile, include_references=include_references)
    }
    placements = list(
        project.get_assembly_placements(
            params,
            include_references=include_references,
            assembly_id=resolved_assembly_id,
        )
    )
    local_centers: dict[str, tuple[tuple[float, float, float], str]] = {}
    contributions: list[MassContribution] = []
    missing_mass: list[str] = []
    missing_com: list[str] = []
    missing_inertia: list[str] = []
    weighted = [0.0, 0.0, 0.0]
    total_mass = 0.0

    for placement in placements:
        part_id = str(placement["part_key"])
        occurrence_name = str(placement["name"])
        definition = definitions.get(part_id)
        if definition is None:
            missing_mass.append(f"{occurrence_name}:{part_id}:definition_missing")
            continue

        try:
            mass = float(_metadata_value(definition, overrides, "mass_kg"))
        except (TypeError, ValueError):
            missing_mass.append(f"{occurrence_name}:{part_id}")
            continue
        if mass <= 0.0 or not math.isfinite(mass):
            missing_mass.append(f"{occurrence_name}:{part_id}")
            continue

        local_center = _float_tuple(_metadata_value(definition, overrides, "center_of_mass_mm"), 3)
        center_source = "explicit_metadata"
        if local_center is None:
            cached = local_centers.get(part_id)
            if cached is None:
                try:
                    cached = (_shape_center_mm(definition.factory(params)), "geometry_estimate")
                except Exception:
                    cached = None
            if cached is None:
                missing_com.append(f"{occurrence_name}:{part_id}")
                continue
            local_centers[part_id] = cached
            local_center, center_source = cached

        inertia = _float_tuple(_metadata_value(definition, overrides, "inertia_kg_m2"), 6)
        if inertia is None:
            missing_inertia.append(f"{occurrence_name}:{part_id}")

        location = _float_tuple(placement.get("location"), 3) or (0.0, 0.0, 0.0)
        rotation = _float_tuple(placement.get("rotation"), 3) or (0.0, 0.0, 0.0)
        assembly_center = _transform_point(local_center, location, rotation)
        contribution = MassContribution(
            occurrence_name=occurrence_name,
            part_id=part_id,
            mass_kg=mass,
            local_center_of_mass_mm=local_center,
            assembly_center_of_mass_mm=assembly_center,
            inertia_kg_m2=inertia,
            center_source=center_source,
            mass_source=str(_metadata_value(definition, overrides, "mass_source", "unset")),
            role=str(getattr(definition, "role", "")),
        )
        contributions.append(contribution)
        total_mass += mass
        weighted[0] += mass * assembly_center[0]
        weighted[1] += mass * assembly_center[1]
        weighted[2] += mass * assembly_center[2]

    center = (
        (weighted[0] / total_mass, weighted[1] / total_mass, weighted[2] / total_mass)
        if total_mass > 0.0
        else None
    )
    return AssemblyMassProperties(
        profile=profile,
        assembly_id=resolved_assembly_id,
        total_mass_kg=total_mass,
        center_of_mass_mm=center,
        known_mass_occurrence_count=len(contributions),
        total_occurrence_count=len(placements),
        missing_mass_occurrences=tuple(missing_mass),
        missing_com_occurrences=tuple(missing_com),
        missing_inertia_occurrences=tuple(missing_inertia),
        contributions=tuple(contributions),
    )


def _path_is_within(path: Path, root: Path) -> bool:
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def _validate_output_path(project: FlowCadProject, output_path: str | Path, *, overwrite: bool) -> Path:
    raw_path = Path(output_path).expanduser()
    path = raw_path if raw_path.is_absolute() else project.root / raw_path
    path = path.resolve()
    if path.suffix.lower() != ".urdf":
        raise UrdfExportError("URDF output path must end with .urdf.")
    if not (_path_is_within(path, Path.home()) or _path_is_within(path, project.root)):
        raise UrdfExportError(f"URDF output path must be under {Path.home()} or the project root.")
    if not path.parent.exists():
        raise UrdfExportError(f"URDF output parent directory does not exist: {path.parent}")
    if path.exists() and path.is_dir():
        raise UrdfExportError(f"URDF output path is a directory: {path}")
    if path.exists() and not overwrite:
        raise UrdfOutputExistsError(f"URDF output already exists: {path}")
    return path


def _fmt(value: float | str) -> str:
    if isinstance(value, str):
        return value
    if abs(value) < 5e-10:
        value = 0.0
    return f"{value:.9f}".rstrip("0").rstrip(".")


def _origin(parent: ET.Element, xyz: Iterable[float | str], rpy: Iterable[float | str] = (0.0, 0.0, 0.0)) -> ET.Element:
    return ET.SubElement(parent, "origin", {"xyz": " ".join(_fmt(value) for value in xyz), "rpy": " ".join(_fmt(value) for value in rpy)})


def _inertia(parent: ET.Element, *, ixx: float | str, ixy: float | str, ixz: float | str, iyy: float | str, iyz: float | str, izz: float | str) -> None:
    ET.SubElement(
        parent,
        "inertia",
        {
            "ixx": _fmt(ixx),
            "ixy": _fmt(ixy),
            "ixz": _fmt(ixz),
            "iyy": _fmt(iyy),
            "iyz": _fmt(iyz),
            "izz": _fmt(izz),
        },
    )


def _material(parent: ET.Element, name: str, rgba: str) -> None:
    material = ET.SubElement(parent, "material", {"name": name})
    ET.SubElement(material, "color", {"rgba": rgba})


def _add_cylinder_link(
    robot: ET.Element,
    *,
    name: str,
    radius_m: float,
    length_m: float,
    mass_kg: float,
    material_name: str,
    rpy: tuple[float, float, float] = (math.pi / 2.0, 0.0, 0.0),
) -> None:
    link = ET.SubElement(robot, "link", {"name": name})
    for tag in ("visual", "collision"):
        element = ET.SubElement(link, tag)
        _origin(element, (0.0, 0.0, 0.0), rpy)
        geometry = ET.SubElement(element, "geometry")
        ET.SubElement(geometry, "cylinder", {"radius": _fmt(radius_m), "length": _fmt(length_m)})
        if tag == "visual":
            ET.SubElement(element, "material", {"name": material_name})
    inertial = ET.SubElement(link, "inertial")
    ET.SubElement(inertial, "mass", {"value": _fmt(mass_kg)})
    _origin(inertial, (0.0, 0.0, 0.0))
    radius_sq = radius_m * radius_m
    length_sq = length_m * length_m
    i_axis = 0.5 * mass_kg * radius_sq
    i_cross = (1.0 / 12.0) * mass_kg * (3.0 * radius_sq + length_sq)
    _inertia(inertial, ixx=i_cross, ixy=0.0, ixz=0.0, iyy=i_axis, iyz=0.0, izz=i_cross)


def _add_box_link(
    robot: ET.Element,
    *,
    name: str,
    size_m: tuple[float, float, float],
    material_name: str,
) -> None:
    link = ET.SubElement(robot, "link", {"name": name})
    for tag in ("visual", "collision"):
        element = ET.SubElement(link, tag)
        _origin(element, (0.0, 0.0, 0.0))
        geometry = ET.SubElement(element, "geometry")
        ET.SubElement(geometry, "box", {"size": " ".join(_fmt(value) for value in size_m)})
        if tag == "visual":
            ET.SubElement(element, "material", {"name": material_name})
    inertial = ET.SubElement(link, "inertial")
    ET.SubElement(inertial, "mass", {"value": "{CHASSIS_MASS}"})
    _origin(inertial, ("{COM_X}", 0.0, "{COM_Z}"))
    _inertia(inertial, ixx="{IXX}", ixy=0.0, ixz=0.0, iyy="{IYY}", iyz=0.0, izz="{IZZ}")


def _add_fixed_joint(
    robot: ET.Element,
    *,
    name: str,
    parent: str,
    child: str,
    xyz: tuple[float, float, float],
) -> None:
    joint = ET.SubElement(robot, "joint", {"name": name, "type": "fixed"})
    ET.SubElement(joint, "parent", {"link": parent})
    ET.SubElement(joint, "child", {"link": child})
    _origin(joint, xyz)


def _add_wheel_joint(robot: ET.Element, *, name: str, parent: str, child: str, y_m: float) -> None:
    joint = ET.SubElement(robot, "joint", {"name": name, "type": "continuous"})
    ET.SubElement(joint, "parent", {"link": parent})
    ET.SubElement(joint, "child", {"link": child})
    _origin(joint, (0.0, y_m, 0.0))
    ET.SubElement(joint, "axis", {"xyz": "0 1 0"})


def _bounds_from_shape(shape: Any) -> dict[str, tuple[float, float, float]]:
    bb = shape.bounding_box()
    minimum = (float(bb.min.X), float(bb.min.Y), float(bb.min.Z))
    maximum = (float(bb.max.X), float(bb.max.Y), float(bb.max.Z))
    size = tuple(maximum[index] - minimum[index] for index in range(3))
    center = tuple((minimum[index] + maximum[index]) / 2.0 for index in range(3))
    return {"min": minimum, "max": maximum, "size": size, "center": center}


def _assembly_bounds(project: FlowCadProject, params: Any, *, profile: str, assembly_id: str | None) -> dict[str, tuple[float, float, float]] | None:
    try:
        placed_part_ids = {
            str(placement["part_key"])
            for placement in project.get_assembly_placements(
                params,
                include_references=False,
                assembly_id=assembly_id,
            )
        }
        definitions = [
            definition
            for definition in project.iter_part_definitions_for_profile(profile, include_references=False)
            if str(definition.id) in placed_part_ids
        ]
        parts = {str(definition.id): definition.factory(params) for definition in definitions}
        assembly = project.make_assembly(
            params,
            parts,
            include_references=False,
            assembly_id=assembly_id,
        )
        return _bounds_from_shape(assembly)
    except Exception:
        return None


def _wheel_contributions(mass_properties: AssemblyMassProperties) -> list[MassContribution]:
    return [
        contribution
        for contribution in mass_properties.contributions
        if "wheel" in contribution.part_id and "reference" in contribution.part_id
    ]


def _estimate_wheel_base_m(mass_properties: AssemblyMassProperties, target: UrdfExportTarget, params: Any) -> float:
    metadata = dict(target.metadata)
    if "wheel_base_m" in metadata:
        return float(metadata["wheel_base_m"])
    wheel_contributions = _wheel_contributions(mass_properties)
    left = next((item for item in wheel_contributions if item.occurrence_name.startswith("left")), None)
    right = next((item for item in wheel_contributions if item.occurrence_name.startswith("right")), None)
    if left is not None and right is not None:
        return abs(right.assembly_center_of_mass_mm[0] - left.assembly_center_of_mass_mm[0]) / 1000.0
    if hasattr(params, "wheel_overall_width") and hasattr(params, "wheel_width"):
        return (float(params.wheel_overall_width) - float(params.wheel_width)) / 1000.0
    return 0.4064


def _estimate_wheel_radius_m(target: UrdfExportTarget, params: Any) -> float:
    metadata = dict(target.metadata)
    if "wheel_radius_m" in metadata:
        return float(metadata["wheel_radius_m"])
    if hasattr(params, "wheel_diameter"):
        return float(params.wheel_diameter) / 2000.0
    return 0.0762


def _estimate_wheel_width_m(target: UrdfExportTarget, params: Any) -> float:
    metadata = dict(target.metadata)
    if "wheel_width_m" in metadata:
        return float(metadata["wheel_width_m"])
    if hasattr(params, "wheel_width"):
        return float(params.wheel_width) / 1000.0
    return 0.05715


def _estimate_wheel_mass_kg(mass_properties: AssemblyMassProperties, target: UrdfExportTarget) -> float:
    metadata = dict(target.metadata)
    if "wheel_mass_kg" in metadata:
        return float(metadata["wheel_mass_kg"])
    wheels = _wheel_contributions(mass_properties)
    if wheels:
        return sum(wheel.mass_kg for wheel in wheels) / len(wheels)
    return 0.35


def _dojo_config_recommendations(
    *,
    output_path: Path,
    wheel_radius_m: float,
    wheel_base_m: float,
    chassis_mass_kg: float,
    nominal_chassis_com_m: tuple[float, float],
) -> dict[str, Any]:
    return {
        "embodiment": {
            "urdf_template_path": str(output_path),
            "urdf_chassis_link_name": "chassis_link",
            "wheel_radius_m": wheel_radius_m,
            "wheel_base_m": wheel_base_m,
        },
        "randomization": {
            "urdf_chassis_mass_choices": [chassis_mass_kg],
            "com_dx_range": [nominal_chassis_com_m[0], nominal_chassis_com_m[0]],
            "com_dz_range": [nominal_chassis_com_m[1], nominal_chassis_com_m[1]],
        },
    }


def _build_dojo_balance_bot_template(
    project: FlowCadProject,
    params: Any,
    target: UrdfExportTarget,
    output_path: Path,
    mass_properties: AssemblyMassProperties,
) -> tuple[str, dict[str, Any]]:
    assembly_id = target.assembly_id or project.active_assembly_id
    bounds = _assembly_bounds(project, params, profile=target.profile, assembly_id=assembly_id)
    wheel_radius_m = _estimate_wheel_radius_m(target, params)
    wheel_width_m = _estimate_wheel_width_m(target, params)
    wheel_base_m = _estimate_wheel_base_m(mass_properties, target, params)
    wheel_mass_kg = _estimate_wheel_mass_kg(mass_properties, target)
    axle_radius_m = float(dict(target.metadata).get("axle_radius_m", 0.0127))
    axle_mass_kg = float(dict(target.metadata).get("axle_mass_kg", 0.1))

    if bounds is None:
        chassis_size_m = (0.254, 0.2286, 0.254)
        chassis_center_flow_mm = (0.0, 0.0, wheel_radius_m * 500.0)
    else:
        flow_size = bounds["size"]
        flow_center = bounds["center"]
        chassis_size_m = (flow_size[1] / 1000.0, flow_size[0] / 1000.0, flow_size[2] / 1000.0)
        chassis_center_flow_mm = flow_center

    wheel_center_z_mm = 0.0
    wheel_contributions = _wheel_contributions(mass_properties)
    if wheel_contributions:
        wheel_center_z_mm = sum(item.assembly_center_of_mass_mm[2] for item in wheel_contributions) / len(wheel_contributions)

    chassis_joint_xyz = (
        chassis_center_flow_mm[1] / 1000.0,
        0.0,
        (chassis_center_flow_mm[2] - wheel_center_z_mm) / 1000.0,
    )
    assembly_com = mass_properties.center_of_mass_mm
    nominal_com_x_m = 0.0
    nominal_com_z_m = 0.0
    if assembly_com is not None:
        nominal_com_x_m = assembly_com[1] / 1000.0 - chassis_joint_xyz[0]
        nominal_com_z_m = (assembly_com[2] - wheel_center_z_mm) / 1000.0 - chassis_joint_xyz[2]

    wheel_total_mass = sum(item.mass_kg for item in wheel_contributions[:2])
    chassis_mass_kg = max(mass_properties.total_mass_kg - wheel_total_mass - axle_mass_kg, 0.001)

    robot = ET.Element("robot", {"name": target.robot_name or "B2_v2"})
    _material(robot, "matte_black", "0.02 0.02 0.02 1.0")
    _material(robot, "tire_rubber", "0.12 0.12 0.13 1.0")
    _material(robot, "accent_green", "0.0 1.0 0.15 1.0")

    _add_cylinder_link(
        robot,
        name="base_link",
        radius_m=axle_radius_m,
        length_m=wheel_base_m,
        mass_kg=axle_mass_kg,
        material_name="matte_black",
    )
    _add_fixed_joint(robot, name="chassis_joint", parent="base_link", child="chassis_link", xyz=chassis_joint_xyz)
    _add_box_link(robot, name="chassis_link", size_m=chassis_size_m, material_name="matte_black")

    _add_cylinder_link(
        robot,
        name="left_wheel",
        radius_m=wheel_radius_m,
        length_m=wheel_width_m,
        mass_kg=wheel_mass_kg,
        material_name="tire_rubber",
    )
    _add_wheel_joint(robot, name="left_wheel_joint", parent="base_link", child="left_wheel", y_m=wheel_base_m / 2.0)
    _add_cylinder_link(
        robot,
        name="right_wheel",
        radius_m=wheel_radius_m,
        length_m=wheel_width_m,
        mass_kg=wheel_mass_kg,
        material_name="tire_rubber",
    )
    _add_wheel_joint(robot, name="right_wheel_joint", parent="base_link", child="right_wheel", y_m=-wheel_base_m / 2.0)

    ET.indent(robot, space="  ")
    xml_text = '<?xml version="1.0"?>\n' + ET.tostring(robot, encoding="unicode") + "\n"
    metrics = {
        "design_ledger": DOJO_BALANCE_BOT_DESIGN_LEDGER,
        "wheel_radius_m": wheel_radius_m,
        "wheel_width_m": wheel_width_m,
        "wheel_base_m": wheel_base_m,
        "wheel_mass_kg": wheel_mass_kg,
        "wheel_total_mass_kg": wheel_total_mass,
        "chassis_box_size_m": list(chassis_size_m),
        "chassis_joint_xyz_m": list(chassis_joint_xyz),
        "recommended_chassis_mass_kg": chassis_mass_kg,
        "nominal_chassis_com_m": {
            "x": nominal_com_x_m,
            "z": nominal_com_z_m,
        },
        "recommended_dojo_config": _dojo_config_recommendations(
            output_path=output_path,
            wheel_radius_m=wheel_radius_m,
            wheel_base_m=wheel_base_m,
            chassis_mass_kg=chassis_mass_kg,
            nominal_chassis_com_m=(nominal_com_x_m, nominal_com_z_m),
        ),
    }
    return xml_text, metrics


def validate_urdf_xml(xml_text: str) -> dict[str, Any]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise UrdfExportError(f"Generated URDF is not valid XML: {exc}") from exc
    if root.tag != "robot":
        raise UrdfExportError("Generated URDF root must be <robot>.")
    if not root.attrib.get("name"):
        raise UrdfExportError("Generated URDF robot name is required.")
    links = [link.attrib.get("name", "") for link in root.findall("link")]
    joints = root.findall("joint")
    if not links:
        raise UrdfExportError("Generated URDF must contain at least one link.")
    if len(set(links)) != len(links) or any(not link for link in links):
        raise UrdfExportError("Generated URDF link names must be unique and non-empty.")
    link_names = set(links)
    children: set[str] = set()
    joint_names: list[str] = []
    for joint in joints:
        name = joint.attrib.get("name", "")
        joint_names.append(name)
        if not name:
            raise UrdfExportError("Generated URDF joint names must be non-empty.")
        parent = joint.find("parent")
        child = joint.find("child")
        parent_name = parent.attrib.get("link", "") if parent is not None else ""
        child_name = child.attrib.get("link", "") if child is not None else ""
        if parent_name not in link_names or child_name not in link_names:
            raise UrdfExportError(f"Generated URDF joint {name!r} references an unknown link.")
        if child_name in children:
            raise UrdfExportError(f"Generated URDF link {child_name!r} has multiple parent joints.")
        children.add(child_name)
        if joint.attrib.get("type") != "fixed":
            axis = joint.find("axis")
            if axis is None or not axis.attrib.get("xyz"):
                raise UrdfExportError(f"Generated URDF movable joint {name!r} must define an axis.")
    if len(set(joint_names)) != len(joint_names):
        raise UrdfExportError("Generated URDF joint names must be unique.")
    roots = link_names - children
    if len(roots) != 1:
        raise UrdfExportError("Generated URDF must have exactly one root link.")
    return {
        "robot_name": root.attrib["name"],
        "link_count": len(links),
        "joint_count": len(joints),
        "root_link": next(iter(roots)),
    }


class UrdfExportService:
    def __init__(
        self,
        project: FlowCadProject,
        *,
        params: Any | None = None,
        metadata_overrides_path: Path | None = None,
    ):
        self.project = project
        self.params = params or project.make_params()
        self.metadata_overrides_path = metadata_overrides_path or project.paths.local_state / "part-metadata-overrides.json"

    def list_targets(self) -> dict[str, Any]:
        targets = _target_map(self.project, self.params)
        return {
            "ok": True,
            "project_id": self.project.project_id,
            "targets": [target.to_payload(self.project) for target in targets.values()],
        }

    def compute_mass_properties(
        self,
        *,
        profile: str = "active",
        assembly_id: str | None = None,
        include_references: bool = True,
    ) -> AssemblyMassProperties:
        return compute_assembly_mass_properties(
            self.project,
            self.params,
            profile=profile,
            assembly_id=assembly_id,
            include_references=include_references,
            metadata_overrides=load_part_metadata_overrides(self.metadata_overrides_path),
        )

    def export(
        self,
        *,
        target_name: str,
        output_path: str | Path | None = None,
        profile: str | None = None,
        overwrite: bool = False,
    ) -> dict[str, Any]:
        targets = _target_map(self.project, self.params)
        target = targets.get(target_name)
        if target is None:
            raise UrdfTargetNotFoundError(f"URDF export target not found: {target_name}")
        target_profile = (profile or target.profile or "active").strip() or "active"
        target = UrdfExportTarget(
            **{
                **target.__dict__,
                "profile": target_profile,
            }
        )
        resolved_output = _validate_output_path(
            self.project,
            output_path or target.resolved_default_output_path(self.project),
            overwrite=overwrite,
        )
        mass_properties = self.compute_mass_properties(
            profile=target.profile,
            assembly_id=target.assembly_id,
            include_references=target.include_references,
        )
        if target.kind != "dojo_balance_bot":
            raise UrdfExportError(f"Unsupported URDF target kind: {target.kind}")

        xml_text, target_metrics = _build_dojo_balance_bot_template(
            self.project,
            self.params,
            target,
            resolved_output,
            mass_properties,
        )
        validation = validate_urdf_xml(xml_text)
        resolved_output.write_text(xml_text, encoding="utf-8")
        report_path = resolved_output.with_suffix(resolved_output.suffix + ".report.json")
        report = {
            "schema_version": 1,
            "generated_at": datetime.now(UTC).isoformat(),
            "project_id": self.project.project_id,
            "target": target.to_payload(self.project),
            "profile": target.profile,
            "output_path": str(resolved_output),
            "report_path": str(report_path),
            "validation": validation,
            "mass_properties": mass_properties.to_payload(include_contributions=True),
            **target_metrics,
        }
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {
            "ok": True,
            "target": target.name,
            "profile": target.profile,
            "output_path": str(resolved_output),
            "report_path": str(report_path),
            "mass_properties": mass_properties.to_payload(include_contributions=False),
            "wheel_radius_m": target_metrics["wheel_radius_m"],
            "wheel_base_m": target_metrics["wheel_base_m"],
            "recommended_dojo_config": target_metrics["recommended_dojo_config"],
            "validation": validation,
        }
