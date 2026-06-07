from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from flow_cad.editing.models import EditDocument, EditEntity, EditHoleCut
from flow_cad.step_io import normalize_step_file


class EditKernelError(RuntimeError):
    pass


def shape_for_entity(entity: EditEntity, document: EditDocument | None = None, _seen: frozenset[str] | None = None) -> Any:
    if entity.kind != "primitive_box":
        raise EditKernelError(f"Unsupported edit entity kind: {entity.kind}")
    try:
        from build123d import Box, Location
    except Exception as exc:  # pragma: no cover - depends on local CAD install
        raise EditKernelError(
            "Edit kernel operations require build123d/OCP. Install project dependencies or configure the CAD environment."
        ) from exc

    shape = Box(*entity.size_mm).moved(Location(entity.transform.translation_mm, entity.transform.rotation_deg))
    for hole in entity.holes:
        shape = _cut_through_hole(shape, hole)
    for operation in entity.booleans:
        if document is None:
            raise EditKernelError(f"Boolean operation {operation.id} requires an edit document")
        shape = _apply_boolean_operation(shape, document, operation.tool_entity_id, operation.type, (_seen or frozenset()) | {entity.id})
    return shape


def export_entity_step(entity: EditEntity, path: Path, document: EditDocument | None = None) -> Path:
    try:
        from build123d import export_step
    except Exception as exc:  # pragma: no cover - depends on local CAD install
        raise EditKernelError(
            "Edit STEP export requires build123d/OCP. Install project dependencies or configure the CAD environment."
        ) from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    ok = export_step(shape_for_entity(entity, document), path)
    if not ok:
        raise EditKernelError(f"STEP export failed for edit entity: {entity.id}")
    normalize_step_file(path)
    return path


def bounding_box_payload(entity: EditEntity, document: EditDocument | None = None) -> dict[str, Any]:
    shape = shape_for_entity(entity, document)
    bb = shape.bounding_box()
    min_point = (float(bb.min.X), float(bb.min.Y), float(bb.min.Z))
    max_point = (float(bb.max.X), float(bb.max.Y), float(bb.max.Z))
    return {
        "min_mm": list(min_point),
        "max_mm": list(max_point),
        "size_mm": [
            max_point[0] - min_point[0],
            max_point[1] - min_point[1],
            max_point[2] - min_point[2],
        ],
        "center_mm": [
            (min_point[0] + max_point[0]) / 2,
            (min_point[1] + max_point[1]) / 2,
            (min_point[2] + max_point[2]) / 2,
        ],
    }


def _apply_boolean_operation(
    target_shape: Any,
    document: EditDocument,
    tool_entity_id: str,
    operation_type: str,
    seen: frozenset[str],
) -> Any:
    if tool_entity_id in seen:
        raise EditKernelError(f"Boolean operation cycle detected at edit entity: {tool_entity_id}")
    try:
        tool_entity = document.entities[tool_entity_id]
    except KeyError as exc:
        raise EditKernelError(f"Boolean tool entity is not registered: {tool_entity_id}") from exc
    tool_shape = shape_for_entity(tool_entity, document, seen)
    try:
        if operation_type == "fuse":
            result = target_shape + tool_shape
        elif operation_type == "cut":
            result = target_shape - tool_shape
        else:
            raise EditKernelError(f"Unsupported boolean operation type: {operation_type}")
        return result.clean()
    except Exception as exc:
        raise EditKernelError(f"Could not apply boolean {operation_type} with tool {tool_entity_id}: {exc}") from exc


def _cut_through_hole(shape: Any, hole: EditHoleCut) -> Any:
    if not hole.through:
        raise EditKernelError("Only through-hole cuts are supported in the edit kernel")
    try:
        from build123d import Cylinder, Location
    except Exception as exc:  # pragma: no cover - depends on local CAD install
        raise EditKernelError(
            "Edit kernel operations require build123d/OCP. Install project dependencies or configure the CAD environment."
        ) from exc

    axis = _cardinal_axis(hole.axis)
    length = _through_length(shape, axis, hole.diameter_mm)
    rotation = {
        "x": (0.0, 90.0, 0.0),
        "y": (90.0, 0.0, 0.0),
        "z": (0.0, 0.0, 0.0),
    }[axis]
    cutter = Cylinder(hole.diameter_mm / 2.0, length, rotation=rotation).moved(Location(hole.position_mm))
    try:
        result = shape - cutter
        return result.clean()
    except Exception as exc:
        raise EditKernelError(f"Could not cut through-hole {hole.id}: {exc}") from exc


def _cardinal_axis(axis: tuple[float, float, float]) -> str:
    normalized = _normalized_axis(axis)
    candidates = {
        "x": (1.0, 0.0, 0.0),
        "y": (0.0, 1.0, 0.0),
        "z": (0.0, 0.0, 1.0),
    }
    for name, candidate in candidates.items():
        if all(abs(abs(normalized[index]) - candidate[index]) < 1e-6 for index in range(3)):
            return name
    raise EditKernelError("Only X, Y, and Z axis through-hole cuts are supported")


def _normalized_axis(axis: tuple[float, float, float]) -> tuple[float, float, float]:
    length = math.sqrt(sum(value * value for value in axis))
    if length == 0:
        raise EditKernelError("Hole axis must not be the zero vector")
    return (axis[0] / length, axis[1] / length, axis[2] / length)


def _through_length(shape: Any, axis: str, diameter_mm: float) -> float:
    bb = shape.bounding_box()
    span = {
        "x": float(bb.max.X - bb.min.X),
        "y": float(bb.max.Y - bb.min.Y),
        "z": float(bb.max.Z - bb.min.Z),
    }[axis]
    return span + max(20.0, diameter_mm * 4.0)
