from __future__ import annotations

import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


VALIDATOR_REPORT_SCHEMA_VERSION = 1


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class ValidatorMode(StrEnum):
    DRAFT = "draft"
    SOURCE = "source"
    CACHE = "cache"
    VIEWER = "viewer"
    GATE = "gate"


class GeometryAuthority(StrEnum):
    STEP = "step"
    DRAFT = "draft"
    CACHE = "cache"
    MESH = "mesh"
    UNKNOWN = "unknown"


def _string_tuple(values: Iterable[Any] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    return tuple(str(value) for value in values)


def _json_value(value: Any) -> Any:
    if isinstance(value, os.PathLike):
        return str(value)
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class ValidatorMetadata:
    """Stable focused-validator identity and execution contract."""

    id: str
    family: str
    description: str
    mode: str = ValidatorMode.SOURCE
    inputs: tuple[str, ...] = ()
    budget_ms: float = 2000.0
    tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "family": self.family,
            "description": self.description,
            "mode": str(self.mode),
            "inputs": list(self.inputs),
            "budget_ms": float(self.budget_ms),
            "tags": list(self.tags),
        }

    @classmethod
    def from_any(cls, value: Any, *, default_id: str) -> ValidatorMetadata:
        if isinstance(value, ValidatorMetadata):
            return value
        if isinstance(value, dict):
            return cls(
                id=str(value.get("id") or default_id),
                family=str(value.get("family") or "project"),
                description=str(value.get("description") or "Project focused validator."),
                mode=str(value.get("mode") or ValidatorMode.SOURCE),
                inputs=_string_tuple(value.get("inputs") or ()),
                budget_ms=float(value.get("budget_ms") or 2000.0),
                tags=_string_tuple(value.get("tags") or ()),
            )
        return cls(
            id=default_id,
            family="project",
            description="Project focused validator.",
            mode=ValidatorMode.SOURCE,
            inputs=("project",),
            budget_ms=2000.0,
            tags=("project",),
        )


@dataclass(frozen=True)
class ValidatorIssue:
    """Machine-readable validator issue.

    The fields mirror the public schema in docs/FocusedValidators.md so callers
    can locate geometry failures without parsing prose.
    """

    severity: str
    check_id: str
    message: str
    part_id: str | None = None
    family: str | None = None
    expected: Any = None
    actual: Any = None
    units: str | None = None
    point_mm: tuple[float, float, float] | list[float] | None = None
    axis: tuple[float, float, float] | list[float] | None = None
    feature_id: str | None = None
    artifact_path: str | None = None
    geometry_authority: str = GeometryAuthority.UNKNOWN
    remediation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": str(self.severity),
            "check_id": self.check_id,
            "part_id": self.part_id,
            "family": self.family,
            "message": self.message,
            "expected": _json_value(self.expected),
            "actual": _json_value(self.actual),
            "units": self.units,
            "point_mm": list(self.point_mm) if self.point_mm is not None else None,
            "axis": list(self.axis) if self.axis is not None else None,
            "feature_id": self.feature_id,
            "artifact_path": self.artifact_path,
            "geometry_authority": str(self.geometry_authority),
            "remediation": self.remediation,
        }

    @classmethod
    def from_any(
        cls,
        value: Any,
        *,
        default_check_id: str,
        default_part_id: str | None = None,
        default_family: str | None = None,
        default_geometry_authority: str = GeometryAuthority.UNKNOWN,
    ) -> ValidatorIssue:
        if isinstance(value, ValidatorIssue):
            return value
        if isinstance(value, dict):
            return cls(
                severity=str(value.get("severity") or value.get("level") or Severity.ERROR),
                check_id=str(value.get("check_id") or default_check_id),
                message=str(value.get("message") or value),
                part_id=str(value["part_id"]) if value.get("part_id") is not None else default_part_id,
                family=str(value["family"]) if value.get("family") is not None else default_family,
                expected=value.get("expected"),
                actual=value.get("actual"),
                units=str(value["units"]) if value.get("units") is not None else None,
                point_mm=value.get("point_mm"),
                axis=value.get("axis"),
                feature_id=str(value["feature_id"]) if value.get("feature_id") is not None else None,
                artifact_path=str(value["artifact_path"]) if value.get("artifact_path") is not None else None,
                geometry_authority=str(value.get("geometry_authority") or default_geometry_authority),
                remediation=str(value["remediation"]) if value.get("remediation") is not None else None,
            )
        return cls(
            severity=Severity.ERROR,
            check_id=default_check_id,
            message=str(value),
            part_id=default_part_id,
            family=default_family,
            geometry_authority=default_geometry_authority,
        )


@dataclass(frozen=True)
class ValidatorReport:
    metadata: ValidatorMetadata
    elapsed_ms: float = 0.0
    input_summary: dict[str, Any] = field(default_factory=dict)
    issues: tuple[ValidatorIssue, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if str(issue.severity) == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if str(issue.severity) == Severity.WARNING)

    @property
    def info_count(self) -> int:
        return sum(1 for issue in self.issues if str(issue.severity) == Severity.INFO)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def ok(self) -> bool:
        return self.error_count == 0

    @property
    def geometry_authority(self) -> str:
        value = self.input_summary.get("geometry_authority")
        if value:
            return str(value)
        for issue in self.issues:
            if issue.geometry_authority and str(issue.geometry_authority) != GeometryAuthority.UNKNOWN:
                return str(issue.geometry_authority)
        return str(GeometryAuthority.UNKNOWN)

    @property
    def over_budget(self) -> bool:
        return float(self.elapsed_ms) > float(self.metadata.budget_ms)

    def with_elapsed(self, elapsed_ms: float) -> ValidatorReport:
        return ValidatorReport(
            metadata=self.metadata,
            elapsed_ms=elapsed_ms,
            input_summary=dict(self.input_summary),
            issues=self.issues,
            warnings=self.warnings,
        )

    def to_dict(self) -> dict[str, Any]:
        issue_counts = {
            "error": self.error_count,
            "warning": self.warning_count,
            "info": self.info_count,
            "total": self.issue_count,
        }
        return {
            "schema_version": VALIDATOR_REPORT_SCHEMA_VERSION,
            "ok": self.ok,
            "status": "ok" if self.ok else "failed",
            "metadata": self.metadata.to_dict(),
            "elapsed_ms": float(self.elapsed_ms),
            "input_summary": _json_value(self.input_summary),
            "issue_counts": issue_counts,
            "issues": [issue.to_dict() for issue in self.issues],
            "warnings": list(self.warnings),
        }

    def profile_metadata(self, *, part_id: str | None = None, draft_token: str | None = None) -> dict[str, Any]:
        metadata = self.metadata.to_dict()
        metadata.update(
            {
                "validator_id": self.metadata.id,
                "part_id": part_id or "",
                "draft_token": draft_token or "",
                "check_count": max(1, int(self.input_summary.get("check_count") or self.issue_count or 1)),
                "issue_count": self.issue_count,
                "error_count": self.error_count,
                "warning_count": self.warning_count,
                "geometry_authority": self.geometry_authority,
                "over_budget": self.over_budget,
            }
        )
        return metadata


def make_issue(
    severity: str | Severity,
    check_id: str,
    message: str,
    **kwargs: Any,
) -> ValidatorIssue:
    return ValidatorIssue(severity=str(severity), check_id=check_id, message=message, **kwargs)


def error(check_id: str, message: str, **kwargs: Any) -> ValidatorIssue:
    return make_issue(Severity.ERROR, check_id, message, **kwargs)


def warning(check_id: str, message: str, **kwargs: Any) -> ValidatorIssue:
    return make_issue(Severity.WARNING, check_id, message, **kwargs)


def info(check_id: str, message: str, **kwargs: Any) -> ValidatorIssue:
    return make_issue(Severity.INFO, check_id, message, **kwargs)


def success_report(
    metadata: ValidatorMetadata,
    *,
    elapsed_ms: float = 0.0,
    input_summary: dict[str, Any] | None = None,
    warnings: Iterable[str] = (),
) -> ValidatorReport:
    return ValidatorReport(
        metadata=metadata,
        elapsed_ms=elapsed_ms,
        input_summary=dict(input_summary or {}),
        issues=(),
        warnings=tuple(str(item) for item in warnings),
    )


def report_with_issues(
    metadata: ValidatorMetadata,
    issues: Iterable[ValidatorIssue],
    *,
    elapsed_ms: float = 0.0,
    input_summary: dict[str, Any] | None = None,
    warnings: Iterable[str] = (),
) -> ValidatorReport:
    return ValidatorReport(
        metadata=metadata,
        elapsed_ms=elapsed_ms,
        input_summary=dict(input_summary or {}),
        issues=tuple(issues),
        warnings=tuple(str(item) for item in warnings),
    )


def coerce_validator_result(
    result: Any,
    metadata: ValidatorMetadata,
    *,
    elapsed_ms: float = 0.0,
    input_summary: dict[str, Any] | None = None,
    default_part_id: str | None = None,
    default_family: str | None = None,
    default_geometry_authority: str = GeometryAuthority.UNKNOWN,
) -> ValidatorReport:
    if isinstance(result, ValidatorReport):
        return result.with_elapsed(elapsed_ms) if result.elapsed_ms == 0 else result

    if result is None:
        return success_report(metadata, elapsed_ms=elapsed_ms, input_summary=input_summary)

    if isinstance(result, str):
        if not result.strip():
            return success_report(metadata, elapsed_ms=elapsed_ms, input_summary=input_summary)
        return report_with_issues(
            metadata,
            [
                error(
                    "legacy_string_result",
                    result.strip(),
                    part_id=default_part_id,
                    family=default_family,
                    geometry_authority=default_geometry_authority,
                )
            ],
            elapsed_ms=elapsed_ms,
            input_summary=input_summary,
        )

    if isinstance(result, dict):
        issues_source = result.get("errors") or result.get("issues") or result.get("failures") or ()
        if result.get("ok") is False and not issues_source:
            issues_source = [{"message": "Validator reported ok=false"}]
        issues = [
            ValidatorIssue.from_any(
                item,
                default_check_id="legacy_dict_issue",
                default_part_id=default_part_id,
                default_family=default_family,
                default_geometry_authority=default_geometry_authority,
            )
            for item in issues_source
        ]
        summary = dict(input_summary or {})
        if isinstance(result.get("input_summary"), dict):
            summary.update(result["input_summary"])
        return report_with_issues(
            metadata,
            issues,
            elapsed_ms=elapsed_ms,
            input_summary=summary,
            warnings=result.get("warnings") or (),
        )

    if isinstance(result, (list, tuple, set)):
        issues = [
            ValidatorIssue.from_any(
                item,
                default_check_id="legacy_sequence_issue",
                default_part_id=default_part_id,
                default_family=default_family,
                default_geometry_authority=default_geometry_authority,
            )
            for item in result
        ]
        return report_with_issues(metadata, issues, elapsed_ms=elapsed_ms, input_summary=input_summary)

    if result is False:
        return report_with_issues(
            metadata,
            [
                error(
                    "legacy_boolean_result",
                    "Validator returned False.",
                    part_id=default_part_id,
                    family=default_family,
                    geometry_authority=default_geometry_authority,
                )
            ],
            elapsed_ms=elapsed_ms,
            input_summary=input_summary,
        )

    return success_report(metadata, elapsed_ms=elapsed_ms, input_summary=input_summary)
