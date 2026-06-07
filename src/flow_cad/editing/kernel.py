from __future__ import annotations

from typing import Any

from flow_cad.editing.models import EditEntity


class EditKernelError(RuntimeError):
    pass


def shape_for_entity(entity: EditEntity) -> Any:
    if entity.kind != "primitive_box":
        raise EditKernelError(f"Unsupported edit entity kind: {entity.kind}")
    try:
        from build123d import Box, Location
    except Exception as exc:  # pragma: no cover - depends on local CAD install
        raise EditKernelError(
            "Edit kernel operations require build123d/OCP. Install project dependencies or configure the CAD environment."
        ) from exc

    shape = Box(*entity.size_mm)
    return shape.moved(Location(entity.transform.translation_mm, entity.transform.rotation_deg))


def bounding_box_payload(entity: EditEntity) -> dict[str, Any]:
    shape = shape_for_entity(entity)
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
