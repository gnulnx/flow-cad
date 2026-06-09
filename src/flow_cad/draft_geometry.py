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


def _safe_slug(value: str, *, fallback: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._-")
    return slug or fallback


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


class DraftGeometryStore:
    """Draft-only panel geometry operations backed by project-local state."""

    def __init__(self, project: FlowCadProject, *, drafts_dir: Path | None = None):
        self.project = project
        self.root = project.root
        self.drafts_dir = (drafts_dir or project.paths.local_state / "drafts").resolve()
        self._ensure_isolated_drafts_dir()
        self._drafts: dict[str, DraftPart] = {}

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

    def _require(self, draft_token: str) -> DraftPart:
        try:
            return self._drafts[draft_token]
        except KeyError as exc:
            loaded = self._load_state(draft_token)
            if loaded is not None:
                self._drafts[loaded.token] = loaded
                return loaded
            raise DraftNotFoundError(f"Draft token is not active: {draft_token}") from exc

    @staticmethod
    def _next_feature_id(draft: DraftPart, prefix: str) -> str:
        return f"{prefix}_{len(draft.features) + 1}"

    def _draft_dir(self, draft_token: str) -> Path:
        return self.drafts_dir / _safe_slug(draft_token, fallback="draft")

    def _state_path(self, draft_token: str) -> Path:
        return self._draft_dir(draft_token) / "draft.json"

    def _write_state(self, draft: DraftPart) -> None:
        path = self._state_path(draft.token)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(draft.to_state(self.root), indent=2, sort_keys=True), encoding="utf-8")

    def _load_state(self, draft_token: str) -> DraftPart | None:
        path = self._state_path(draft_token)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict) or payload.get("schema_version") != DRAFT_SCHEMA_VERSION:
            return None
        return DraftPart.from_state(payload)

    def _ensure_isolated_drafts_dir(self) -> None:
        protected_roots = (
            self.root / "flow",
            self.project.paths.exports,
            self.project.paths.reports,
            self.root / "handoff",
        )
        for protected_root in protected_roots:
            protected = protected_root.resolve()
            if self.drafts_dir == protected or self.drafts_dir.is_relative_to(protected):
                raise DraftGeometryError(
                    f"Draft artifacts must stay out of project source and handoff outputs: {self.drafts_dir}"
                )
