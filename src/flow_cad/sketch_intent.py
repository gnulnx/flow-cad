from __future__ import annotations

"""Helpers to normalize rough sketch-like viewport annotations into a CAD recipe."""

from collections.abc import Mapping, Sequence
from typing import Any

Point = tuple[float, float]

DEFAULT_DIMENSIONS = {"length": 120.0, "width": 65.0, "thickness": 10.0}
MIN_DIMENSION = 1e-9
ROUND_TO = 6


def build_sketch_intent_recipe(
    annotations: Sequence[Mapping[str, Any]] | None,
    requested_dimensions: Mapping[str, Any] | None = None,
    options: Mapping[str, Any] | None = None,
    *,
    length: float | None = None,
    width: float | None = None,
    thickness: float | None = None,
    symmetry: str | bool | None = None,
    part_id: str = "sketch_plate",
) -> dict[str, Any]:
    """Convert rough sketch annotations into a deterministic footprint recipe.

    The result is intentionally intent-focused (not exact CAD). It extracts one
    outer freehand outline and separates small marks as hole markers.
    """

    if symmetry is None and options:
        option_symmetry = options.get("symmetry")
        if option_symmetry is not None:
            symmetry = option_symmetry

    annotations_list = list(annotations or [])
    dimensions = _coerce_dimensions(requested_dimensions, length=length, width=width, thickness=thickness)

    requested_length = dimensions["length"]
    requested_width = dimensions["width"]
    requested_thickness = dimensions["thickness"]

    warnings: list[str] = []
    assumptions: list[str] = [
        "Sketch annotations are interpreted as design intent, not exact CAD topology.",
        "Footprint geometry is normalized from viewport evidence and may be approximate.",
    ]

    freehand_annotations: list[tuple[int, list[Point]]] = []
    circle_annotations: list[tuple[int, Point, float]] = []

    for index, annotation in enumerate(annotations_list):
        if not isinstance(annotation, Mapping):
            continue
        kind = str(annotation.get("kind") or "").strip().lower()
        if kind == "note":
            continue
        if kind == "circle":
            circle = _parse_circle(annotation)
            if circle is not None:
                circle_annotations.append((index, *circle))
            else:
                warnings.append(f"Skipped malformed circle annotation at index {index}.")
            continue
        if kind == "freehand":
            points = _parse_freehand(annotation)
            if points:
                freehand_annotations.append((index, points))
            else:
                warnings.append(f"Skipped malformed freehand annotation at index {index}.")

    outline_index: int | None = None
    outline_points: list[Point] = []
    if freehand_annotations:
        outline_index, outline_points = _largest_freehand(freehand_annotations)
        assumptions.append(
            f"Selected freehand annotation {outline_index} as outer outline (largest by polygon area)."
        )

    # Collect a fallback span for mapping secondary markers and shape hints.
    fallback_bounds = _collect_normalized_bounds(freehand_annotations)
    if outline_points:
        outline_bounds = _bounds(outline_points)
    else:
        if fallback_bounds is None:
            outline_bounds = (0.0, 1.0, 0.0, 1.0)
        else:
            outline_bounds = fallback_bounds
            warnings.append(
                "No freehand outline was usable; using non-outline annotation bounds for marker mapping."
            )

    map_scale_x, map_scale_y = _scale_factors(outline_bounds, requested_length, requested_width)
    if map_scale_x is None or map_scale_y is None:
        map_scale_x = requested_length
        map_scale_y = requested_width
        warnings.append("Degenerate outline span detected; used 1:1 normalized fallback scaling.")

    normalized_point = _make_normalized_mapper(outline_bounds, requested_length, requested_width)

    if outline_points:
        scaled_outline = [normalized_point(point) for point in outline_points]
        if _is_symmetry_enabled(symmetry):
            scaled_outline = _apply_y_symmetry_cleanup(scaled_outline)
            assumptions.append("Applied optional y-axis symmetry cleanup to the outline.")
        outline_points_mm = _ensure_closed_polygon([_round_point(point) for point in scaled_outline])
    else:
        # Conservative fallback when there is no usable freehand outline.
        outline_points_mm = [
            _round_point((-requested_length / 2.0, -requested_width / 2.0)),
            _round_point((requested_length / 2.0, -requested_width / 2.0)),
            _round_point((requested_length / 2.0, requested_width / 2.0)),
            _round_point((-requested_length / 2.0, requested_width / 2.0)),
            _round_point((-requested_length / 2.0, -requested_width / 2.0)),
        ]
        warnings.append("No usable freehand outline; generated rectangle fallback from requested dimensions.")

    holes: list[dict[str, Any]] = []

    if outline_points:
        # classify small circles as hole marks
        for idx, center, radius in circle_annotations:
            if _is_small_circle(radius, outline_points):
                hx, hy = normalized_point(center)
                holes.append(
                    {
                        "source_annotation_index": idx,
                        "source_kind": "circle",
                        "center": _round_point((hx, hy)),
                        "radius": _round(_radius_to_mm(radius, map_scale_x, map_scale_y)),
                    }
                )
        # classify small freehand annotations as hole marks
        for idx, points in freehand_annotations:
            if idx == outline_index:
                continue
            if _is_small_freehand_for_hole(points, outline_points):
                cx, cy = _centroid(points)
                hx, hy = normalized_point((cx, cy))
                holes.append(
                    {
                        "source_annotation_index": idx,
                        "source_kind": "freehand",
                        "center": _round_point((hx, hy)),
                        "radius": _round(_freehand_radius(points, map_scale_x, map_scale_y)),
                    }
                )

        if circle_annotations and not holes:
            warnings.append(
                "Circle annotations were not classified as holes; they were too large for rough-hole heuristics."
            )
    else:
        # No outer outline means no reliable normalization source; map markers directly.
        for idx, points in freehand_annotations:
            if _is_small_freehand(points):
                cx, cy = _centroid(points)
                hx, hy = normalized_point((cx, cy))
                holes.append(
                    {
                        "source_annotation_index": idx,
                        "source_kind": "freehand",
                        "center": _round_point((hx, hy)),
                        "radius": _round(_freehand_radius(points, map_scale_x, map_scale_y)),
                    }
                )
        for idx, center, radius in circle_annotations:
            hx, hy = normalized_point(center)
            holes.append(
                {
                    "source_annotation_index": idx,
                    "source_kind": "circle",
                    "center": _round_point((hx, hy)),
                    "radius": _round(_radius_to_mm(radius, map_scale_x, map_scale_y)),
                }
            )

    return {
        "part_id": part_id,
        "length": requested_length,
        "width": requested_width,
        "thickness": requested_thickness,
        "outline": {
            "kind": "closed_polygon_mm",
            "points": [list(point) for point in outline_points_mm],
        },
        "holes": holes,
        "assumptions": assumptions,
        "warnings": warnings,
    }


def build_sketch_footprint_recipe(
    annotations: Sequence[Mapping[str, Any]] | None,
    length: float,
    width: float,
    thickness: float,
    *,
    symmetry: str | bool | None = None,
    part_id: str = "sketch_plate",
) -> dict[str, Any]:
    """Compatibility wrapper for scalar dimension inputs."""

    return build_sketch_intent_recipe(
        annotations,
        {"length": length, "width": width, "thickness": thickness},
        symmetry=symmetry,
        part_id=part_id,
    )


def build_footprint_from_annotations(
    annotations: Sequence[Mapping[str, Any]] | None,
    *,
    dimensions: Mapping[str, Any],
    symmetry: str | bool | None = None,
    part_id: str = "sketch_plate",
) -> dict[str, Any]:
    """Compatibility wrapper for callers that prefer an options dictionary."""

    return build_sketch_intent_recipe(
        annotations,
        dimensions,
        symmetry=symmetry,
        part_id=part_id,
    )


def _coerce_dimensions(
    requested_dimensions: Mapping[str, Any] | None,
    *,
    length: float | None = None,
    width: float | None = None,
    thickness: float | None = None,
) -> dict[str, float]:
    parsed = dict(DEFAULT_DIMENSIONS)
    source = dict(requested_dimensions or {})
    if isinstance(requested_dimensions, Mapping):
        if _coerce_positive_float(source.get("length")) is not None:
            parsed["length"] = float(source["length"])  # type: ignore[arg-type]
        if _coerce_positive_float(source.get("width")) is not None:
            parsed["width"] = float(source["width"])  # type: ignore[arg-type]
        if _coerce_positive_float(source.get("thickness")) is not None:
            parsed["thickness"] = float(source["thickness"])  # type: ignore[arg-type]
    if _coerce_positive_float(length) is not None:
        parsed["length"] = float(length)  # type: ignore[arg-type]
    if _coerce_positive_float(width) is not None:
        parsed["width"] = float(width)  # type: ignore[arg-type]
    if _coerce_positive_float(thickness) is not None:
        parsed["thickness"] = float(thickness)  # type: ignore[arg-type]
    return parsed


def _coerce_positive_float(value: Any) -> float | None:
    try:
        value_float = float(value)
    except (TypeError, ValueError):
        return None
    if value_float <= 0:
        return None
    return value_float


def _parse_freehand(annotation: Mapping[str, Any]) -> list[Point] | None:
    raw_points = annotation.get("points")
    if not isinstance(raw_points, list):
        return None
    points: list[Point] = []
    for point in raw_points:
        if not isinstance(point, Mapping):
            continue
        x = _coerce_normalized(point.get("x"))
        y = _coerce_normalized(point.get("y"))
        if x is None or y is None:
            continue
        points.append((x, y))
    if len(points) < 3:
        return None
    return _remove_consecutive_duplicates(_ensure_closed_polygon(points)[:-1])


def _parse_circle(annotation: Mapping[str, Any]) -> tuple[Point, float] | None:
    x = _coerce_normalized(annotation.get("x"))
    y = _coerce_normalized(annotation.get("y"))
    radius = _coerce_normalized(annotation.get("radius"), allow_zero=False)
    if x is None or y is None or radius is None:
        return None
    return (x, y), radius


def _coerce_normalized(value: Any, allow_zero: bool = True) -> float | None:
    try:
        value_float = float(value)
    except (TypeError, ValueError):
        return None
    if value_float < 0 or value_float > 1:
        value_float = min(1.0, max(0.0, value_float))
    if allow_zero and value_float >= 0:
        return value_float
    if value_float > 0:
        return value_float
    return None

def _ensure_closed_polygon(points: list[Point]) -> list[Point]:
    if not points:
        return []
    if points[0] == points[-1]:
        return points
    return points + [points[0]]


def _remove_consecutive_duplicates(points: list[Point], eps: float = 1e-9) -> list[Point]:
    if not points:
        return []
    deduped: list[Point] = [points[0]]
    for point in points[1:]:
        x, y = point
        px, py = deduped[-1]
        if abs(x - px) <= eps and abs(y - py) <= eps:
            continue
        deduped.append((x, y))
    return deduped


def _polygon_area(points: list[Point]) -> float:
    if len(points) < 3:
        return 0.0
    closed = _ensure_closed_polygon(points)
    area = 0.0
    for (x1, y1), (x2, y2) in zip(closed[:-1], closed[1:]):
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0


def _largest_freehand(
    candidates: list[tuple[int, list[Point]]],
) -> tuple[int, list[Point]]:
    def metric(item: tuple[int, list[Point]]) -> float:
        _, points = item
        area = abs(_polygon_area(points))
        b = _bounds(points)
        bbox_area = max(0.0, _span(b)[0] * _span(b)[1])
        return max(area, bbox_area)

    selected = max(candidates, key=metric)
    return selected


def _bounds(points: list[Point]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), max(xs), min(ys), max(ys)


def _span(bounds: tuple[float, float, float, float]) -> tuple[float, float]:
    min_x, max_x, min_y, max_y = bounds
    return max_x - min_x, max_y - min_y


def _collect_normalized_bounds(
    freehand_candidates: list[tuple[int, list[Point]]],
) -> tuple[float, float, float, float] | None:
    all_points: list[Point] = []
    for _, points in freehand_candidates:
        all_points.extend(points)
    if not all_points:
        return None
    xs = [point[0] for point in all_points]
    ys = [point[1] for point in all_points]
    return min(xs), max(xs), min(ys), max(ys)


def _scale_factors(
    bounds: tuple[float, float, float, float],
    requested_length: float,
    requested_width: float,
) -> tuple[float | None, float | None]:
    min_x, max_x, min_y, max_y = bounds
    span_x = max(max_x - min_x, MIN_DIMENSION)
    span_y = max(max_y - min_y, MIN_DIMENSION)
    return requested_length / span_x, requested_width / span_y


def _make_normalized_mapper(
    bounds: tuple[float, float, float, float],
    requested_length: float,
    requested_width: float,
) -> Any:
    min_x, max_x, min_y, max_y = bounds
    span_x, span_y = _span((min_x, max_x, min_y, max_y))
    span_x = max(span_x, MIN_DIMENSION)
    span_y = max(span_y, MIN_DIMENSION)

    def map_point(point: Point) -> Point:
        x, y = point
        mm_x = ((x - min_x) / span_x) * requested_length - requested_length / 2.0
        mm_y = ((y - min_y) / span_y) * requested_width - requested_width / 2.0
        return mm_x, mm_y

    return map_point


def _radius_to_mm(radius_norm: float, scale_x: float | None, scale_y: float | None) -> float:
    if scale_x is None or scale_y is None:
        return radius_norm
    return radius_norm * (abs(scale_x) + abs(scale_y)) / 2.0


def _freehand_radius(points: list[Point], scale_x: float | None, scale_y: float | None) -> float:
    min_x, max_x, min_y, max_y = _bounds(points)
    span_x = max(max_x - min_x, MIN_DIMENSION)
    span_y = max(max_y - min_y, MIN_DIMENSION)
    local_radius = max(span_x, span_y) / 2.0
    if scale_x is None or scale_y is None:
        return local_radius
    return local_radius * (abs(scale_x) + abs(scale_y)) / 2.0


def _centroid(points: list[Point]) -> Point:
    if not points:
        return (0.0, 0.0)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def _is_symmetry_enabled(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower().replace("_", "").replace("-", "")
    return normalized in {"y", "ymm", "ysym", "symmetryy", "symmetryon", "mirror", "mirrory"}


def _is_small_circle(radius_norm: float, outline_points: list[Point]) -> bool:
    min_x, max_x, min_y, max_y = _bounds(outline_points)
    span_x = max(max_x - min_x, MIN_DIMENSION)
    span_y = max(max_y - min_y, MIN_DIMENSION)
    return radius_norm <= 0.12 and radius_norm <= max(span_x, span_y) * 0.45


def _is_small_freehand_for_hole(points: list[Point], outline_points: list[Point]) -> bool:
    outline_area = abs(_polygon_area(outline_points))
    outline_bounds = _bounds(outline_points)
    outline_span_x, outline_span_y = _span(outline_bounds)
    candidate_area = abs(_polygon_area(points))
    candidate_bounds = _bounds(points)
    cand_span_x, cand_span_y = _span(candidate_bounds)
    if outline_span_x <= MIN_DIMENSION or outline_span_y <= MIN_DIMENSION:
        return False
    if len(points) < 3:
        return False
    return (
        candidate_area <= max(outline_area * 0.2, 0.003)
        and cand_span_x <= outline_span_x * 0.6
        and cand_span_y <= outline_span_y * 0.6
    )


def _is_small_freehand(points: list[Point]) -> bool:
    span_x, span_y = _span(_bounds(points))
    if len(points) < 4 or span_x <= 0.0 or span_y <= 0.0:
        return False
    area = abs(_polygon_area(points))
    return area <= 0.06 and span_x <= 0.35 and span_y <= 0.35


def _apply_y_symmetry_cleanup(points: list[Point]) -> list[Point]:
    if not points:
        return []
    base = _remove_consecutive_duplicates(points[:-1] if points[0] == points[-1] else points)
    if len(base) < 2:
        return points
    folded = [(abs(x), y) for x, y in base]
    mirrored = [(-x, y) for x, y in reversed(folded)]
    merged = _remove_consecutive_duplicates(folded + mirrored)
    if merged and merged[0] != merged[-1]:
        merged.append(merged[0])
    return merged


def _round_point(point: Point) -> Point:
    return _round(point[0]), _round(point[1])


def _round(value: float) -> float:
    return round(float(value), ROUND_TO)
