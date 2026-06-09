from __future__ import annotations

from typing import Any

from flow_cad.validation.contracts import (
    GeometryAuthority,
    ValidatorMetadata,
    ValidatorReport,
    error,
    info,
    report_with_issues,
)


PANEL_BASIC_METADATA = ValidatorMetadata(
    id="panel-basic",
    family="panel",
    description="Validate basic rectangular panel facts, features, and edge clearances.",
    mode="source",
    inputs=("active-cache", "step", "draft", "draft-transaction"),
    budget_ms=2000.0,
    tags=("fast", "source-loop", "panel"),
)


def _float(value: Any) -> float:
    return float(value)


def _distance(a: float, b: float) -> float:
    return abs(float(a) - float(b))


def _bbox_size(facts: dict[str, Any]) -> list[float] | None:
    if isinstance(facts.get("bounding_box"), dict):
        size = facts["bounding_box"].get("size")
        if isinstance(size, list | tuple) and len(size) == 3:
            return [float(value) for value in size]
    dimensions = facts.get("dimensions")
    if isinstance(dimensions, dict):
        try:
            return [float(dimensions["length"]), float(dimensions["width"]), float(dimensions["height"])]
        except KeyError:
            return None
    return None


def _feature_list(facts: dict[str, Any]) -> list[dict[str, Any]]:
    features = facts.get("feature_list")
    return [feature for feature in features if isinstance(feature, dict)] if isinstance(features, list) else []


def _hole_list(facts: dict[str, Any]) -> list[dict[str, Any]]:
    holes = facts.get("hole_centers")
    return [hole for hole in holes if isinstance(hole, dict)] if isinstance(holes, list) else []


def _feature_by_id(features: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(feature.get("id")): feature for feature in features if feature.get("id") is not None}


def _feature_xy(feature: dict[str, Any]) -> tuple[float | None, float | None]:
    params = feature.get("parameters")
    if isinstance(params, dict) and "x" in params and "y" in params:
        return float(params["x"]), float(params["y"])
    center = feature.get("center")
    if isinstance(center, list | tuple) and len(center) >= 2:
        return float(center[0]), float(center[1])
    return None, None


def validate_panel_facts(
    facts: dict[str, Any],
    *,
    metadata: ValidatorMetadata = PANEL_BASIC_METADATA,
    part_id: str | None = None,
    expected_dimensions_mm: tuple[float, float, float] | list[float] | None = None,
    expected_thickness_mm: float | None = None,
    expected_holes: list[dict[str, Any]] | None = None,
    expected_slots: list[dict[str, Any]] | None = None,
    keepout_rectangles: list[dict[str, Any]] | None = None,
    min_edge_distance_mm: float | None = 0.0,
    tolerance_mm: float = 0.1,
) -> ValidatorReport:
    """Validate rectangular panel facts from draft, cache, or STEP providers.

    Project-specific dimensions and hardware rules stay outside Flow CAD; this
    helper only applies the expectations that the caller passes in.
    """

    resolved_part_id = part_id or str(facts.get("part_id") or facts.get("id") or "")
    family = metadata.family
    authority = str(facts.get("geometry_authority") or GeometryAuthority.UNKNOWN)
    artifact_path = facts.get("artifact_relative_path") or facts.get("preview_step_relative_path") or facts.get("step_relative_path")
    size = _bbox_size(facts)
    features = _feature_list(facts)
    holes = _hole_list(facts)
    features_by_id = _feature_by_id(features)
    issues = []
    check_count = 1

    if size is None:
        issues.append(
            error(
                "panel_bbox_missing",
                "Panel facts are missing bounding-box dimensions.",
                part_id=resolved_part_id or None,
                family=family,
                artifact_path=str(artifact_path) if artifact_path else None,
                geometry_authority=authority,
                remediation="Provide draft facts, active-cache facts, or STEP-backed bounding-box facts.",
            )
        )
    else:
        if any(value <= 0 for value in size):
            issues.append(
                error(
                    "panel_bbox_nonpositive",
                    "Panel bounding-box dimensions must all be positive.",
                    part_id=resolved_part_id or None,
                    family=family,
                    expected="all dimensions > 0",
                    actual=size,
                    units="mm",
                    artifact_path=str(artifact_path) if artifact_path else None,
                    geometry_authority=authority,
                )
            )

    if expected_dimensions_mm is not None and size is not None:
        check_count += 1
        expected_size = [float(value) for value in expected_dimensions_mm]
        labels = ("length", "width", "height")
        for index, label in enumerate(labels):
            if _distance(size[index], expected_size[index]) > tolerance_mm:
                issues.append(
                    error(
                        f"panel_{label}_mismatch",
                        f"Panel {label} differs from expected size.",
                        part_id=resolved_part_id or None,
                        family=family,
                        expected=expected_size[index],
                        actual=size[index],
                        units="mm",
                        artifact_path=str(artifact_path) if artifact_path else None,
                        geometry_authority=authority,
                        remediation=f"Adjust the panel {label} or update the validator expectation.",
                    )
                )

    if expected_thickness_mm is not None and size is not None:
        check_count += 1
        if _distance(size[2], expected_thickness_mm) > tolerance_mm:
            issues.append(
                error(
                    "panel_thickness_mismatch",
                    "Panel thickness differs from expected value.",
                    part_id=resolved_part_id or None,
                    family=family,
                    expected=float(expected_thickness_mm),
                    actual=size[2],
                    units="mm",
                    artifact_path=str(artifact_path) if artifact_path else None,
                    geometry_authority=authority,
                    remediation="Adjust panel thickness or update the project-specific contract.",
                )
            )

    if min_edge_distance_mm is not None:
        for feature in features:
            check_count += 1
            edge_distance = feature.get("minimum_edge_distance_mm")
            if edge_distance is None:
                continue
            if float(edge_distance) + tolerance_mm < float(min_edge_distance_mm):
                issues.append(
                    error(
                        "panel_feature_edge_distance",
                        "Panel feature violates the minimum edge distance.",
                        part_id=resolved_part_id or None,
                        family=family,
                        expected=float(min_edge_distance_mm),
                        actual=float(edge_distance),
                        units="mm",
                        point_mm=feature.get("center"),
                        axis=feature.get("axis"),
                        feature_id=str(feature.get("id") or ""),
                        artifact_path=str(artifact_path) if artifact_path else None,
                        geometry_authority=authority,
                        remediation="Move the feature inward, shrink it, or update the project-specific minimum.",
                    )
                )

    for index, expected in enumerate(expected_holes or []):
        check_count += 1
        actual = None
        feature_id = expected.get("feature_id")
        if feature_id:
            actual = next((hole for hole in holes if str(hole.get("feature_id")) == str(feature_id)), None)
        elif index < len(holes):
            actual = holes[index]
        if actual is None:
            issues.append(
                error(
                    "panel_hole_missing",
                    "Expected panel hole is missing.",
                    part_id=resolved_part_id or None,
                    family=family,
                    expected=expected,
                    actual=None,
                    geometry_authority=authority,
                    remediation="Add the missing hole or update the panel validator expectation.",
                )
            )
            continue
        _compare_hole(
            issues,
            expected=expected,
            actual=actual,
            feature=features_by_id.get(str(actual.get("feature_id"))),
            part_id=resolved_part_id or None,
            family=family,
            authority=authority,
            artifact_path=str(artifact_path) if artifact_path else None,
            tolerance_mm=tolerance_mm,
        )

    for expected in expected_slots or []:
        check_count += 1
        face = str(expected.get("face") or "")
        expected_count = int(expected.get("count", 1))
        actual_slots = [
            feature
            for feature in features
            if feature.get("kind") == "slot" and (not face or str(feature.get("face")) == face)
        ]
        if len(actual_slots) != expected_count:
            issues.append(
                error(
                    "panel_slot_count_mismatch",
                    "Panel slot count differs from expected value.",
                    part_id=resolved_part_id or None,
                    family=family,
                    expected=expected_count,
                    actual=len(actual_slots),
                    units="count",
                    geometry_authority=authority,
                    remediation="Adjust the slot or louver pattern count.",
                )
            )

    for keepout in keepout_rectangles or []:
        check_count += 1
        _check_keepout(
            issues,
            features=features,
            keepout=keepout,
            part_id=resolved_part_id or None,
            family=family,
            authority=authority,
            artifact_path=str(artifact_path) if artifact_path else None,
        )

    if not issues and size is not None:
        issues.append(
            info(
                "panel_basic_passed",
                "Panel facts passed the requested basic checks.",
                part_id=resolved_part_id or None,
                family=family,
                expected="valid panel facts",
                actual={"bounding_box_size": size, "feature_count": len(features), "hole_count": len(holes)},
                units="mm",
                artifact_path=str(artifact_path) if artifact_path else None,
                geometry_authority=authority,
            )
        )

    return report_with_issues(
        metadata,
        issues,
        input_summary={
            "part_id": resolved_part_id,
            "geometry_authority": authority,
            "artifact_path": str(artifact_path) if artifact_path else None,
            "check_count": check_count,
            "feature_count": len(features),
            "hole_count": len(holes),
        },
    )


def _compare_hole(
    issues: list,
    *,
    expected: dict[str, Any],
    actual: dict[str, Any],
    feature: dict[str, Any] | None,
    part_id: str | None,
    family: str,
    authority: str,
    artifact_path: str | None,
    tolerance_mm: float,
) -> None:
    feature_id = str(actual.get("feature_id") or expected.get("feature_id") or "")
    if expected.get("face") is not None and str(actual.get("face")) != str(expected["face"]):
        issues.append(
            error(
                "panel_hole_face_mismatch",
                "Panel hole is on a different face than expected.",
                part_id=part_id,
                family=family,
                expected=str(expected["face"]),
                actual=str(actual.get("face")),
                point_mm=actual.get("center"),
                axis=actual.get("axis"),
                feature_id=feature_id,
                artifact_path=artifact_path,
                geometry_authority=authority,
            )
        )
    if expected.get("diameter") is not None and _distance(actual.get("diameter", 0.0), expected["diameter"]) > tolerance_mm:
        issues.append(
            error(
                "panel_hole_diameter_mismatch",
                "Panel hole diameter differs from expected value.",
                part_id=part_id,
                family=family,
                expected=float(expected["diameter"]),
                actual=float(actual.get("diameter", 0.0)),
                units="mm",
                point_mm=actual.get("center"),
                axis=actual.get("axis"),
                feature_id=feature_id,
                artifact_path=artifact_path,
                geometry_authority=authority,
            )
        )
    if feature is not None:
        actual_x, actual_y = _feature_xy(feature)
        for key, actual_value in (("x", actual_x), ("y", actual_y)):
            if expected.get(key) is None or actual_value is None:
                continue
            if _distance(actual_value, expected[key]) > tolerance_mm:
                issues.append(
                    error(
                        f"panel_hole_{key}_mismatch",
                        f"Panel hole {key} coordinate differs from expected value.",
                        part_id=part_id,
                        family=family,
                        expected=float(expected[key]),
                        actual=float(actual_value),
                        units="mm",
                        point_mm=actual.get("center"),
                        axis=actual.get("axis"),
                        feature_id=feature_id,
                        artifact_path=artifact_path,
                        geometry_authority=authority,
                    )
                )


def _check_keepout(
    issues: list,
    *,
    features: list[dict[str, Any]],
    keepout: dict[str, Any],
    part_id: str | None,
    family: str,
    authority: str,
    artifact_path: str | None,
) -> None:
    face = str(keepout.get("face") or "")
    x_min = _float(keepout.get("x_min", keepout.get("min_x", 0.0)))
    x_max = _float(keepout.get("x_max", keepout.get("max_x", 0.0)))
    y_min = _float(keepout.get("y_min", keepout.get("min_y", 0.0)))
    y_max = _float(keepout.get("y_max", keepout.get("max_y", 0.0)))
    label = str(keepout.get("id") or keepout.get("label") or "keepout")
    for feature in features:
        if face and str(feature.get("face")) != face:
            continue
        x_value, y_value = _feature_xy(feature)
        if x_value is None or y_value is None:
            continue
        if x_min <= x_value <= x_max and y_min <= y_value <= y_max:
            issues.append(
                error(
                    "panel_keepout_violation",
                    "Panel feature intersects a protected keep-out rectangle.",
                    part_id=part_id,
                    family=family,
                    expected={"keepout": label, "outside": [x_min, y_min, x_max, y_max]},
                    actual={"feature_id": feature.get("id"), "x": x_value, "y": y_value},
                    units="mm",
                    point_mm=feature.get("center"),
                    axis=feature.get("axis"),
                    feature_id=str(feature.get("id") or ""),
                    artifact_path=artifact_path,
                    geometry_authority=authority,
                    remediation="Move the feature or revise the project-specific keep-out contract.",
                )
            )
