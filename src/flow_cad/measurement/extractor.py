"""Lazy STEP-topology extraction for exact measurement targets."""

from __future__ import annotations

from pathlib import Path
from typing import Any


EXACT_FEATURE_SCHEMA_VERSION = 1
EXACT_FEATURE_EXTRACTOR_VERSION = 1


class ExactFeatureExtractionError(RuntimeError):
    """STEP topology could not be read by the configured CAD kernel."""


def extract_step_features(
    step_path: Path,
    *,
    part_uuid: str,
    artifact_revision: str,
) -> dict[str, Any]:
    """Return deterministic, exact snap and edge-length facts from STEP.

    ``build123d`` and OCP are intentionally imported inside this worker-only
    function.  Inventory, cache lookups, and API construction therefore stay
    geometry-free.
    """

    try:
        from build123d import import_step
    except Exception as exc:  # pragma: no cover - environment dependent
        raise ExactFeatureExtractionError(
            "exact STEP extraction requires build123d/OCP in the Flow CAD runtime"
        ) from exc

    try:
        shape = import_step(step_path)
        vertices = shape.vertices()
        edges = shape.edges()
    except Exception as exc:
        raise ExactFeatureExtractionError(
            f"could not read STEP topology from {step_path.name}: {exc}"
        ) from exc

    vertex_points = sorted({_point(vertex.center()) for vertex in vertices})
    line_edges: list[dict[str, Any]] = []
    circles: list[dict[str, Any]] = []
    unsupported_edge_count = 0

    for edge in edges:
        try:
            geometry_type = _geometry_type(edge)
            length_mm = float(edge.length)
            if geometry_type == "line":
                start_mm = _point(edge.position_at(0.0))
                end_mm = _point(edge.position_at(1.0))
                start_mm, end_mm = sorted((start_mm, end_mm))
                line_edges.append(
                    {
                        "start_mm": start_mm,
                        "end_mm": end_mm,
                        "midpoint_mm": _midpoint(start_mm, end_mm),
                        "length_mm": length_mm,
                    }
                )
            elif geometry_type == "circle":
                circles.append(
                    {
                        "center_mm": _point(edge.arc_center),
                        "radius_mm": float(edge.radius),
                        "length_mm": length_mm,
                    }
                )
            else:
                unsupported_edge_count += 1
        except Exception:
            unsupported_edge_count += 1

    line_edges.sort(key=_line_sort_key)
    circles.sort(key=_circle_sort_key)
    features: list[dict[str, Any]] = []

    for index, point_mm in enumerate(vertex_points):
        features.append(
            _exact_feature(
                feature_id=f"vertex:{index}",
                kind="vertex",
                point_mm=point_mm,
            )
        )

    for index, edge in enumerate(line_edges):
        edge_id = f"line_edge:{index}"
        features.append(
            _exact_feature(
                feature_id=edge_id,
                kind="line_edge",
                start_mm=edge["start_mm"],
                end_mm=edge["end_mm"],
                midpoint_mm=edge["midpoint_mm"],
                length_mm=edge["length_mm"],
            )
        )
        features.append(
            _exact_feature(
                feature_id=f"edge_midpoint:{index}",
                kind="edge_midpoint",
                point_mm=edge["midpoint_mm"],
                edge_feature_id=edge_id,
            )
        )

    for index, circle in enumerate(circles):
        features.append(
            _exact_feature(
                feature_id=f"circle_center:{index}",
                kind="circle_center",
                point_mm=circle["center_mm"],
                radius_mm=circle["radius_mm"],
                edge_length_mm=circle["length_mm"],
            )
        )

    warnings = []
    if unsupported_edge_count:
        warnings.append(
            f"{unsupported_edge_count} non-line/non-circle edges are not first-release snap targets"
        )
    if not features:
        warnings.append("STEP topology contains no supported exact snap targets")

    return {
        "schema_version": EXACT_FEATURE_SCHEMA_VERSION,
        "extractor_version": EXACT_FEATURE_EXTRACTOR_VERSION,
        "status": "ready",
        "part_uuid": part_uuid,
        "artifact_revision": artifact_revision,
        "geometry_authority": "step_kernel",
        "quality": "exact",
        "units": "mm",
        "features": features,
        "feature_counts": {
            "vertex": len(vertex_points),
            "line_edge": len(line_edges),
            "edge_midpoint": len(line_edges),
            "circle_center": len(circles),
        },
        "warnings": warnings,
    }


def _geometry_type(edge: Any) -> str:
    value = getattr(edge, "geom_type", "")
    return str(getattr(value, "name", value)).lower()


def _point(value: Any) -> tuple[float, float, float]:
    return (_clean_float(value.X), _clean_float(value.Y), _clean_float(value.Z))


def _clean_float(value: float) -> float:
    number = float(value)
    return 0.0 if abs(number) < 1e-12 else number


def _midpoint(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
) -> tuple[float, float, float]:
    return tuple((left + right) / 2.0 for left, right in zip(start, end, strict=True))


def _line_sort_key(edge: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _rounded_point(edge["start_mm"]),
        _rounded_point(edge["end_mm"]),
        round(float(edge["length_mm"]), 12),
    )


def _circle_sort_key(circle: dict[str, Any]) -> tuple[Any, ...]:
    return (
        _rounded_point(circle["center_mm"]),
        round(float(circle["radius_mm"]), 12),
        round(float(circle["length_mm"]), 12),
    )


def _rounded_point(point: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(round(float(value), 12) for value in point)


def _exact_feature(*, feature_id: str, kind: str, **facts: Any) -> dict[str, Any]:
    return {
        "id": feature_id,
        "kind": kind,
        "source": "step_topology",
        "quality": "exact",
        **facts,
    }
