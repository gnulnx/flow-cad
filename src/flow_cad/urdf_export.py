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
    metadata_status: str
    metadata_notes: str
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
            "metadata_status": self.metadata_status,
            "metadata_notes": self.metadata_notes,
            "role": self.role,
        }


@dataclass(frozen=True)
class UrdfBoxPrimitive:
    name: str
    occurrence_name: str
    part_id: str
    size_m: tuple[float, float, float]
    origin_xyz_m: tuple[float, float, float]
    flow_center_mm: tuple[float, float, float]
    flow_size_mm: tuple[float, float, float]
    role: str
    include_collision: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "occurrence_name": self.occurrence_name,
            "part_id": self.part_id,
            "size_m": list(self.size_m),
            "origin_xyz_m": list(self.origin_xyz_m),
            "flow_center_mm": list(self.flow_center_mm),
            "flow_size_mm": list(self.flow_size_mm),
            "role": self.role,
            "include_collision": self.include_collision,
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
        "chassis_link": (
            "Collapsed non-wheel body link fixed above base_link. The inertial mass/COM/inertia stay as "
            "Dojo placeholders. Visual geometry is emitted as axis-aligned boxes from active assembly "
            "occurrences, while collision geometry is limited to selected external/contact envelopes."
        ),
        "left_wheel/right_wheel": "Primitive cylinders centered at the wheel joints.",
    },
    "joints": {
        "chassis_joint": "Fixed transform from wheel axle midpoint to simplified chassis box center.",
        "left_wheel_joint/right_wheel_joint": "Continuous wheel joints. Axis is +Y in each joint frame to match existing Dojo adapter names.",
    },
    "assumptions": [
        "Collision geometry is intentionally primitive for training stability.",
        "Dojo randomization fills CHASSIS_MASS, COM_X, COM_Z, IXX, IYY, and IZZ at runtime.",
        "Recommended Dojo COM is the collapsed non-wheel body COM after subtracting wheel links and the fixed base dummy mass.",
        "Occurrence boxes are world-axis-aligned approximations of CAD occurrence bounds, expressed in the chassis_link frame.",
        "The chassis sizing box used by Dojo is written as non-rendered flow_cad_chassis_box metadata.",
    ],
}


DOJO_BALANCE_BOT_COLLISION_FORCE_INCLUDE_OCCURRENCES = {
    "left_wheel_box_body",
    "left_wheel_box_top_lid",
    "left_wheel_box_bottom_lid",
    "right_wheel_box_body",
    "right_wheel_box_top_lid",
    "right_wheel_box_bottom_lid",
    "battery_compartment",
    "buck_power_tray",
    "flipsky_vesc_tray",
    "bosgame_compute_shelf",
    "bosgame_compute_top_plate",
}


DOJO_BALANCE_BOT_COLLISION_EXCLUDED_NAME_TOKENS = (
    "_wire_grommet",
    "_electronics_cover",
    "_front_keeper",
    "_tight_insert",
    "_tpu_sleeve",
    "_tpu_mount",
    "_power_switch_bridge",
    "_slide_cradle",
    "_front_panel",
    "_rear_panel",
    "_left_panel",
    "_right_panel",
)


def _include_chassis_collision_occurrence(occurrence_name: str) -> bool:
    if occurrence_name in DOJO_BALANCE_BOT_COLLISION_FORCE_INCLUDE_OCCURRENCES:
        return True
    return not any(token in occurrence_name for token in DOJO_BALANCE_BOT_COLLISION_EXCLUDED_NAME_TOKENS)


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
            metadata_status=str(_metadata_value(definition, overrides, "metadata_status", "")),
            metadata_notes=str(_metadata_value(definition, overrides, "metadata_notes", "")),
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
    include_visual: bool = True,
    include_collision: bool = True,
    geometry_name: str | None = None,
    inertial_mass: float | str = "{CHASSIS_MASS}",
    inertial_origin_xyz: tuple[float | str, float | str, float | str] = ("{COM_X}", 0.0, "{COM_Z}"),
    inertial_tensor: tuple[float | str, float | str, float | str, float | str, float | str, float | str] = (
        "{IXX}",
        0.0,
        0.0,
        "{IYY}",
        0.0,
        "{IZZ}",
    ),
) -> ET.Element:
    link = ET.SubElement(robot, "link", {"name": name})
    tags: list[str] = []
    if include_visual:
        tags.append("visual")
    if include_collision:
        tags.append("collision")
    for tag in tags:
        attrs = {"name": geometry_name} if geometry_name else {}
        element = ET.SubElement(link, tag, attrs)
        _origin(element, (0.0, 0.0, 0.0))
        geometry = ET.SubElement(element, "geometry")
        ET.SubElement(geometry, "box", {"size": " ".join(_fmt(value) for value in size_m)})
        if tag == "visual":
            ET.SubElement(element, "material", {"name": material_name})
    inertial = ET.SubElement(link, "inertial")
    ET.SubElement(inertial, "mass", {"value": _fmt(inertial_mass)})
    _origin(inertial, inertial_origin_xyz)
    ixx, ixy, ixz, iyy, iyz, izz = inertial_tensor
    _inertia(inertial, ixx=ixx, ixy=ixy, ixz=ixz, iyy=iyy, iyz=iyz, izz=izz)
    return link


def _add_chassis_box_metadata(link: ET.Element, size_m: tuple[float, float, float]) -> None:
    ET.SubElement(link, "flow_cad_chassis_box", {"size": " ".join(_fmt(value) for value in size_m)})


def _add_box_geometry(
    link: ET.Element,
    *,
    tag: str,
    name: str,
    size_m: tuple[float, float, float],
    origin_xyz_m: tuple[float, float, float],
    material_name: str | None = None,
) -> None:
    element = ET.SubElement(link, tag, {"name": name})
    _origin(element, origin_xyz_m)
    geometry = ET.SubElement(element, "geometry")
    ET.SubElement(geometry, "box", {"size": " ".join(_fmt(value) for value in size_m)})
    if tag == "visual" and material_name:
        ET.SubElement(element, "material", {"name": material_name})


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


def _xml_safe_name(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in value.strip())
    return safe or "unnamed"


def _flow_point_to_urdf_root_m(point_mm: tuple[float, float, float], *, wheel_center_z_mm: float) -> tuple[float, float, float]:
    return (
        point_mm[1] / 1000.0,
        point_mm[0] / 1000.0,
        (point_mm[2] - wheel_center_z_mm) / 1000.0,
    )


def _offset_xyz(
    point_m: tuple[float, float, float],
    origin_m: tuple[float, float, float],
) -> tuple[float, float, float]:
    return tuple(point_m[index] - origin_m[index] for index in range(3))


def _contribution_root_com_m(
    contribution: MassContribution,
    *,
    wheel_center_z_mm: float,
) -> tuple[float, float, float]:
    return _flow_point_to_urdf_root_m(
        contribution.assembly_center_of_mass_mm,
        wheel_center_z_mm=wheel_center_z_mm,
    )


def _build_chassis_occurrence_boxes(
    project: FlowCadProject,
    params: Any,
    *,
    profile: str,
    assembly_id: str | None,
    wheel_center_z_mm: float,
    chassis_joint_xyz_m: tuple[float, float, float],
) -> tuple[tuple[UrdfBoxPrimitive, ...], tuple[str, ...]]:
    from build123d import Location

    definitions = {
        str(definition.id): definition
        for definition in project.iter_part_definitions_for_profile(profile, include_references=False)
    }
    placements = list(
        project.get_assembly_placements(
            params,
            include_references=False,
            assembly_id=assembly_id,
        )
    )
    boxes: list[UrdfBoxPrimitive] = []
    failures: list[str] = []
    for placement in placements:
        part_id = str(placement["part_key"])
        occurrence_name = str(placement["name"])
        definition = definitions.get(part_id)
        if definition is None:
            failures.append(f"{occurrence_name}:{part_id}:definition_missing")
            continue
        try:
            location = _float_tuple(placement.get("location"), 3) or (0.0, 0.0, 0.0)
            rotation = _float_tuple(placement.get("rotation"), 3) or (0.0, 0.0, 0.0)
            placed_shape = definition.factory(params).moved(Location(location, rotation))
            bounds = _bounds_from_shape(placed_shape)
        except Exception as exc:
            failures.append(f"{occurrence_name}:{part_id}:{exc.__class__.__name__}")
            continue

        flow_size = bounds["size"]
        if any(value <= 0.0 or not math.isfinite(value) for value in flow_size):
            failures.append(f"{occurrence_name}:{part_id}:invalid_bounds")
            continue
        size_m = (flow_size[1] / 1000.0, flow_size[0] / 1000.0, flow_size[2] / 1000.0)
        root_center_m = _flow_point_to_urdf_root_m(bounds["center"], wheel_center_z_mm=wheel_center_z_mm)
        origin_xyz_m = _offset_xyz(root_center_m, chassis_joint_xyz_m)
        boxes.append(
            UrdfBoxPrimitive(
                name=f"occ_{_xml_safe_name(occurrence_name)}",
                occurrence_name=occurrence_name,
                part_id=part_id,
                size_m=size_m,
                origin_xyz_m=origin_xyz_m,
                flow_center_mm=bounds["center"],
                flow_size_mm=flow_size,
                role=str(getattr(definition, "role", "")),
                include_collision=_include_chassis_collision_occurrence(occurrence_name),
            )
        )
    return tuple(boxes), tuple(failures)


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


def _collapsed_body_mass_model(
    *,
    mass_properties: AssemblyMassProperties,
    wheel_contributions: Iterable[MassContribution],
    wheel_center_z_mm: float,
    chassis_joint_xyz_m: tuple[float, float, float],
    fixed_base_mass_kg: float,
) -> dict[str, Any]:
    wheel_items = list(wheel_contributions)
    wheel_keys = {(item.occurrence_name, item.part_id) for item in wheel_items}
    body_items = [
        item
        for item in mass_properties.contributions
        if (item.occurrence_name, item.part_id) not in wheel_keys
    ]
    wheel_total_mass_kg = sum(item.mass_kg for item in wheel_items)
    known_body_mass_kg = sum(item.mass_kg for item in body_items)
    collapsed_body_mass_kg = max(mass_properties.total_mass_kg - wheel_total_mass_kg - fixed_base_mass_kg, 0.001)

    whole_assembly_com_root_m: tuple[float, float, float] | None = None
    collapsed_body_com_root_m = chassis_joint_xyz_m
    if mass_properties.center_of_mass_mm is not None and collapsed_body_mass_kg > 0.0:
        whole_assembly_com_root_m = _flow_point_to_urdf_root_m(
            mass_properties.center_of_mass_mm,
            wheel_center_z_mm=wheel_center_z_mm,
        )
        weighted = [
            mass_properties.total_mass_kg * whole_assembly_com_root_m[index]
            for index in range(3)
        ]
        for wheel in wheel_items:
            wheel_root_m = _contribution_root_com_m(wheel, wheel_center_z_mm=wheel_center_z_mm)
            for index in range(3):
                weighted[index] -= wheel.mass_kg * wheel_root_m[index]
        collapsed_body_com_root_m = tuple(weighted[index] / collapsed_body_mass_kg for index in range(3))

    collapsed_body_com_chassis_link_m = _offset_xyz(collapsed_body_com_root_m, chassis_joint_xyz_m)
    return {
        "whole_assembly_mass_kg": mass_properties.total_mass_kg,
        "whole_assembly_com_root_m": list(whole_assembly_com_root_m) if whole_assembly_com_root_m is not None else None,
        "wheel_link_mass_total_kg": wheel_total_mass_kg,
        "fixed_base_mass_kg": fixed_base_mass_kg,
        "known_body_mass_kg_before_fixed_base_subtraction": known_body_mass_kg,
        "known_body_mass_occurrence_count": len(body_items),
        "known_body_mass_occurrences": [
            {
                "occurrence_name": item.occurrence_name,
                "part_id": item.part_id,
                "mass_kg": item.mass_kg,
                "mass_source": item.mass_source,
                "metadata_status": item.metadata_status,
                "metadata_notes": item.metadata_notes,
            }
            for item in body_items
        ],
        "recommended_collapsed_body_mass_kg": collapsed_body_mass_kg,
        "recommended_collapsed_body_com_root_m": list(collapsed_body_com_root_m),
        "recommended_collapsed_body_com_chassis_link_m": {
            "x": collapsed_body_com_chassis_link_m[0],
            "y": collapsed_body_com_chassis_link_m[1],
            "z": collapsed_body_com_chassis_link_m[2],
        },
    }


def _target_uses_composite_chassis_inertia(target: UrdfExportTarget) -> bool:
    metadata = dict(target.metadata)
    return str(metadata.get("chassis_inertia_model", "")).strip().lower() in {
        "component_composite",
        "component_composite_numeric",
        "composite",
    }


def _target_metadata_mapping(target: UrdfExportTarget, key: str) -> dict[str, str]:
    raw = dict(target.metadata).get(key, {})
    if not isinstance(raw, Mapping):
        return {}
    result: dict[str, str] = {}
    for item_key, item_value in raw.items():
        if isinstance(item_value, Mapping):
            reason = item_value.get("reason", "")
        else:
            reason = item_value
        result[str(item_key)] = str(reason or "")
    return result


def _is_wheel_or_wheel_reference(occurrence_name: str, part_id: str) -> bool:
    lowered = f"{occurrence_name}:{part_id}".lower()
    return "reference_wheel" in lowered or "wheel_only_reference" in lowered or part_id in {"left_wheel", "right_wheel"}


def _tensor_to_matrix(tensor: tuple[float, ...]) -> list[list[float]]:
    ixx, ixy, ixz, iyy, iyz, izz = tensor
    return [
        [ixx, ixy, ixz],
        [ixy, iyy, iyz],
        [ixz, iyz, izz],
    ]


def _matrix_to_tensor(matrix: list[list[float]]) -> tuple[float, float, float, float, float, float]:
    return (
        matrix[0][0],
        matrix[0][1],
        matrix[0][2],
        matrix[1][1],
        matrix[1][2],
        matrix[2][2],
    )


def _zero_matrix() -> list[list[float]]:
    return [[0.0, 0.0, 0.0] for _ in range(3)]


def _matrix_add(a: list[list[float]], b: list[list[float]], *, scale_b: float = 1.0) -> list[list[float]]:
    return [[a[row][col] + scale_b * b[row][col] for col in range(3)] for row in range(3)]


def _matrix_multiply(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [
        [
            sum(a[row][inner] * b[inner][col] for inner in range(3))
            for col in range(3)
        ]
        for row in range(3)
    ]


def _matrix_transpose(matrix: list[list[float]]) -> list[list[float]]:
    return [[matrix[col][row] for col in range(3)] for row in range(3)]


def _rotation_matrix_xyz_degrees(rotation_deg: tuple[float, float, float]) -> list[list[float]]:
    rx, ry, rz = (math.radians(value) for value in rotation_deg)
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    rx_m = [
        [1.0, 0.0, 0.0],
        [0.0, cx, -sx],
        [0.0, sx, cx],
    ]
    ry_m = [
        [cy, 0.0, sy],
        [0.0, 1.0, 0.0],
        [-sy, 0.0, cy],
    ]
    rz_m = [
        [cz, -sz, 0.0],
        [sz, cz, 0.0],
        [0.0, 0.0, 1.0],
    ]
    return _matrix_multiply(rz_m, _matrix_multiply(ry_m, rx_m))


def _flow_to_urdf_matrix() -> list[list[float]]:
    return [
        [0.0, 1.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
    ]


def _rotate_flow_local_tensor_to_urdf(
    tensor: tuple[float, ...],
    rotation_deg: tuple[float, float, float],
) -> tuple[float, float, float, float, float, float]:
    local = _tensor_to_matrix(tuple(float(value) for value in tensor))
    flow_rotation = _rotation_matrix_xyz_degrees(rotation_deg)
    urdf_rotation = _matrix_multiply(_flow_to_urdf_matrix(), flow_rotation)
    rotated = _matrix_multiply(_matrix_multiply(urdf_rotation, local), _matrix_transpose(urdf_rotation))
    return _matrix_to_tensor(rotated)


def _box_inertia_tensor_kg_m2(
    *,
    mass_kg: float,
    size_m: tuple[float, float, float],
) -> tuple[float, float, float, float, float, float]:
    x, y, z = size_m
    return (
        mass_kg / 12.0 * (y * y + z * z),
        0.0,
        0.0,
        mass_kg / 12.0 * (x * x + z * z),
        0.0,
        mass_kg / 12.0 * (x * x + y * y),
    )


def _parallel_axis_tensor_kg_m2(
    *,
    mass_kg: float,
    offset_m: tuple[float, float, float],
) -> tuple[float, float, float, float, float, float]:
    dx, dy, dz = offset_m
    d2 = dx * dx + dy * dy + dz * dz
    return (
        mass_kg * (d2 - dx * dx),
        -mass_kg * dx * dy,
        -mass_kg * dx * dz,
        mass_kg * (d2 - dy * dy),
        -mass_kg * dy * dz,
        mass_kg * (d2 - dz * dz),
    )


def _tensor_payload(tensor: tuple[float, ...]) -> dict[str, float]:
    ixx, ixy, ixz, iyy, iyz, izz = tensor
    return {
        "ixx": ixx,
        "ixy": ixy,
        "ixz": ixz,
        "iyy": iyy,
        "iyz": iyz,
        "izz": izz,
    }


def _tensor_list_from_payload(payload: Mapping[str, Any]) -> tuple[float, float, float, float, float, float]:
    return (
        float(payload["ixx"]),
        float(payload["ixy"]),
        float(payload["ixz"]),
        float(payload["iyy"]),
        float(payload["iyz"]),
        float(payload["izz"]),
    )


def _panel_area_and_thickness_mm(
    box: UrdfBoxPrimitive,
    *,
    nominal_thickness_mm: float | None = None,
) -> tuple[float, float]:
    sizes = sorted(float(value) for value in box.flow_size_mm)
    thickness = float(nominal_thickness_mm) if nominal_thickness_mm is not None else sizes[0]
    return sizes[1] * sizes[2], thickness


def _is_3mm_panel_candidate(
    definition: Any,
    box: UrdfBoxPrimitive,
    *,
    max_thickness_mm: float,
    nominal_thickness_mm: float | None = None,
) -> bool:
    part_id = str(getattr(definition, "id", box.part_id)).lower()
    filename = str(getattr(definition, "filename", "")).lower()
    if "panel" not in part_id and "panel" not in filename:
        return False
    if nominal_thickness_mm is not None:
        return nominal_thickness_mm <= max_thickness_mm
    _area, thickness = _panel_area_and_thickness_mm(box)
    return thickness <= max_thickness_mm


def _component_quality(mass_source: str, metadata_status: str) -> str:
    lowered = f"{mass_source} {metadata_status}".lower()
    if "estimated" in lowered:
        return "estimated"
    if "placeholder" in lowered or "todo" in lowered:
        return "placeholder"
    if "measured" in lowered:
        return "measured"
    return metadata_status or "unknown"


def _parse_missing_mass_item(item: str) -> tuple[str, str]:
    occurrence_name, _sep, part_id = item.partition(":")
    return occurrence_name, part_id


def _build_panel_estimator_sources(
    *,
    definitions: Mapping[str, Any],
    boxes_by_key: Mapping[tuple[str, str], UrdfBoxPrimitive],
    mass_properties: AssemblyMassProperties,
    max_thickness_mm: float,
    nominal_thickness_mm: float | None = None,
) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    by_family_material: dict[tuple[str, str], list[dict[str, Any]]] = {}
    by_material: dict[str, list[dict[str, Any]]] = {}
    for contribution in mass_properties.contributions:
        box = boxes_by_key.get((contribution.occurrence_name, contribution.part_id))
        definition = definitions.get(contribution.part_id)
        if box is None or definition is None:
            continue
        if "measured" not in contribution.mass_source.lower():
            continue
        if not _is_3mm_panel_candidate(
            definition,
            box,
            max_thickness_mm=max_thickness_mm,
            nominal_thickness_mm=nominal_thickness_mm,
        ):
            continue
        area_mm2, thickness_mm = _panel_area_and_thickness_mm(box, nominal_thickness_mm=nominal_thickness_mm)
        if area_mm2 <= 0.0 or thickness_mm <= 0.0:
            continue
        material = str(getattr(definition, "material", "") or "")
        family = str(getattr(definition, "module_id", "") or "")
        source = {
            "occurrence_name": contribution.occurrence_name,
            "part_id": contribution.part_id,
            "material": material,
            "family": family,
            "mass_kg": contribution.mass_kg,
            "area_mm2": area_mm2,
            "thickness_mm": thickness_mm,
            "mass_per_area_kg_per_mm2": contribution.mass_kg / area_mm2,
        }
        by_family_material.setdefault((family, material), []).append(source)
        by_material.setdefault(material, []).append(source)
    return by_family_material, by_material


def _estimate_3mm_panel_mass(
    *,
    occurrence_name: str,
    part_id: str,
    definition: Any,
    box: UrdfBoxPrimitive,
    by_family_material: Mapping[tuple[str, str], list[dict[str, Any]]],
    by_material: Mapping[str, list[dict[str, Any]]],
    nominal_thickness_mm: float | None = None,
) -> tuple[float, dict[str, Any]] | None:
    material = str(getattr(definition, "material", "") or "")
    family = str(getattr(definition, "module_id", "") or "")
    sources = list(by_family_material.get((family, material), ()))
    estimator_name = "same_family_measured_panel_area"
    if not sources:
        sources = list(by_material.get(material, ()))
        estimator_name = "project_3mm_panel_mass_per_area_same_material"
    if not sources:
        return None

    area_mm2, thickness_mm = _panel_area_and_thickness_mm(box, nominal_thickness_mm=nominal_thickness_mm)
    bounds_area_mm2, bounds_min_thickness_mm = _panel_area_and_thickness_mm(box)
    estimates = [
        float(source["mass_per_area_kg_per_mm2"]) * area_mm2 * (thickness_mm / float(source["thickness_mm"]))
        for source in sources
    ]
    estimated_mass_kg = sum(estimates) / len(estimates)
    average_area = sum(float(source["area_mm2"]) for source in sources) / len(sources)
    average_thickness = sum(float(source["thickness_mm"]) for source in sources) / len(sources)
    return estimated_mass_kg, {
        "occurrence_name": occurrence_name,
        "part_id": part_id,
        "mass_source": "estimated_from_measured_panel_area",
        "metadata_status": "estimated",
        "estimator_name": estimator_name,
        "material": material,
        "source_panel_ids": [str(source["part_id"]) for source in sources],
        "source_occurrences": [str(source["occurrence_name"]) for source in sources],
        "source_mass_total_kg": sum(float(source["mass_kg"]) for source in sources),
        "source_area_total_mm2": sum(float(source["area_mm2"]) for source in sources),
        "missing_panel_area_mm2": area_mm2,
        "missing_panel_thickness_mm": thickness_mm,
        "missing_panel_bounds_area_mm2": bounds_area_mm2,
        "missing_panel_bounds_min_thickness_mm": bounds_min_thickness_mm,
        "source_average_thickness_mm": average_thickness,
        "area_ratio": area_mm2 / average_area if average_area else math.inf,
        "thickness_ratio": thickness_mm / average_thickness if average_thickness else math.inf,
        "estimated_mass_kg": estimated_mass_kg,
    }


def _component_payload(
    *,
    occurrence_name: str,
    part_id: str,
    mass_kg: float,
    mass_source: str,
    metadata_status: str,
    metadata_notes: str,
    local_com_source: str,
    assembly_com_root_m: tuple[float, float, float],
    assembly_com_chassis_link_m: tuple[float, float, float],
    box: UrdfBoxPrimitive,
    local_inertia_tensor: tuple[float, ...],
    local_inertia_source: str,
    bounds_source: str,
    component_quality: str,
) -> dict[str, Any]:
    return {
        "occurrence_name": occurrence_name,
        "part_id": part_id,
        "mass_kg": mass_kg,
        "mass_source": mass_source,
        "metadata_status": metadata_status,
        "metadata_notes": metadata_notes,
        "metadata_quality": component_quality,
        "local_com_source": local_com_source,
        "assembly_com_root_m": list(assembly_com_root_m),
        "assembly_com_chassis_link_m": list(assembly_com_chassis_link_m),
        "bounds_source": bounds_source,
        "bounds_flow_center_mm": list(box.flow_center_mm),
        "bounds_flow_size_mm": list(box.flow_size_mm),
        "bounds_urdf_size_m": list(box.size_m),
        "local_inertia_source": local_inertia_source,
        "local_inertia_tensor_kg_m2": _tensor_payload(local_inertia_tensor),
    }


def _build_composite_chassis_inertia_model(
    *,
    project: FlowCadProject,
    params: Any,
    target: UrdfExportTarget,
    mass_properties: AssemblyMassProperties,
    chassis_occurrence_boxes: tuple[UrdfBoxPrimitive, ...],
    wheel_contributions: Iterable[MassContribution],
    wheel_center_z_mm: float,
    chassis_joint_xyz_m: tuple[float, float, float],
    chassis_size_m: tuple[float, float, float],
    fixed_base_mass_kg: float,
) -> dict[str, Any]:
    metadata = dict(target.metadata)
    heavy_threshold_kg = float(metadata.get("heavy_missing_mass_threshold_kg", 0.100))
    panel_max_thickness_mm = float(metadata.get("panel_estimator_max_thickness_mm", 3.5))
    panel_nominal_thickness_raw = metadata.get("panel_estimator_nominal_thickness_mm")
    panel_nominal_thickness_mm = (
        float(panel_nominal_thickness_raw)
        if panel_nominal_thickness_raw is not None
        else None
    )
    covered_missing_part_ids = _target_metadata_mapping(target, "covered_missing_mass_part_ids")
    excluded_missing_part_ids = _target_metadata_mapping(target, "excluded_missing_mass_part_ids")
    assembly_id = target.assembly_id or project.active_assembly_id
    definitions = {
        str(definition.id): definition
        for definition in project.iter_part_definitions_for_profile(target.profile, include_references=target.include_references)
    }
    placements = {
        (str(placement["name"]), str(placement["part_key"])): placement
        for placement in project.get_assembly_placements(
            params,
            include_references=target.include_references,
            assembly_id=assembly_id,
        )
    }
    boxes_by_key = {(box.occurrence_name, box.part_id): box for box in chassis_occurrence_boxes}
    wheel_keys = {(item.occurrence_name, item.part_id) for item in wheel_contributions}
    panel_sources_by_family, panel_sources_by_material = _build_panel_estimator_sources(
        definitions=definitions,
        boxes_by_key=boxes_by_key,
        mass_properties=mass_properties,
        max_thickness_mm=panel_max_thickness_mm,
        nominal_thickness_mm=panel_nominal_thickness_mm,
    )

    raw_components: list[dict[str, Any]] = []
    missing_failures: list[str] = []
    estimated_panel_ledger: list[dict[str, Any]] = []
    covered_missing_mass_ledger: list[dict[str, Any]] = []
    skipped_missing_mass_ledger: list[dict[str, Any]] = []
    excluded_wheel_reference_ledger: list[dict[str, Any]] = []

    for contribution in mass_properties.contributions:
        if (contribution.occurrence_name, contribution.part_id) in wheel_keys:
            excluded_wheel_reference_ledger.append(
                {
                    "occurrence_name": contribution.occurrence_name,
                    "part_id": contribution.part_id,
                    "mass_kg": contribution.mass_kg,
                    "reason": "wheel_link_mass_is_modeled_on_separate_wheel_link",
                }
            )
            continue
        if _is_wheel_or_wheel_reference(contribution.occurrence_name, contribution.part_id):
            excluded_wheel_reference_ledger.append(
                {
                    "occurrence_name": contribution.occurrence_name,
                    "part_id": contribution.part_id,
                    "mass_kg": contribution.mass_kg,
                    "reason": "wheel_reference_geometry_excluded_from_collapsed_chassis",
                }
            )
            continue
        box = boxes_by_key.get((contribution.occurrence_name, contribution.part_id))
        if box is None:
            if contribution.mass_kg >= heavy_threshold_kg:
                missing_failures.append(
                    f"{contribution.occurrence_name}:{contribution.part_id}:missing_bounds_for_{contribution.mass_kg:.6g}kg_component"
                )
            else:
                skipped_missing_mass_ledger.append(
                    {
                        "occurrence_name": contribution.occurrence_name,
                        "part_id": contribution.part_id,
                        "mass_kg": contribution.mass_kg,
                        "reason": "mass_present_but_no_chassis_bounds_for_small_or_non_body_occurrence",
                    }
                )
            continue
        placement = placements.get((contribution.occurrence_name, contribution.part_id), {})
        rotation = _float_tuple(placement.get("rotation"), 3) or (0.0, 0.0, 0.0)
        if contribution.inertia_kg_m2 is not None:
            local_tensor = _rotate_flow_local_tensor_to_urdf(contribution.inertia_kg_m2, rotation)
            inertia_source = "explicit_part_metadata_rotated_to_urdf"
        else:
            local_tensor = _box_inertia_tensor_kg_m2(mass_kg=contribution.mass_kg, size_m=box.size_m)
            inertia_source = "placed_axis_aligned_box_estimate"
        root_com = _contribution_root_com_m(contribution, wheel_center_z_mm=wheel_center_z_mm)
        chassis_com = _offset_xyz(root_com, chassis_joint_xyz_m)
        raw_components.append(
            _component_payload(
                occurrence_name=contribution.occurrence_name,
                part_id=contribution.part_id,
                mass_kg=contribution.mass_kg,
                mass_source=contribution.mass_source,
                metadata_status=contribution.metadata_status,
                metadata_notes=contribution.metadata_notes,
                local_com_source=contribution.center_source,
                assembly_com_root_m=root_com,
                assembly_com_chassis_link_m=chassis_com,
                box=box,
                local_inertia_tensor=local_tensor,
                local_inertia_source=inertia_source,
                bounds_source="placed_occurrence_axis_aligned_bounds",
                component_quality=_component_quality(contribution.mass_source, contribution.metadata_status),
            )
        )

    for item in mass_properties.missing_mass_occurrences:
        occurrence_name, part_id = _parse_missing_mass_item(item)
        if not occurrence_name or not part_id:
            missing_failures.append(f"{item}:malformed_missing_mass_entry")
            continue
        if _is_wheel_or_wheel_reference(occurrence_name, part_id):
            excluded_wheel_reference_ledger.append(
                {
                    "occurrence_name": occurrence_name,
                    "part_id": part_id,
                    "mass_kg": None,
                    "reason": "wheel_or_wheel_reference_geometry_excluded_from_collapsed_chassis",
                }
            )
            continue
        if part_id in covered_missing_part_ids:
            covered_missing_mass_ledger.append(
                {
                    "occurrence_name": occurrence_name,
                    "part_id": part_id,
                    "reason": covered_missing_part_ids[part_id],
                }
            )
            continue
        if part_id in excluded_missing_part_ids:
            skipped_missing_mass_ledger.append(
                {
                    "occurrence_name": occurrence_name,
                    "part_id": part_id,
                    "mass_kg": None,
                    "reason": excluded_missing_part_ids[part_id],
                }
            )
            continue
        box = boxes_by_key.get((occurrence_name, part_id))
        definition = definitions.get(part_id)
        if box is not None and definition is not None and _is_3mm_panel_candidate(
            definition,
            box,
            max_thickness_mm=panel_max_thickness_mm,
            nominal_thickness_mm=panel_nominal_thickness_mm,
        ):
            estimated = _estimate_3mm_panel_mass(
                occurrence_name=occurrence_name,
                part_id=part_id,
                definition=definition,
                box=box,
                by_family_material=panel_sources_by_family,
                by_material=panel_sources_by_material,
                nominal_thickness_mm=panel_nominal_thickness_mm,
            )
            if estimated is not None:
                mass_kg, ledger = estimated
                estimated_panel_ledger.append(ledger)
                root_com = _flow_point_to_urdf_root_m(box.flow_center_mm, wheel_center_z_mm=wheel_center_z_mm)
                chassis_com = _offset_xyz(root_com, chassis_joint_xyz_m)
                local_tensor = _box_inertia_tensor_kg_m2(mass_kg=mass_kg, size_m=box.size_m)
                raw_components.append(
                    _component_payload(
                        occurrence_name=occurrence_name,
                        part_id=part_id,
                        mass_kg=mass_kg,
                        mass_source="estimated_from_measured_panel_area",
                        metadata_status="estimated",
                        metadata_notes=f"Estimated by {ledger['estimator_name']} from measured 3 mm panel siblings.",
                        local_com_source="geometry_estimate",
                        assembly_com_root_m=root_com,
                        assembly_com_chassis_link_m=chassis_com,
                        box=box,
                        local_inertia_tensor=local_tensor,
                        local_inertia_source="placed_axis_aligned_box_estimate",
                        bounds_source="placed_occurrence_axis_aligned_bounds",
                        component_quality="estimated",
                    )
                )
                continue
        if box is None:
            missing_failures.append(f"{occurrence_name}:{part_id}:missing_mass_and_missing_bounds")
        else:
            missing_failures.append(f"{occurrence_name}:{part_id}:missing_mass_uncovered_by_target_metadata")

    if missing_failures:
        raise UrdfExportError(
            "B2 composite inertia cannot be generated with uncovered missing mass/bounds metadata: "
            + "; ".join(sorted(missing_failures))
        )

    body_mass_before_base = sum(float(component["mass_kg"]) for component in raw_components)
    collapsed_body_mass = body_mass_before_base - fixed_base_mass_kg
    if collapsed_body_mass <= 0.0:
        raise UrdfExportError(
            f"Composite chassis mass must stay positive after fixed base subtraction; got {collapsed_body_mass:.6g} kg."
        )
    weighted_root = [0.0, 0.0, 0.0]
    for component in raw_components:
        mass_kg = float(component["mass_kg"])
        root_com = _float_tuple(component["assembly_com_root_m"], 3) or (0.0, 0.0, 0.0)
        for index in range(3):
            weighted_root[index] += mass_kg * root_com[index]
    collapsed_body_com_root = tuple(weighted_root[index] / collapsed_body_mass for index in range(3))
    collapsed_body_com_chassis = _offset_xyz(collapsed_body_com_root, chassis_joint_xyz_m)

    total_matrix = _zero_matrix()
    components: list[dict[str, Any]] = []
    for component in raw_components:
        mass_kg = float(component["mass_kg"])
        component_com_chassis = _float_tuple(component["assembly_com_chassis_link_m"], 3) or (0.0, 0.0, 0.0)
        offset = tuple(component_com_chassis[index] - collapsed_body_com_chassis[index] for index in range(3))
        local_tensor = _tensor_list_from_payload(component["local_inertia_tensor_kg_m2"])
        parallel_tensor = _parallel_axis_tensor_kg_m2(mass_kg=mass_kg, offset_m=offset)
        total_tensor = _matrix_to_tensor(
            _matrix_add(_tensor_to_matrix(local_tensor), _tensor_to_matrix(parallel_tensor))
        )
        total_matrix = _matrix_add(total_matrix, _tensor_to_matrix(total_tensor))
        enriched = {
            **component,
            "parallel_axis_offset_from_collapsed_com_m": list(offset),
            "parallel_axis_tensor_kg_m2": _tensor_payload(parallel_tensor),
            "total_tensor_about_collapsed_com_kg_m2": _tensor_payload(total_tensor),
        }
        components.append(enriched)

    base_root_chassis = _offset_xyz((0.0, 0.0, 0.0), chassis_joint_xyz_m)
    base_offset = tuple(base_root_chassis[index] - collapsed_body_com_chassis[index] for index in range(3))
    fixed_base_subtraction_tensor = _parallel_axis_tensor_kg_m2(mass_kg=fixed_base_mass_kg, offset_m=base_offset)
    total_matrix = _matrix_add(total_matrix, _tensor_to_matrix(fixed_base_subtraction_tensor), scale_b=-1.0)
    collapsed_tensor = _matrix_to_tensor(total_matrix)
    if collapsed_tensor[0] <= 0.0 or collapsed_tensor[3] <= 0.0 or collapsed_tensor[5] <= 0.0:
        raise UrdfExportError(
            "Composite chassis inertia has a non-positive diagonal after fixed-base subtraction: "
            f"{_tensor_payload(collapsed_tensor)}"
        )

    simple_box_tensor = _box_inertia_tensor_kg_m2(mass_kg=collapsed_body_mass, size_m=chassis_size_m)
    measured_mass_total = sum(
        float(component["mass_kg"])
        for component in raw_components
        if component["metadata_quality"] == "measured"
    )
    estimated_mass_total = sum(
        float(component["mass_kg"])
        for component in raw_components
        if component["metadata_quality"] == "estimated"
    )
    estimated_panel_mass_total = sum(float(item["estimated_mass_kg"]) for item in estimated_panel_ledger)
    return {
        "mode": "component_composite_numeric",
        "target_name": target.name,
        "assembly_id": assembly_id,
        "profile": target.profile,
        "heavy_missing_mass_threshold_kg": heavy_threshold_kg,
        "body_component_mass_before_fixed_base_subtraction_kg": body_mass_before_base,
        "fixed_base_mass_kg": fixed_base_mass_kg,
        "collapsed_body_mass_kg": collapsed_body_mass,
        "collapsed_body_com_root_m": list(collapsed_body_com_root),
        "collapsed_body_com_chassis_link_m": {
            "x": collapsed_body_com_chassis[0],
            "y": collapsed_body_com_chassis[1],
            "z": collapsed_body_com_chassis[2],
        },
        "collapsed_body_inertia_tensor_about_com_kg_m2": _tensor_payload(collapsed_tensor),
        "component_count": len(components),
        "components": sorted(
            components,
            key=lambda item: float(item["total_tensor_about_collapsed_com_kg_m2"]["iyy"]),
            reverse=True,
        ),
        "measured_mass_total_kg": measured_mass_total,
        "estimated_mass_total_kg": estimated_mass_total,
        "estimated_3mm_panel_mass_total_kg": estimated_panel_mass_total,
        "missing_skipped_mass_total_kg": 0.0,
        "estimated_3mm_panel_ledger": estimated_panel_ledger,
        "excluded_wheel_reference_ledger": excluded_wheel_reference_ledger,
        "covered_missing_mass_ledger": covered_missing_mass_ledger,
        "skipped_missing_mass_ledger": skipped_missing_mass_ledger,
        "fixed_base_mass_adjustment": {
            "reason": "base_link carries this dummy axle mass, so the collapsed chassis tensor subtracts a point-mass equivalent at base_link origin.",
            "mass_kg": fixed_base_mass_kg,
            "offset_from_collapsed_com_m": list(base_offset),
            "subtracted_parallel_axis_tensor_kg_m2": _tensor_payload(fixed_base_subtraction_tensor),
        },
        "simple_box_comparison": {
            "flow_cad_chassis_box_size_m": list(chassis_size_m),
            "simple_box_tensor_kg_m2": _tensor_payload(simple_box_tensor),
            "ratio_composite_iyy_to_simple_box_iyy": collapsed_tensor[3] / simple_box_tensor[3] if simple_box_tensor[3] else math.inf,
            "dojo_multiplier_comparisons": {
                f"x{multiplier:g}": {
                    "old_simple_box_iyy_times_multiplier": simple_box_tensor[3] * multiplier,
                    "ratio_composite_iyy_to_old_multiplied_iyy": (
                        collapsed_tensor[3] / (simple_box_tensor[3] * multiplier)
                        if simple_box_tensor[3] * multiplier
                        else math.inf
                    ),
                }
                for multiplier in (3.0, 5.0, 6.0, 9.0)
            },
        },
        "dojo_consumer_gate": {
            "urdf_inertial_mode": "numeric_inertial_fields_no_template_placeholders",
            "dojo_template_formatting": (
                "Current Dojo render paths call str.format(...); a URDF with no CHASSIS_MASS/COM/IXX placeholders "
                "is returned unchanged by that formatting step."
            ),
            "pybullet_inertia_flag_note": (
                "PyBullet load behavior still needs a consumer smoke check because p.loadURDF without "
                "URDF_USE_INERTIA_FROM_FILE may adjust inertias from collision geometry."
            ),
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
    mass_model = _collapsed_body_mass_model(
        mass_properties=mass_properties,
        wheel_contributions=wheel_contributions,
        wheel_center_z_mm=wheel_center_z_mm,
        chassis_joint_xyz_m=chassis_joint_xyz,
        fixed_base_mass_kg=axle_mass_kg,
    )
    chassis_mass_kg = float(mass_model["recommended_collapsed_body_mass_kg"])
    collapsed_com = mass_model["recommended_collapsed_body_com_chassis_link_m"]
    nominal_com_x_m = float(collapsed_com["x"])
    nominal_com_z_m = float(collapsed_com["z"])
    wheel_total_mass = float(mass_model["wheel_link_mass_total_kg"])
    chassis_occurrence_boxes, chassis_occurrence_box_failures = _build_chassis_occurrence_boxes(
        project,
        params,
        profile=target.profile,
        assembly_id=assembly_id,
        wheel_center_z_mm=wheel_center_z_mm,
        chassis_joint_xyz_m=chassis_joint_xyz,
    )
    composite_inertia_model: dict[str, Any] | None = None
    chassis_inertial_mass: float | str = "{CHASSIS_MASS}"
    chassis_inertial_origin_xyz: tuple[float | str, float | str, float | str] = ("{COM_X}", 0.0, "{COM_Z}")
    chassis_inertial_tensor: tuple[float | str, float | str, float | str, float | str, float | str, float | str] = (
        "{IXX}",
        0.0,
        0.0,
        "{IYY}",
        0.0,
        "{IZZ}",
    )
    if _target_uses_composite_chassis_inertia(target):
        composite_inertia_model = _build_composite_chassis_inertia_model(
            project=project,
            params=params,
            target=target,
            mass_properties=mass_properties,
            chassis_occurrence_boxes=chassis_occurrence_boxes,
            wheel_contributions=wheel_contributions,
            wheel_center_z_mm=wheel_center_z_mm,
            chassis_joint_xyz_m=chassis_joint_xyz,
            chassis_size_m=chassis_size_m,
            fixed_base_mass_kg=axle_mass_kg,
        )
        chassis_mass_kg = float(composite_inertia_model["collapsed_body_mass_kg"])
        composite_com = composite_inertia_model["collapsed_body_com_chassis_link_m"]
        nominal_com_x_m = float(composite_com["x"])
        nominal_com_z_m = float(composite_com["z"])
        chassis_inertial_mass = chassis_mass_kg
        chassis_inertial_origin_xyz = (
            nominal_com_x_m,
            float(composite_com["y"]),
            nominal_com_z_m,
        )
        chassis_inertial_tensor = _tensor_list_from_payload(
            composite_inertia_model["collapsed_body_inertia_tensor_about_com_kg_m2"]
        )
        mass_model = {
            **mass_model,
            "recommended_collapsed_body_mass_kg": chassis_mass_kg,
            "recommended_collapsed_body_com_root_m": composite_inertia_model["collapsed_body_com_root_m"],
            "recommended_collapsed_body_com_chassis_link_m": dict(composite_com),
            "composite_inertia_component_count": composite_inertia_model["component_count"],
            "estimated_3mm_panel_mass_total_kg": composite_inertia_model["estimated_3mm_panel_mass_total_kg"],
        }

    robot = ET.Element("robot", {"name": target.robot_name or "B2_v2"})
    _material(robot, "matte_black", "0.02 0.02 0.02 1.0")
    _material(robot, "tire_rubber", "0.12 0.12 0.13 1.0")
    _material(robot, "accent_green", "0.0 1.0 0.15 1.0")
    _material(robot, "compartment_visual", "0.08 0.38 0.75 0.42")

    _add_cylinder_link(
        robot,
        name="base_link",
        radius_m=axle_radius_m,
        length_m=wheel_base_m,
        mass_kg=axle_mass_kg,
        material_name="matte_black",
    )
    _add_fixed_joint(robot, name="chassis_joint", parent="base_link", child="chassis_link", xyz=chassis_joint_xyz)
    chassis_link = _add_box_link(
        robot,
        name="chassis_link",
        size_m=chassis_size_m,
        material_name="compartment_visual",
        include_visual=not chassis_occurrence_boxes,
        include_collision=not chassis_occurrence_boxes,
        inertial_mass=chassis_inertial_mass,
        inertial_origin_xyz=chassis_inertial_origin_xyz,
        inertial_tensor=chassis_inertial_tensor,
    )
    _add_chassis_box_metadata(chassis_link, chassis_size_m)
    for box in chassis_occurrence_boxes:
        _add_box_geometry(
            chassis_link,
            tag="visual",
            name=box.name,
            size_m=box.size_m,
            origin_xyz_m=box.origin_xyz_m,
            material_name="compartment_visual",
        )
        if box.include_collision:
            _add_box_geometry(
                chassis_link,
                tag="collision",
                name=box.name,
                size_m=box.size_m,
                origin_xyz_m=box.origin_xyz_m,
            )

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
        "chassis_collision_geometry": {
            "mode": "assembly_occurrence_axis_aligned_boxes",
            "visual_primitive_count": len(chassis_occurrence_boxes),
            "primitive_count": sum(1 for box in chassis_occurrence_boxes if box.include_collision),
            "occurrences": [box.to_payload() for box in chassis_occurrence_boxes],
            "collision_occurrences": [box.to_payload() for box in chassis_occurrence_boxes if box.include_collision],
            "failures": list(chassis_occurrence_box_failures),
        },
        "recommended_chassis_mass_kg": chassis_mass_kg,
        "nominal_chassis_com_m": {
            "x": nominal_com_x_m,
            "y": float(chassis_inertial_origin_xyz[1]) if not isinstance(chassis_inertial_origin_xyz[1], str) else 0.0,
            "z": nominal_com_z_m,
        },
        "dojo_mass_model": mass_model,
        "chassis_inertia_model": composite_inertia_model
        if composite_inertia_model is not None
        else {
            "mode": "dojo_template_placeholders_simple_box_runtime",
            "placeholder_fields": ["CHASSIS_MASS", "COM_X", "COM_Z", "IXX", "IYY", "IZZ"],
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
