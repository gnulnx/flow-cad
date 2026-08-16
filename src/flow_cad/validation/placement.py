from __future__ import annotations

from typing import Any

from flow_cad.validation.contracts import GeometryAuthority, ValidatorIssue, error, info


def placement_issues(
    placements: list[dict[str, Any]],
    *,
    part_id: str,
    expected_translation: tuple[float, float, float] | list[float] | None = None,
    expected_rotation: tuple[float, float, float] | list[float] | None = None,
    expected_visible: bool | None = None,
    expected_neighbor_ids: list[str] | tuple[str, ...] = (),
    tolerance_mm: float = 0.1,
    tolerance_deg: float = 0.1,
) -> list[ValidatorIssue]:
    """Generic placement checks for project-local validators."""

    issues: list[ValidatorIssue] = []
    matching = [placement for placement in placements if placement.get("part_id") == part_id]
    if not matching:
        return [
            error(
                "placement_missing",
                f"Expected placement for part {part_id!r} is missing.",
                part_id=part_id,
                expected="at least one placement",
                actual=0,
                units="count",
                geometry_authority=GeometryAuthority.UNKNOWN,
                remediation="Add or correct this part in get_assembly_placements().",
            )
        ]

    primary = matching[0]
    if expected_translation is not None:
        expected = [float(value) for value in expected_translation]
        actual = [float(value) for value in primary.get("location", (0.0, 0.0, 0.0))]
        deltas = [actual[index] - expected[index] for index in range(3)]
        if any(abs(delta) > tolerance_mm for delta in deltas):
            issues.append(
                error(
                    "placement_translation_mismatch",
                    "Part placement translation differs from expected value.",
                    part_id=part_id,
                    expected=expected,
                    actual=actual,
                    units="mm",
                    point_mm=actual,
                    geometry_authority=GeometryAuthority.UNKNOWN,
                    remediation="Adjust the project assembly placement translation.",
                )
            )

    if expected_rotation is not None:
        expected = [float(value) for value in expected_rotation]
        actual = [float(value) for value in primary.get("rotation", (0.0, 0.0, 0.0))]
        deltas = [actual[index] - expected[index] for index in range(3)]
        if any(abs(delta) > tolerance_deg for delta in deltas):
            issues.append(
                error(
                    "placement_rotation_mismatch",
                    "Part placement rotation differs from expected value.",
                    part_id=part_id,
                    expected=expected,
                    actual=actual,
                    units="deg",
                    geometry_authority=GeometryAuthority.UNKNOWN,
                    remediation="Adjust the project assembly placement rotation.",
                )
            )

    if expected_visible is not None:
        actual_visible = bool(primary.get("default_visible", True))
        if actual_visible is not bool(expected_visible):
            issues.append(
                error(
                    "placement_visibility_mismatch",
                    "Part default-review visibility differs from expected value.",
                    part_id=part_id,
                    expected=bool(expected_visible),
                    actual=actual_visible,
                    geometry_authority=GeometryAuthority.UNKNOWN,
                    remediation="Update placement metadata or the project validator expectation.",
                )
            )

    actual_ids = {str(placement.get("part_id")) for placement in placements}
    for neighbor_id in expected_neighbor_ids:
        if str(neighbor_id) not in actual_ids:
            issues.append(
                error(
                    "placement_neighbor_missing",
                    f"Expected neighboring part {neighbor_id!r} is not present in placement facts.",
                    part_id=part_id,
                    expected=str(neighbor_id),
                    actual=sorted(actual_ids),
                    geometry_authority=GeometryAuthority.UNKNOWN,
                    remediation="Check the assembly id, include_references flag, or expected neighbor list.",
                )
            )

    if not issues:
        issues.append(
            info(
                "placement_basic_passed",
                "Placement facts passed the requested checks.",
                part_id=part_id,
                expected="valid placement facts",
                actual={"placement_count": len(matching)},
                geometry_authority=GeometryAuthority.UNKNOWN,
            )
        )
    return issues
