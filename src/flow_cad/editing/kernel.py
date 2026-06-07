from __future__ import annotations

from pathlib import Path
from typing import Any

from flow_cad.editing.models import EditEntity
from flow_cad.step_io import normalize_step_file


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


def export_entity_step(entity: EditEntity, path: Path) -> Path:
    try:
        from build123d import export_step
    except Exception as exc:  # pragma: no cover - depends on local CAD install
        raise EditKernelError(
            "Edit STEP export requires build123d/OCP. Install project dependencies or configure the CAD environment."
        ) from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    ok = export_step(shape_for_entity(entity), path)
    if not ok:
        raise EditKernelError(f"STEP export failed for edit entity: {entity.id}")
    normalize_step_file(path)
    return path


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
