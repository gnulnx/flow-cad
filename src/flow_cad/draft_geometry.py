from __future__ import annotations

import json
import math
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from build123d import Box, Cylinder, Location, export_step

from flow_cad.project import FlowCadProject
from flow_cad.step_io import normalize_step_file


DRAFT_SCHEMA_VERSION = 1
DRAFT_TRANSACTION_SCHEMA_VERSION = 1

DraftFeatureKind = Literal["hole", "counterbore", "slot"]


class DraftGeometryError(RuntimeError):
    """Base error for draft geometry operations."""

    status_code = 400


class DraftNotFoundError(DraftGeometryError):
    status_code = 404


@dataclass(frozen=True)
class FaceSpec:
    name: str
    normal_axis: int
    normal_sign: int
    u_axis: int
    v_axis: int
    u_dimension: str
    v_dimension: str
    depth_dimension: str

    @property
    def axis(self) -> tuple[float, float, float]:
        values = [0.0, 0.0, 0.0]
        values[self.normal_axis] = float(self.normal_sign)
        return (values[0], values[1], values[2])


FACE_SPECS: dict[str, FaceSpec] = {
    "top": FaceSpec("top", 2, 1, 0, 1, "length", "width", "height"),
    "bottom": FaceSpec("bottom", 2, -1, 0, 1, "length", "width", "height"),
    "front": FaceSpec("front", 1, 1, 0, 2, "length", "height", "width"),
    "back": FaceSpec("back", 1, -1, 0, 2, "length", "height", "width"),
    "right": FaceSpec("right", 0, 1, 1, 2, "width", "height", "length"),
    "left": FaceSpec("left", 0, -1, 1, 2, "width", "height", "length"),
}


@dataclass
class DraftFeature:
    id: str
    kind: DraftFeatureKind
    face: str
    x: float
    y: float
    diameter: float | None = None
    through: bool | None = None
    depth: float | None = None
    length: float | None = None
    width: float | None = None
    angle: float = 0.0

    def to_state(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "face": self.face,
            "x": self.x,
            "y": self.y,
        }
        for key in ("diameter", "through", "depth", "length", "width", "angle"):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return payload

    @classmethod
    def from_state(cls, payload: dict[str, Any]) -> DraftFeature:
        return cls(
            id=str(payload["id"]),
            kind=str(payload["kind"]),  # type: ignore[arg-type]
            face=str(payload["face"]),
            x=float(payload["x"]),
            y=float(payload["y"]),
            diameter=float(payload["diameter"]) if payload.get("diameter") is not None else None,
            through=bool(payload["through"]) if payload.get("through") is not None else None,
            depth=float(payload["depth"]) if payload.get("depth") is not None else None,
            length=float(payload["length"]) if payload.get("length") is not None else None,
            width=float(payload["width"]) if payload.get("width") is not None else None,
            angle=float(payload.get("angle", 0.0)),
        )


@dataclass
class DraftPart:
    token: str
    part_id: str
    length: float
    width: float
    height: float
    material: str = "draft"
    role: str = "draft"
    features: list[DraftFeature] = field(default_factory=list)
    preview_step_path: Path | None = None

    def dimensions(self) -> dict[str, float]:
        return {
            "length": float(self.length),
            "width": float(self.width),
            "height": float(self.height),
        }

    def to_state(self, root: Path) -> dict[str, Any]:
        preview_path = str(self.preview_step_path) if self.preview_step_path is not None else None
        try:
            preview_relative = (
                str(self.preview_step_path.relative_to(root))
                if self.preview_step_path is not None
                else None
            )
        except ValueError:
            preview_relative = preview_path
        return {
            "schema_version": DRAFT_SCHEMA_VERSION,
            "token": self.token,
            "part_id": self.part_id,
            "dimensions": self.dimensions(),
            "material": self.material,
            "role": self.role,
            "features": [feature.to_state() for feature in self.features],
            "preview_step_path": preview_path,
            "preview_step_relative_path": preview_relative,
        }

    @classmethod
    def from_state(cls, payload: dict[str, Any]) -> DraftPart:
        dimensions = payload.get("dimensions", {})
        if not isinstance(dimensions, dict):
            raise DraftGeometryError("Draft state is missing dimensions")
        preview = payload.get("preview_step_path")
        return cls(
            token=str(payload["token"]),
            part_id=str(payload["part_id"]),
            length=float(dimensions["length"]),
            width=float(dimensions["width"]),
            height=float(dimensions["height"]),
            material=str(payload.get("material") or "draft"),
            role=str(payload.get("role") or "draft"),
            features=[
                DraftFeature.from_state(feature)
                for feature in payload.get("features", [])
                if isinstance(feature, dict)
            ],
            preview_step_path=Path(preview).resolve() if isinstance(preview, str) and preview else None,
        )


@dataclass
class DraftTransaction:
    token: str
    part_id: str
    status: str = "open"
    draft_token: str | None = None
    operations: list[dict[str, Any]] = field(default_factory=list)
    preview_step_path: Path | None = None
    source_patch_path: Path | None = None
    generated_source_path: Path | None = None
    validator_stub_path: Path | None = None
    acceptance_manifest_path: Path | None = None

    def to_state(self, root: Path) -> dict[str, Any]:
        return {
            "schema_version": DRAFT_TRANSACTION_SCHEMA_VERSION,
            "token": self.token,
            "part_id": self.part_id,
            "status": self.status,
            "draft_token": self.draft_token,
            "operations": self.operations,
            "preview_step_path": _path_value(self.preview_step_path),
            "preview_step_relative_path": _relative_path_value(self.preview_step_path, root),
            "source_patch_path": _path_value(self.source_patch_path),
            "source_patch_relative_path": _relative_path_value(self.source_patch_path, root),
            "generated_source_path": _path_value(self.generated_source_path),
            "generated_source_relative_path": _relative_path_value(self.generated_source_path, root),
            "validator_stub_path": _path_value(self.validator_stub_path),
            "validator_stub_relative_path": _relative_path_value(self.validator_stub_path, root),
            "acceptance_manifest_path": _path_value(self.acceptance_manifest_path),
            "acceptance_manifest_relative_path": _relative_path_value(self.acceptance_manifest_path, root),
        }

    @classmethod
    def from_state(cls, payload: dict[str, Any]) -> DraftTransaction:
        return cls(
            token=str(payload["token"]),
            part_id=str(payload["part_id"]),
            status=str(payload.get("status") or "open"),
            draft_token=str(payload["draft_token"]) if payload.get("draft_token") else None,
            operations=[
                operation
                for operation in payload.get("operations", [])
                if isinstance(operation, dict)
            ],
            preview_step_path=_state_path_value(payload.get("preview_step_path")),
            source_patch_path=_state_path_value(payload.get("source_patch_path")),
            generated_source_path=_state_path_value(payload.get("generated_source_path")),
            validator_stub_path=_state_path_value(payload.get("validator_stub_path")),
            acceptance_manifest_path=_state_path_value(payload.get("acceptance_manifest_path")),
        )


def _path_value(path: Path | None) -> str | None:
    return str(path) if path is not None else None


def _relative_path_value(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _state_path_value(value: Any) -> Path | None:
    return Path(value).resolve() if isinstance(value, str) and value else None


def _safe_slug(value: str, *, fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._-")
    return slug or fallback


def _python_name(value: str, *, fallback: str) -> str:
    name = re.sub(r"[^0-9A-Za-z_]+", "_", value.strip()).strip("_").lower()
    if not name:
        name = fallback
    if name[0].isdigit():
        name = f"{fallback}_{name}"
    return name


def _require_positive(name: str, value: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise DraftGeometryError(f"{name} must be a positive number") from exc
    if numeric <= 0:
        raise DraftGeometryError(f"{name} must be a positive number")
    return numeric


def _float_value(name: str, value: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise DraftGeometryError(f"{name} must be a number") from exc


def _face(face: str) -> FaceSpec:
    key = str(face).strip().lower()
    try:
        return FACE_SPECS[key]
    except KeyError as exc:
        choices = ", ".join(sorted(FACE_SPECS))
        raise DraftGeometryError(f"face must be one of: {choices}") from exc


def _dims_for(part: DraftPart, spec: FaceSpec) -> tuple[float, float, float]:
    dims = part.dimensions()
    return dims[spec.u_dimension], dims[spec.v_dimension], dims[spec.depth_dimension]


def _point_on_face(part: DraftPart, spec: FaceSpec, x: float, y: float, *, at_mid_depth: bool = False) -> tuple[float, float, float]:
    u_extent, v_extent, depth = _dims_for(part, spec)
    coords = [0.0, 0.0, 0.0]
    coords[spec.u_axis] = -u_extent / 2.0 + x
    coords[spec.v_axis] = -v_extent / 2.0 + y
    coords[spec.normal_axis] = 0.0 if at_mid_depth else spec.normal_sign * depth / 2.0
    return (coords[0], coords[1], coords[2])


def _edge_distance(part: DraftPart, spec: FaceSpec, x: float, y: float, footprint_u: float, footprint_v: float) -> float:
    u_extent, v_extent, _depth = _dims_for(part, spec)
    half_u = footprint_u / 2.0
    half_v = footprint_v / 2.0
    return min(x - half_u, u_extent - x - half_u, y - half_v, v_extent - y - half_v)


def _warning_for_edge_distance(feature_id: str, feature_kind: str, edge_distance: float) -> str | None:
    if edge_distance < 0:
        return f"{feature_kind} {feature_id} extends beyond the selected face by {abs(edge_distance):.3f} mm."
    if edge_distance < 1.0:
        return f"{feature_kind} {feature_id} leaves only {edge_distance:.3f} mm to the selected face edge."
    return None


def _axis_length(part: DraftPart, spec: FaceSpec, extra: float = 2.0) -> float:
    _u_extent, _v_extent, depth = _dims_for(part, spec)
    return depth + extra


def _oriented_cylinder(radius: float, length: float, spec: FaceSpec, center: tuple[float, float, float]):
    if spec.normal_axis == 0:
        rotation = (0.0, 90.0, 0.0)
    elif spec.normal_axis == 1:
        rotation = (90.0, 0.0, 0.0)
    else:
        rotation = (0.0, 0.0, 0.0)
    return Cylinder(radius, length, rotation=rotation).moved(Location(center))


def _counterbore_center(part: DraftPart, spec: FaceSpec, x: float, y: float, depth: float) -> tuple[float, float, float]:
    center = list(_point_on_face(part, spec, x, y))
    center[spec.normal_axis] -= spec.normal_sign * depth / 2.0
    return (center[0], center[1], center[2])


def _axis_box(size: tuple[float, float, float], center: tuple[float, float, float]):
    return Box(*size).moved(Location(center))


def _top_slot_cut(length: float, width: float, cut_depth: float, center: tuple[float, float, float], angle: float):
    body_length = max(length - width, 0.0)
    if body_length > 0:
        cut = Box(body_length, width, cut_depth)
    else:
        cut = Cylinder(width / 2.0, cut_depth)
    offset = body_length / 2.0
    if offset:
        cut += Cylinder(width / 2.0, cut_depth).moved(Location((-offset, 0.0, 0.0)))
        cut += Cylinder(width / 2.0, cut_depth).moved(Location((offset, 0.0, 0.0)))
    if angle:
        cut = cut.moved(Location((0.0, 0.0, 0.0), (0.0, 0.0, angle)))
    return cut.moved(Location(center))


def _front_slot_cut(length: float, width: float, cut_depth: float, center: tuple[float, float, float], angle: float):
    body_length = max(length - width, 0.0)
    if body_length > 0:
        cut = Box(body_length, cut_depth, width)
    else:
        cut = Cylinder(width / 2.0, cut_depth, rotation=(90.0, 0.0, 0.0))
    offset = body_length / 2.0
    if offset:
        cut += Cylinder(width / 2.0, cut_depth, rotation=(90.0, 0.0, 0.0)).moved(Location((-offset, 0.0, 0.0)))
        cut += Cylinder(width / 2.0, cut_depth, rotation=(90.0, 0.0, 0.0)).moved(Location((offset, 0.0, 0.0)))
    if angle:
        cut = cut.moved(Location((0.0, 0.0, 0.0), (0.0, angle, 0.0)))
    return cut.moved(Location(center))


def _side_slot_cut(length: float, width: float, cut_depth: float, center: tuple[float, float, float], angle: float):
    body_length = max(length - width, 0.0)
    if body_length > 0:
        cut = Box(cut_depth, body_length, width)
    else:
        cut = Cylinder(width / 2.0, cut_depth, rotation=(0.0, 90.0, 0.0))
    offset = body_length / 2.0
    if offset:
        cut += Cylinder(width / 2.0, cut_depth, rotation=(0.0, 90.0, 0.0)).moved(Location((0.0, -offset, 0.0)))
        cut += Cylinder(width / 2.0, cut_depth, rotation=(0.0, 90.0, 0.0)).moved(Location((0.0, offset, 0.0)))
    if angle:
        cut = cut.moved(Location((0.0, 0.0, 0.0), (angle, 0.0, 0.0)))
    return cut.moved(Location(center))


def _slot_cut(part: DraftPart, spec: FaceSpec, feature: DraftFeature):
    assert feature.length is not None
    assert feature.width is not None
    center = _point_on_face(part, spec, feature.x, feature.y, at_mid_depth=True)
    cut_depth = _axis_length(part, spec)
    if spec.normal_axis == 2:
        return _top_slot_cut(feature.length, feature.width, cut_depth, center, feature.angle)
    if spec.normal_axis == 1:
        return _front_slot_cut(feature.length, feature.width, cut_depth, center, feature.angle)
    return _side_slot_cut(feature.length, feature.width, cut_depth, center, feature.angle)


def _bbox_payload(shape) -> dict[str, Any]:
    bb = shape.bounding_box()
    min_point = [float(bb.min.X), float(bb.min.Y), float(bb.min.Z)]
    max_point = [float(bb.max.X), float(bb.max.Y), float(bb.max.Z)]
    size = [max_point[index] - min_point[index] for index in range(3)]
    center = [(min_point[index] + max_point[index]) / 2.0 for index in range(3)]
    return {
        "units": "mm",
        "min": min_point,
        "max": max_point,
        "size": size,
        "center": center,
    }


def _copy_feature_to_face(feature: DraftFeature, *, feature_id: str, face: str) -> DraftFeature:
    return DraftFeature(
        id=feature_id,
        kind=feature.kind,
        face=face,
        x=feature.x,
        y=feature.y,
        diameter=feature.diameter,
        through=feature.through,
        depth=feature.depth,
        length=feature.length,
        width=feature.width,
        angle=feature.angle,
    )


def _tuple_literal(values: tuple[float, ...] | list[float]) -> str:
    return "(" + ", ".join(repr(float(value)) for value in values) + ")"


def _source_for_draft(draft: DraftPart) -> str:
    module_name = _python_name(draft.part_id, fallback="draft_part")
    function_name = f"make_{module_name}"
    needs_cylinder = any(feature.kind in {"hole", "counterbore"} for feature in draft.features)
    needs_slot = any(feature.kind == "slot" for feature in draft.features)
    imports = "Box"
    if needs_cylinder or needs_slot:
        imports += ", Cylinder, Location"

    lines = [
        "from __future__ import annotations",
        "",
        f"from build123d import {imports}",
        "",
        "",
    ]
    if needs_cylinder:
        lines.extend(
            [
                "def _oriented_cylinder(radius: float, length: float, normal_axis: int, center: tuple[float, float, float]):",
                "    if normal_axis == 0:",
                "        rotation = (0.0, 90.0, 0.0)",
                "    elif normal_axis == 1:",
                "        rotation = (90.0, 0.0, 0.0)",
                "    else:",
                "        rotation = (0.0, 0.0, 0.0)",
                "    return Cylinder(radius, length, rotation=rotation).moved(Location(center))",
                "",
                "",
            ]
        )
    if needs_slot:
        lines.extend(
            [
                "def _slot_cut(length: float, width: float, cut_depth: float, normal_axis: int, center: tuple[float, float, float], angle: float):",
                "    body_length = max(length - width, 0.0)",
                "    if normal_axis == 2:",
                "        cut = Box(body_length, width, cut_depth) if body_length > 0 else Cylinder(width / 2.0, cut_depth)",
                "        if body_length > 0:",
                "            offset = body_length / 2.0",
                "            cut += Cylinder(width / 2.0, cut_depth).moved(Location((-offset, 0.0, 0.0)))",
                "            cut += Cylinder(width / 2.0, cut_depth).moved(Location((offset, 0.0, 0.0)))",
                "        if angle:",
                "            cut = cut.moved(Location((0.0, 0.0, 0.0), (0.0, 0.0, angle)))",
                "    elif normal_axis == 1:",
                "        cut = Box(body_length, cut_depth, width) if body_length > 0 else Cylinder(width / 2.0, cut_depth, rotation=(90.0, 0.0, 0.0))",
                "        if body_length > 0:",
                "            offset = body_length / 2.0",
                "            cut += Cylinder(width / 2.0, cut_depth, rotation=(90.0, 0.0, 0.0)).moved(Location((-offset, 0.0, 0.0)))",
                "            cut += Cylinder(width / 2.0, cut_depth, rotation=(90.0, 0.0, 0.0)).moved(Location((offset, 0.0, 0.0)))",
                "        if angle:",
                "            cut = cut.moved(Location((0.0, 0.0, 0.0), (0.0, angle, 0.0)))",
                "    else:",
                "        cut = Box(cut_depth, body_length, width) if body_length > 0 else Cylinder(width / 2.0, cut_depth, rotation=(0.0, 90.0, 0.0))",
                "        if body_length > 0:",
                "            offset = body_length / 2.0",
                "            cut += Cylinder(width / 2.0, cut_depth, rotation=(0.0, 90.0, 0.0)).moved(Location((0.0, -offset, 0.0)))",
                "            cut += Cylinder(width / 2.0, cut_depth, rotation=(0.0, 90.0, 0.0)).moved(Location((0.0, offset, 0.0)))",
                "        if angle:",
                "            cut = cut.moved(Location((0.0, 0.0, 0.0), (angle, 0.0, 0.0)))",
                "    return cut.moved(Location(center))",
                "",
                "",
            ]
        )

    lines.extend(
        [
            f"def {function_name}(_params):",
            f"    part = Box({draft.length!r}, {draft.width!r}, {draft.height!r})",
        ]
    )
    for feature in draft.features:
        spec = _face(feature.face)
        if feature.kind == "hole":
            assert feature.diameter is not None
            if feature.through is False:
                lines.append(f"    # Draft hole {feature.id} requested through=False; generated source uses a through cut.")
            center = _point_on_face(draft, spec, feature.x, feature.y, at_mid_depth=True)
            lines.append(
                "    part = part - "
                f"_oriented_cylinder({feature.diameter / 2.0!r}, {_axis_length(draft, spec)!r}, "
                f"{spec.normal_axis}, {_tuple_literal(center)})"
            )
        elif feature.kind == "counterbore":
            assert feature.diameter is not None
            assert feature.depth is not None
            center = _counterbore_center(draft, spec, feature.x, feature.y, feature.depth)
            lines.append(
                "    part = part - "
                f"_oriented_cylinder({feature.diameter / 2.0!r}, {feature.depth + 0.2!r}, "
                f"{spec.normal_axis}, {_tuple_literal(center)})"
            )
        elif feature.kind == "slot":
            assert feature.length is not None
            assert feature.width is not None
            center = _point_on_face(draft, spec, feature.x, feature.y, at_mid_depth=True)
            lines.append(
                "    part = part - "
                f"_slot_cut({feature.length!r}, {feature.width!r}, {_axis_length(draft, spec)!r}, "
                f"{spec.normal_axis}, {_tuple_literal(center)}, {feature.angle!r})"
            )
    lines.extend(
        [
            "    return part",
            "",
            "",
            f"# Register {function_name} from your project registry/assembly source after review.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _validator_stub_for_draft(draft: DraftPart, draft_payload: dict[str, Any]) -> str:
    module_name = _python_name(draft.part_id, fallback="draft_part")
    function_name = f"validate_{module_name}_draft"
    return (
        "from __future__ import annotations\n\n"
        f"EXPECTED_DRAFT_PART_ID = {draft.part_id!r}\n"
        f"EXPECTED_DIMENSIONS_MM = {json.dumps(draft_payload['dimensions'], sort_keys=True)}\n"
        f"EXPECTED_BOUNDING_BOX_MM = {json.dumps(draft_payload['bounding_box'], sort_keys=True)}\n"
        f"EXPECTED_HOLE_CENTERS = {json.dumps(draft_payload['hole_centers'], sort_keys=True)}\n"
        f"EXPECTED_FEATURES = {json.dumps(draft_payload['feature_list'], sort_keys=True)}\n\n\n"
        f"def {function_name}(_project=None):\n"
        "    return [\n"
        "        {\n"
        "            \"level\": \"info\",\n"
        "            \"part_id\": EXPECTED_DRAFT_PART_ID,\n"
        "            \"message\": \"Draft validator stub generated by Flow CAD; replace with project-specific checks before handoff.\",\n"
        "        }\n"
        "    ]\n"
    )


def _new_file_diff(relative_path: str, content: str) -> str:
    lines = content.splitlines()
    body = "\n".join(f"+{line}" for line in lines)
    return (
        f"diff --git a/{relative_path} b/{relative_path}\n"
        "new file mode 100644\n"
        "index 0000000..0000000\n"
        "--- /dev/null\n"
        f"+++ b/{relative_path}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}\n"
    )


def _source_patch_for_draft(
    *,
    part_target: str,
    part_source: str,
    validator_target: str,
    validator_source: str,
) -> str:
    return _new_file_diff(part_target, part_source) + "\n" + _new_file_diff(validator_target, validator_source)


class DraftGeometryStore:
    """Draft-only panel geometry operations backed by project-local state."""

    def __init__(
        self,
        project: FlowCadProject,
        *,
        drafts_dir: Path | None = None,
        transactions_dir: Path | None = None,
    ):
        self.project = project
        self.root = project.root
        self.drafts_dir = (drafts_dir or project.paths.local_state / "drafts").resolve()
        self.transactions_dir = (transactions_dir or project.paths.local_state / "draft-transactions").resolve()
        self._ensure_isolated_runtime_dir(self.drafts_dir)
        self._ensure_isolated_runtime_dir(self.transactions_dir)
        self._drafts: dict[str, DraftPart] = {}
        self._transactions: dict[str, DraftTransaction] = {}

    def create_box_part(
        self,
        *,
        id: str | None = None,
        part_id: str | None = None,
        length: float,
        width: float,
        height: float,
        material: str = "draft",
        role: str = "draft",
    ) -> dict[str, Any]:
        name = _safe_slug(part_id or id or "draft_panel", fallback="draft_panel")
        token = f"{name}-{uuid4().hex[:12]}"
        draft = DraftPart(
            token=token,
            part_id=name,
            length=_require_positive("length", length),
            width=_require_positive("width", width),
            height=_require_positive("height", height),
            material=str(material or "draft"),
            role=str(role or "draft"),
        )
        self._drafts[token] = draft
        self._write_state(draft)
        return self._payload(draft)

    def set_panel_thickness(self, draft_token: str, *, thickness: float) -> dict[str, Any]:
        draft = self._require(draft_token)
        draft.height = _require_positive("thickness", thickness)
        draft.preview_step_path = None
        self._write_state(draft)
        return self._payload(draft)

    def add_hole(
        self,
        draft_token: str,
        *,
        face: str,
        x: float,
        y: float,
        diameter: float,
        through: bool = True,
    ) -> dict[str, Any]:
        draft = self._require(draft_token)
        _face(face)
        feature = DraftFeature(
            id=self._next_feature_id(draft, "hole"),
            kind="hole",
            face=str(face).lower(),
            x=_float_value("x", x),
            y=_float_value("y", y),
            diameter=_require_positive("diameter", diameter),
            through=bool(through),
        )
        draft.features.append(feature)
        draft.preview_step_path = None
        self._write_state(draft)
        return self._payload(draft)

    def add_counterbore(
        self,
        draft_token: str,
        *,
        face: str,
        x: float,
        y: float,
        diameter: float,
        depth: float,
    ) -> dict[str, Any]:
        draft = self._require(draft_token)
        _face(face)
        feature = DraftFeature(
            id=self._next_feature_id(draft, "counterbore"),
            kind="counterbore",
            face=str(face).lower(),
            x=_float_value("x", x),
            y=_float_value("y", y),
            diameter=_require_positive("diameter", diameter),
            depth=_require_positive("depth", depth),
        )
        draft.features.append(feature)
        draft.preview_step_path = None
        self._write_state(draft)
        return self._payload(draft)

    def add_slot(
        self,
        draft_token: str,
        *,
        face: str,
        x: float,
        y: float,
        length: float,
        width: float,
        angle: float = 0.0,
    ) -> dict[str, Any]:
        draft = self._require(draft_token)
        _face(face)
        slot_width = _require_positive("width", width)
        slot_length = _require_positive("length", length)
        if slot_length < slot_width:
            raise DraftGeometryError("slot length must be greater than or equal to slot width")
        feature = DraftFeature(
            id=self._next_feature_id(draft, "slot"),
            kind="slot",
            face=str(face).lower(),
            x=_float_value("x", x),
            y=_float_value("y", y),
            length=slot_length,
            width=slot_width,
            angle=_float_value("angle", angle),
        )
        draft.features.append(feature)
        draft.preview_step_path = None
        self._write_state(draft)
        return self._payload(draft)

    def add_louver_pattern(
        self,
        draft_token: str,
        *,
        face: str,
        count: int,
        pitch: float,
        x: float,
        y: float,
        width: float,
        height: float,
        angle: float = 0.0,
    ) -> dict[str, Any]:
        draft = self._require(draft_token)
        _face(face)
        if int(count) <= 0:
            raise DraftGeometryError("count must be a positive integer")
        slot_pitch = _require_positive("pitch", pitch)
        slot_length = _require_positive("width", width)
        slot_width = _require_positive("height", height)
        if slot_length < slot_width:
            raise DraftGeometryError("louver width must be greater than or equal to louver height")
        center_index = (int(count) - 1) / 2.0
        for index in range(int(count)):
            draft.features.append(
                DraftFeature(
                    id=self._next_feature_id(draft, "louver"),
                    kind="slot",
                    face=str(face).lower(),
                    x=_float_value("x", x) + (index - center_index) * slot_pitch,
                    y=_float_value("y", y),
                    length=slot_length,
                    width=slot_width,
                    angle=_float_value("angle", angle),
                )
            )
        draft.preview_step_path = None
        self._write_state(draft)
        return self._payload(draft)

    def mirror_features(self, draft_token: str, *, source_face: str, target_face: str) -> dict[str, Any]:
        draft = self._require(draft_token)
        source = _face(source_face)
        target = _face(target_face)
        if source.name == target.name:
            raise DraftGeometryError("source_face and target_face must be different")
        if source.normal_axis != target.normal_axis:
            raise DraftGeometryError("source_face and target_face must be opposing faces with matching local dimensions")

        features_to_mirror = [feature for feature in draft.features if feature.face == source.name]
        if not features_to_mirror:
            raise DraftGeometryError(f"No features found on source face: {source.name}")

        for feature in features_to_mirror:
            id_prefix = feature.id.rsplit("_", maxsplit=1)[0] if "_" in feature.id else feature.kind
            draft.features.append(
                _copy_feature_to_face(
                    feature,
                    feature_id=self._next_feature_id(draft, id_prefix),
                    face=target.name,
                )
            )
        draft.preview_step_path = None
        self._write_state(draft)
        return self._payload(draft)

    def measure_part(self, draft_token: str) -> dict[str, Any]:
        return self._payload(self._require(draft_token))

    def export_draft_step(self, draft_token: str) -> dict[str, Any]:
        draft = self._require(draft_token)
        shape, _shape_warnings = self._build_shape(draft)
        preview_path = self._draft_dir(draft.token) / f"{draft.part_id}.step"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        ok = export_step(shape, preview_path)
        if not ok:
            raise DraftGeometryError(f"Draft STEP export failed: {preview_path}")
        normalize_step_file(preview_path)
        draft.preview_step_path = preview_path
        self._write_state(draft)
        return self._payload(draft)

    def discard(self, draft_token: str) -> dict[str, Any]:
        draft = self._require(draft_token)
        self._drafts.pop(draft.token, None)
        draft_dir = self._draft_dir(draft.token)
        if draft_dir.exists():
            shutil.rmtree(draft_dir)
        return {"ok": True, "draft_token": draft.token, "discarded": True}

    def begin_transaction(self, *, part_id: str | None = None) -> dict[str, Any]:
        name = _safe_slug(part_id or "draft_panel", fallback="draft_panel")
        token = f"{name}-{uuid4().hex[:12]}"
        transaction = DraftTransaction(token=token, part_id=name)
        self._transactions[token] = transaction
        self._write_transaction_state(transaction)
        return self._transaction_payload(transaction)

    def transaction_create_box(
        self,
        transaction_token: str,
        *,
        length: float,
        width: float,
        height: float,
        part_id: str | None = None,
        material: str = "draft",
        role: str = "draft",
    ) -> dict[str, Any]:
        transaction = self._require_open_transaction(transaction_token)
        if transaction.draft_token is not None:
            raise DraftGeometryError(f"Draft transaction already has a draft part: {transaction.token}")
        draft_payload = self.create_box_part(
            part_id=part_id or transaction.part_id,
            length=length,
            width=width,
            height=height,
            material=material,
            role=role,
        )
        transaction.part_id = str(draft_payload["part_id"])
        transaction.draft_token = str(draft_payload["draft_token"])
        self._record_transaction_operation(
            transaction,
            "create_box",
            {
                "part_id": transaction.part_id,
                "length": float(length),
                "width": float(width),
                "height": float(height),
                "material": str(material or "draft"),
                "role": str(role or "draft"),
            },
        )
        return self._transaction_payload(transaction, draft_payload=draft_payload)

    def transaction_set_panel_thickness(self, transaction_token: str, *, thickness: float) -> dict[str, Any]:
        transaction, draft_token = self._require_open_transaction_draft(transaction_token)
        draft_payload = self.set_panel_thickness(draft_token, thickness=thickness)
        self._record_transaction_operation(transaction, "set_panel_thickness", {"thickness": float(thickness)})
        return self._transaction_payload(transaction, draft_payload=draft_payload)

    def transaction_add_hole(
        self,
        transaction_token: str,
        *,
        face: str,
        x: float,
        y: float,
        diameter: float,
        through: bool = True,
    ) -> dict[str, Any]:
        transaction, draft_token = self._require_open_transaction_draft(transaction_token)
        draft_payload = self.add_hole(draft_token, face=face, x=x, y=y, diameter=diameter, through=through)
        self._record_transaction_operation(
            transaction,
            "add_hole",
            {
                "face": str(face).lower(),
                "x": float(x),
                "y": float(y),
                "diameter": float(diameter),
                "through": bool(through),
            },
        )
        return self._transaction_payload(transaction, draft_payload=draft_payload)

    def transaction_add_counterbore(
        self,
        transaction_token: str,
        *,
        face: str,
        x: float,
        y: float,
        diameter: float,
        depth: float,
    ) -> dict[str, Any]:
        transaction, draft_token = self._require_open_transaction_draft(transaction_token)
        draft_payload = self.add_counterbore(draft_token, face=face, x=x, y=y, diameter=diameter, depth=depth)
        self._record_transaction_operation(
            transaction,
            "add_counterbore",
            {
                "face": str(face).lower(),
                "x": float(x),
                "y": float(y),
                "diameter": float(diameter),
                "depth": float(depth),
            },
        )
        return self._transaction_payload(transaction, draft_payload=draft_payload)

    def transaction_add_slot(
        self,
        transaction_token: str,
        *,
        face: str,
        x: float,
        y: float,
        length: float,
        width: float,
        angle: float = 0.0,
    ) -> dict[str, Any]:
        transaction, draft_token = self._require_open_transaction_draft(transaction_token)
        draft_payload = self.add_slot(draft_token, face=face, x=x, y=y, length=length, width=width, angle=angle)
        self._record_transaction_operation(
            transaction,
            "add_slot",
            {
                "face": str(face).lower(),
                "x": float(x),
                "y": float(y),
                "length": float(length),
                "width": float(width),
                "angle": float(angle),
            },
        )
        return self._transaction_payload(transaction, draft_payload=draft_payload)

    def transaction_add_louver_pattern(
        self,
        transaction_token: str,
        *,
        face: str,
        count: int,
        pitch: float,
        x: float,
        y: float,
        width: float,
        height: float,
        angle: float = 0.0,
    ) -> dict[str, Any]:
        transaction, draft_token = self._require_open_transaction_draft(transaction_token)
        draft_payload = self.add_louver_pattern(
            draft_token,
            face=face,
            count=count,
            pitch=pitch,
            x=x,
            y=y,
            width=width,
            height=height,
            angle=angle,
        )
        self._record_transaction_operation(
            transaction,
            "add_louver_pattern",
            {
                "face": str(face).lower(),
                "count": int(count),
                "pitch": float(pitch),
                "x": float(x),
                "y": float(y),
                "width": float(width),
                "height": float(height),
                "angle": float(angle),
            },
        )
        return self._transaction_payload(transaction, draft_payload=draft_payload)

    def transaction_mirror_features(self, transaction_token: str, *, source_face: str, target_face: str) -> dict[str, Any]:
        transaction, draft_token = self._require_open_transaction_draft(transaction_token)
        draft_payload = self.mirror_features(draft_token, source_face=source_face, target_face=target_face)
        self._record_transaction_operation(
            transaction,
            "mirror_features",
            {"source_face": str(source_face).lower(), "target_face": str(target_face).lower()},
        )
        return self._transaction_payload(transaction, draft_payload=draft_payload)

    def transaction_measure(self, transaction_token: str) -> dict[str, Any]:
        transaction, draft_token = self._require_transaction_draft(transaction_token)
        return self._transaction_payload(transaction, draft_payload=self.measure_part(draft_token))

    def transaction_preview(self, transaction_token: str) -> dict[str, Any]:
        transaction, draft_token = self._require_open_transaction_draft(transaction_token)
        draft_payload = self.export_draft_step(draft_token)
        transaction.preview_step_path = Path(str(draft_payload["preview_step_path"]))
        self._record_transaction_operation(
            transaction,
            "preview",
            {"preview_step_path": str(transaction.preview_step_path)},
        )
        return self._transaction_payload(transaction, draft_payload=draft_payload)

    def accept_transaction(self, transaction_token: str) -> dict[str, Any]:
        transaction, draft_token = self._require_open_transaction_draft(transaction_token)
        draft_payload = self.export_draft_step(draft_token)
        transaction.preview_step_path = Path(str(draft_payload["preview_step_path"]))
        draft = self._require(draft_token)
        module_name = _python_name(draft.part_id, fallback="draft_part")
        part_target = f"flow/parts/{module_name}.py"
        validator_target = f"flow/validators/check_{module_name}_draft.py"
        part_source = _source_for_draft(draft)
        validator_source = _validator_stub_for_draft(draft, draft_payload)
        patch_source = _source_patch_for_draft(
            part_target=part_target,
            part_source=part_source,
            validator_target=validator_target,
            validator_source=validator_source,
        )

        accept_dir = self._transaction_dir(transaction.token) / "accept"
        accept_dir.mkdir(parents=True, exist_ok=True)
        source_patch_path = accept_dir / "source.patch"
        generated_source_path = accept_dir / f"{module_name}.py"
        validator_stub_path = accept_dir / f"check_{module_name}_draft.py"
        acceptance_manifest_path = accept_dir / "acceptance.json"
        source_patch_path.write_text(patch_source, encoding="utf-8")
        generated_source_path.write_text(part_source, encoding="utf-8")
        validator_stub_path.write_text(validator_source, encoding="utf-8")

        transaction.status = "accepted"
        transaction.source_patch_path = source_patch_path
        transaction.generated_source_path = generated_source_path
        transaction.validator_stub_path = validator_stub_path
        transaction.acceptance_manifest_path = acceptance_manifest_path
        self._record_transaction_operation(
            transaction,
            "accept",
            {
                "part_target": part_target,
                "validator_target": validator_target,
                "source_patch_path": str(source_patch_path),
            },
            write=False,
        )
        acceptance_manifest = {
            "schema_version": DRAFT_TRANSACTION_SCHEMA_VERSION,
            "transaction": transaction.to_state(self.root),
            "part_target": part_target,
            "validator_target": validator_target,
            "draft": draft_payload,
        }
        acceptance_manifest_path.write_text(
            json.dumps(acceptance_manifest, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._write_transaction_state(transaction)
        return self._transaction_payload(transaction, draft_payload=draft_payload)

    def discard_transaction(self, transaction_token: str) -> dict[str, Any]:
        transaction = self._require_open_transaction(transaction_token)
        if transaction.draft_token is not None:
            try:
                self.discard(transaction.draft_token)
            except DraftNotFoundError:
                pass
        self._transactions.pop(transaction.token, None)
        transaction_dir = self._transaction_dir(transaction.token)
        if transaction_dir.exists():
            shutil.rmtree(transaction_dir)
        return {"ok": True, "transaction_token": transaction.token, "discarded": True}

    def _payload(self, draft: DraftPart) -> dict[str, Any]:
        shape, shape_warnings = self._build_shape(draft)
        feature_payloads, feature_warnings, hole_centers = self._feature_payloads(draft)
        warnings = [*feature_warnings, *shape_warnings]
        payload = draft.to_state(self.root)
        payload.update(
            {
                "ok": True,
                "draft_token": draft.token,
                "bounding_box": _bbox_payload(shape),
                "feature_list": feature_payloads,
                "hole_centers": hole_centers,
                "warnings": warnings,
            }
        )
        return payload

    def _build_shape(self, draft: DraftPart):
        shape = Box(draft.length, draft.width, draft.height)
        warnings: list[str] = []
        for feature in draft.features:
            spec = _face(feature.face)
            try:
                if feature.kind == "hole":
                    assert feature.diameter is not None
                    if feature.through is False:
                        warnings.append(f"hole {feature.id} requested through=false; draft holes are currently through-cut.")
                    cut = _oriented_cylinder(
                        feature.diameter / 2.0,
                        _axis_length(draft, spec),
                        spec,
                        _point_on_face(draft, spec, feature.x, feature.y, at_mid_depth=True),
                    )
                elif feature.kind == "counterbore":
                    assert feature.diameter is not None
                    assert feature.depth is not None
                    cut = _oriented_cylinder(
                        feature.diameter / 2.0,
                        feature.depth + 0.2,
                        spec,
                        _counterbore_center(draft, spec, feature.x, feature.y, feature.depth),
                    )
                elif feature.kind == "slot":
                    cut = _slot_cut(draft, spec, feature)
                else:
                    continue
                shape = shape - cut
            except Exception as exc:
                warnings.append(f"{feature.kind} {feature.id} could not be applied to draft geometry: {exc}")
        return shape, warnings

    def _feature_payloads(self, draft: DraftPart) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
        payloads: list[dict[str, Any]] = []
        warnings: list[str] = []
        hole_centers: list[dict[str, Any]] = []
        for feature in draft.features:
            spec = _face(feature.face)
            axis = list(spec.axis)
            center = list(_point_on_face(draft, spec, feature.x, feature.y, at_mid_depth=True))
            footprint_u, footprint_v = self._feature_footprint(feature)
            edge_distance = _edge_distance(draft, spec, feature.x, feature.y, footprint_u, footprint_v)
            edge_warning = _warning_for_edge_distance(feature.id, feature.kind, edge_distance)
            if edge_warning:
                warnings.append(edge_warning)
            feature_payload: dict[str, Any] = {
                "id": feature.id,
                "kind": feature.kind,
                "face": feature.face,
                "center": center,
                "axis": axis,
                "minimum_edge_distance_mm": edge_distance,
                "parameters": {
                    key: value
                    for key, value in feature.to_state().items()
                    if key not in {"id", "kind", "face"}
                },
            }
            if feature.kind in {"hole", "counterbore"}:
                assert feature.diameter is not None
                feature_payload["diameter"] = feature.diameter
                hole_centers.append(
                    {
                        "feature_id": feature.id,
                        "kind": feature.kind,
                        "face": feature.face,
                        "center": center,
                        "axis": axis,
                        "diameter": feature.diameter,
                        "through": feature.through if feature.kind == "hole" else False,
                    }
                )
            if feature.kind == "counterbore":
                assert feature.depth is not None
                _u_extent, _v_extent, face_depth = _dims_for(draft, spec)
                if feature.depth > face_depth:
                    warnings.append(
                        f"counterbore {feature.id} depth {feature.depth:.3f} mm exceeds face depth {face_depth:.3f} mm."
                    )
                feature_payload["depth"] = feature.depth
            if feature.kind == "slot":
                feature_payload["length"] = feature.length
                feature_payload["width"] = feature.width
                feature_payload["angle"] = feature.angle
            payloads.append(feature_payload)
        return payloads, warnings, hole_centers

    @staticmethod
    def _feature_footprint(feature: DraftFeature) -> tuple[float, float]:
        if feature.kind in {"hole", "counterbore"}:
            assert feature.diameter is not None
            return feature.diameter, feature.diameter
        assert feature.length is not None
        assert feature.width is not None
        radians = math.radians(feature.angle)
        half_u = abs(math.cos(radians)) * feature.length / 2.0 + abs(math.sin(radians)) * feature.width / 2.0
        half_v = abs(math.sin(radians)) * feature.length / 2.0 + abs(math.cos(radians)) * feature.width / 2.0
        return 2.0 * half_u, 2.0 * half_v

    def _transaction_payload(
        self,
        transaction: DraftTransaction,
        *,
        draft_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if draft_payload is None and transaction.draft_token is not None:
            draft_payload = self.measure_part(transaction.draft_token)
        payload = transaction.to_state(self.root)
        payload.update(
            {
                "ok": True,
                "transaction_token": transaction.token,
                "draft": draft_payload,
            }
        )
        return payload

    def _record_transaction_operation(
        self,
        transaction: DraftTransaction,
        name: str,
        parameters: dict[str, Any],
        *,
        write: bool = True,
    ) -> None:
        transaction.operations.append(
            {
                "index": len(transaction.operations) + 1,
                "name": name,
                "parameters": parameters,
            }
        )
        if write:
            self._write_transaction_state(transaction)

    def _require(self, draft_token: str) -> DraftPart:
        try:
            return self._drafts[draft_token]
        except KeyError as exc:
            loaded = self._load_state(draft_token)
            if loaded is not None:
                self._drafts[loaded.token] = loaded
                return loaded
            raise DraftNotFoundError(f"Draft token is not active: {draft_token}") from exc

    def _require_transaction(self, transaction_token: str) -> DraftTransaction:
        try:
            return self._transactions[transaction_token]
        except KeyError as exc:
            loaded = self._load_transaction_state(transaction_token)
            if loaded is not None:
                self._transactions[loaded.token] = loaded
                return loaded
            raise DraftNotFoundError(f"Draft transaction token is not active: {transaction_token}") from exc

    def _require_open_transaction(self, transaction_token: str) -> DraftTransaction:
        transaction = self._require_transaction(transaction_token)
        if transaction.status != "open":
            raise DraftGeometryError(f"Draft transaction is not open: {transaction.token} status={transaction.status}")
        return transaction

    def _require_transaction_draft(self, transaction_token: str) -> tuple[DraftTransaction, str]:
        transaction = self._require_transaction(transaction_token)
        if transaction.draft_token is None:
            raise DraftGeometryError(f"Draft transaction has no draft part yet: {transaction.token}")
        return transaction, transaction.draft_token

    def _require_open_transaction_draft(self, transaction_token: str) -> tuple[DraftTransaction, str]:
        transaction = self._require_open_transaction(transaction_token)
        if transaction.draft_token is None:
            raise DraftGeometryError(f"Draft transaction has no draft part yet: {transaction.token}")
        return transaction, transaction.draft_token

    @staticmethod
    def _next_feature_id(draft: DraftPart, prefix: str) -> str:
        return f"{prefix}_{len(draft.features) + 1}"

    def _draft_dir(self, draft_token: str) -> Path:
        return self.drafts_dir / _safe_slug(draft_token, fallback="draft")

    def _state_path(self, draft_token: str) -> Path:
        return self._draft_dir(draft_token) / "draft.json"

    def _transaction_dir(self, transaction_token: str) -> Path:
        return self.transactions_dir / _safe_slug(transaction_token, fallback="transaction")

    def _transaction_state_path(self, transaction_token: str) -> Path:
        return self._transaction_dir(transaction_token) / "transaction.json"

    def _write_state(self, draft: DraftPart) -> None:
        path = self._state_path(draft.token)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(draft.to_state(self.root), indent=2, sort_keys=True), encoding="utf-8")

    def _write_transaction_state(self, transaction: DraftTransaction) -> None:
        path = self._transaction_state_path(transaction.token)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(transaction.to_state(self.root), indent=2, sort_keys=True), encoding="utf-8")

    def _load_state(self, draft_token: str) -> DraftPart | None:
        path = self._state_path(draft_token)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("schema_version") != DRAFT_SCHEMA_VERSION:
            return None
        return DraftPart.from_state(payload)

    def _load_transaction_state(self, transaction_token: str) -> DraftTransaction | None:
        path = self._transaction_state_path(transaction_token)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("schema_version") != DRAFT_TRANSACTION_SCHEMA_VERSION:
            return None
        return DraftTransaction.from_state(payload)

    def _ensure_isolated_runtime_dir(self, runtime_dir: Path) -> None:
        protected_roots = (
            self.root / "flow",
            self.project.paths.exports,
            self.project.paths.reports,
            self.root / "handoff",
        )
        for protected_root in protected_roots:
            protected = protected_root.resolve()
            if runtime_dir == protected or runtime_dir.is_relative_to(protected):
                raise DraftGeometryError(
                    f"Draft artifacts must stay out of project source and handoff outputs: {runtime_dir}"
                )
