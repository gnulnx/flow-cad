from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


SCHEMA_VERSION = 1
Vector3 = tuple[float, float, float]
EditEntityKind = Literal["primitive_box"]
PointQuality = Literal["exact", "approximate"]


@dataclass(frozen=True)
class EditTransform:
    translation_mm: Vector3 = (0.0, 0.0, 0.0)
    rotation_deg: Vector3 = (0.0, 0.0, 0.0)

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "EditTransform":
        payload = payload or {}
        return cls(
            translation_mm=_vector3(payload.get("translation_mm"), default=(0.0, 0.0, 0.0), field_name="translation_mm"),
            rotation_deg=_vector3(payload.get("rotation_deg"), default=(0.0, 0.0, 0.0), field_name="rotation_deg"),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "translation_mm": list(self.translation_mm),
            "rotation_deg": list(self.rotation_deg),
        }


@dataclass(frozen=True)
class EditHoleCut:
    id: str
    point_id: str
    position_mm: Vector3
    axis: Vector3 = (0.0, 0.0, 1.0)
    preset: str = "m4_clearance"
    diameter_mm: float = 4.5
    through: bool = True

    @classmethod
    def from_payload(cls, hole_id: str, payload: dict[str, Any]) -> "EditHoleCut":
        diameter = float(payload.get("diameter_mm", 0.0))
        if diameter <= 0:
            raise ValueError("`diameter_mm` must be positive")
        axis = _vector3(payload.get("axis"), default=(0.0, 0.0, 1.0), field_name="axis")
        if sum(abs(value) for value in axis) == 0:
            raise ValueError("`axis` must not be the zero vector")
        return cls(
            id=hole_id,
            point_id=str(payload.get("point_id") or ""),
            position_mm=_vector3(payload.get("position_mm"), default=(0.0, 0.0, 0.0), field_name="position_mm"),
            axis=axis,
            preset=str(payload.get("preset") or "m4_clearance"),
            diameter_mm=diameter,
            through=bool(payload.get("through", True)),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "point_id": self.point_id,
            "position_mm": list(self.position_mm),
            "axis": list(self.axis),
            "preset": self.preset,
            "diameter_mm": self.diameter_mm,
            "through": self.through,
        }


@dataclass(frozen=True)
class EditEntity:
    id: str
    kind: EditEntityKind
    name: str
    size_mm: Vector3
    transform: EditTransform = field(default_factory=EditTransform)
    role: str = "inspection"
    holes: tuple[EditHoleCut, ...] = ()

    @classmethod
    def from_payload(cls, entity_id: str, payload: dict[str, Any]) -> "EditEntity":
        kind = payload.get("kind")
        if kind != "primitive_box":
            raise ValueError(f"Unsupported edit entity kind for {entity_id}: {kind!r}")
        raw_holes = payload.get("holes", [])
        if not isinstance(raw_holes, list):
            raise ValueError(f"Edit entity `{entity_id}` holes must be a list")
        holes: list[EditHoleCut] = []
        for index, hole_payload in enumerate(raw_holes, start=1):
            if not isinstance(hole_payload, dict):
                raise ValueError(f"Edit entity `{entity_id}` hole must be an object")
            hole_id = str(hole_payload.get("id") or f"hole_{index:03d}")
            holes.append(EditHoleCut.from_payload(hole_id, hole_payload))

        return cls(
            id=entity_id,
            kind="primitive_box",
            name=str(payload.get("name") or entity_id),
            size_mm=_vector3(payload.get("size_mm"), default=(20.0, 20.0, 20.0), field_name="size_mm"),
            transform=EditTransform.from_payload(_dict_or_none(payload.get("transform"), field_name="transform")),
            role=str(payload.get("role") or "inspection"),
            holes=tuple(holes),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "size_mm": list(self.size_mm),
            "transform": self.transform.to_payload(),
            "role": self.role,
            "holes": [hole.to_payload() for hole in self.holes],
        }


@dataclass(frozen=True)
class EditPoint:
    id: str
    position_mm: Vector3
    coordinate_space: str = "world"
    quality: PointQuality = "exact"
    source: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, point_id: str, payload: dict[str, Any]) -> "EditPoint":
        quality = str(payload.get("quality") or "exact")
        if quality not in {"exact", "approximate"}:
            raise ValueError(f"Unsupported point quality for {point_id}: {quality!r}")
        quality_value: PointQuality = "exact" if quality == "exact" else "approximate"
        source = payload.get("source", {})
        if source is not None and not isinstance(source, dict):
            raise ValueError("`source` must be an object")
        return cls(
            id=point_id,
            position_mm=_vector3(payload.get("position_mm"), default=(0.0, 0.0, 0.0), field_name="position_mm"),
            coordinate_space=str(payload.get("coordinate_space") or "world"),
            quality=quality_value,
            source=source or {},
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "position_mm": list(self.position_mm),
            "coordinate_space": self.coordinate_space,
            "quality": self.quality,
            "source": self.source,
        }


@dataclass(frozen=True)
class EditDocument:
    schema_version: int = SCHEMA_VERSION
    document_id: str = "main"
    units: str = "mm"
    revision: int = 0
    entities: dict[str, EditEntity] = field(default_factory=dict)
    points: dict[str, EditPoint] = field(default_factory=dict)
    operations: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def empty(cls) -> "EditDocument":
        return cls()

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "EditDocument":
        schema_version = int(payload.get("schema_version", SCHEMA_VERSION))
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported edit document schema_version: {schema_version}")

        raw_entities = payload.get("entities", {})
        if not isinstance(raw_entities, dict):
            raise ValueError("Edit document `entities` must be an object")

        raw_operations = payload.get("operations", [])
        if not isinstance(raw_operations, list):
            raise ValueError("Edit document `operations` must be a list")

        raw_points = payload.get("points", {})
        if not isinstance(raw_points, dict):
            raise ValueError("Edit document `points` must be an object")

        entities: dict[str, EditEntity] = {}
        for entity_id, entity_payload in raw_entities.items():
            if not isinstance(entity_payload, dict):
                raise ValueError(f"Edit entity `{entity_id}` must be an object")
            entities[str(entity_id)] = EditEntity.from_payload(str(entity_id), entity_payload)
        points: dict[str, EditPoint] = {}
        for point_id, point_payload in raw_points.items():
            if not isinstance(point_payload, dict):
                raise ValueError(f"Edit point `{point_id}` must be an object")
            points[str(point_id)] = EditPoint.from_payload(str(point_id), point_payload)
        return cls(
            schema_version=schema_version,
            document_id=str(payload.get("document_id") or "main"),
            units=str(payload.get("units") or "mm"),
            revision=int(payload.get("revision", 0)),
            entities=entities,
            points=points,
            operations=[operation for operation in raw_operations if isinstance(operation, dict)],
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "document_id": self.document_id,
            "units": self.units,
            "revision": self.revision,
            "entities": {
                entity_id: entity.to_payload()
                for entity_id, entity in self.entities.items()
            },
            "points": {
                point_id: point.to_payload()
                for point_id, point in self.points.items()
            },
            "operations": self.operations,
        }

    def with_entity_and_operation(self, entity: EditEntity, operation: dict[str, Any]) -> "EditDocument":
        return EditDocument(
            schema_version=self.schema_version,
            document_id=self.document_id,
            units=self.units,
            revision=self.revision + 1,
            entities={**self.entities, entity.id: entity},
            points=self.points,
            operations=[*self.operations, operation],
        )

    def with_point_and_operation(self, point: EditPoint, operation: dict[str, Any]) -> "EditDocument":
        return EditDocument(
            schema_version=self.schema_version,
            document_id=self.document_id,
            units=self.units,
            revision=self.revision + 1,
            entities=self.entities,
            points={**self.points, point.id: point},
            operations=[*self.operations, operation],
        )


def _vector3(value: Any, *, default: Vector3, field_name: str) -> Vector3:
    if value is None:
        return default
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"`{field_name}` must be a three-number array")
    vector = tuple(float(item) for item in value)
    if any(item <= 0 for item in vector) and field_name == "size_mm":
        raise ValueError("`size_mm` values must be positive")
    return (vector[0], vector[1], vector[2])


def _dict_or_none(value: Any, *, field_name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"`{field_name}` must be an object")
    return value
