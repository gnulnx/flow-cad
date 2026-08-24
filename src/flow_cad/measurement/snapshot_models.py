"""Geometry-free contracts for revision-bound saved measurement labels."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


Vector2 = tuple[float, float]
Vector3 = tuple[float, float, float]
SUPPORTED_MEASUREMENT_KINDS = frozenset({"distance", "edge_length"})
SUPPORTED_MEASUREMENT_QUALITIES = frozenset({"exact", "approximate"})


class MeasurementSnapshotValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MeasurementLabelState:
    """One displayed result plus the state needed to restore its label."""

    measurement_id: str
    kind: str
    title: str
    quality: str
    start_mm: Vector3
    end_mm: Vector3
    total_mm: float
    delta_mm: Vector3
    feature_ids: tuple[str, ...]
    hidden: bool = False
    pinned: bool = False
    label_offset_px: Vector2 = (0.0, 0.0)

    def __post_init__(self) -> None:
        if not self.measurement_id.strip():
            raise MeasurementSnapshotValidationError("measurement_id must not be empty")
        if not self.title.strip():
            raise MeasurementSnapshotValidationError("measurement title must not be empty")
        if self.kind not in SUPPORTED_MEASUREMENT_KINDS:
            raise MeasurementSnapshotValidationError(
                f"unsupported measurement kind: {self.kind}"
            )
        if self.quality not in SUPPORTED_MEASUREMENT_QUALITIES:
            raise MeasurementSnapshotValidationError(
                f"unsupported measurement quality: {self.quality}"
            )

        start = _vector(self.start_mm, 3, "start_mm")
        end = _vector(self.end_mm, 3, "end_mm")
        delta = _vector(self.delta_mm, 3, "delta_mm")
        _vector(self.label_offset_px, 2, "label_offset_px")
        total = _finite_number(self.total_mm, "total_mm")
        if total < 0:
            raise MeasurementSnapshotValidationError("total_mm must be non-negative")

        calculated_delta = tuple(end[index] - start[index] for index in range(3))
        if any(
            not math.isclose(delta[index], calculated_delta[index], rel_tol=1e-9, abs_tol=1e-6)
            for index in range(3)
        ):
            raise MeasurementSnapshotValidationError(
                "delta_mm must equal end_mm minus start_mm"
            )
        calculated_total = math.hypot(*delta)
        if not math.isclose(total, calculated_total, rel_tol=1e-9, abs_tol=1e-6):
            raise MeasurementSnapshotValidationError(
                "total_mm must equal the length of delta_mm"
            )

        if any(not feature_id.strip() for feature_id in self.feature_ids):
            raise MeasurementSnapshotValidationError("feature_ids must not contain empty values")
        if len(set(self.feature_ids)) != len(self.feature_ids):
            raise MeasurementSnapshotValidationError("feature_ids must be unique")
        if self.quality == "exact":
            expected = 2 if self.kind == "distance" else 1
            if len(self.feature_ids) != expected:
                raise MeasurementSnapshotValidationError(
                    f"exact {self.kind} measurements require {expected} feature ID(s)"
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "measurement_id": self.measurement_id,
            "kind": self.kind,
            "title": self.title,
            "quality": self.quality,
            "start_mm": list(self.start_mm),
            "end_mm": list(self.end_mm),
            "total_mm": float(self.total_mm),
            "delta_mm": list(self.delta_mm),
            "feature_ids": list(self.feature_ids),
            "hidden": self.hidden,
            "pinned": self.pinned,
            "label_offset_px": list(self.label_offset_px),
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> MeasurementLabelState:
        feature_ids = payload.get("feature_ids", [])
        if not isinstance(feature_ids, Sequence) or isinstance(feature_ids, (str, bytes)):
            raise MeasurementSnapshotValidationError("feature_ids must be a list")
        return cls(
            measurement_id=_required_text(payload.get("measurement_id"), "measurement_id"),
            kind=_required_text(payload.get("kind"), "kind"),
            title=_required_text(payload.get("title"), "title"),
            quality=_required_text(payload.get("quality"), "quality"),
            start_mm=_vector(payload.get("start_mm"), 3, "start_mm"),
            end_mm=_vector(payload.get("end_mm"), 3, "end_mm"),
            total_mm=_finite_number(payload.get("total_mm"), "total_mm"),
            delta_mm=_vector(payload.get("delta_mm"), 3, "delta_mm"),
            feature_ids=tuple(str(value) for value in feature_ids),
            hidden=bool(payload.get("hidden", False)),
            pinned=bool(payload.get("pinned", False)),
            label_offset_px=_vector(
                payload.get("label_offset_px", (0.0, 0.0)), 2, "label_offset_px"
            ),
        )


@dataclass(frozen=True, slots=True)
class MeasurementSnapshot:
    snapshot_id: str
    thread_id: str
    part_uuid: str
    artifact_revision: str
    created_at: str
    measurements: tuple[MeasurementLabelState, ...]

    def __post_init__(self) -> None:
        identities = (
            (self.snapshot_id, "snapshot_id"),
            (self.thread_id, "thread_id"),
            (self.part_uuid, "part_uuid"),
            (self.artifact_revision, "artifact_revision"),
            (self.created_at, "created_at"),
        )
        for value, label in identities:
            if not value.strip():
                raise MeasurementSnapshotValidationError(f"{label} must not be empty")
        measurement_ids = [measurement.measurement_id for measurement in self.measurements]
        if len(set(measurement_ids)) != len(measurement_ids):
            raise MeasurementSnapshotValidationError(
                "measurement IDs must be unique within a snapshot"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "thread_id": self.thread_id,
            "part_uuid": self.part_uuid,
            "artifact_revision": self.artifact_revision,
            "created_at": self.created_at,
            "measurements": [measurement.as_dict() for measurement in self.measurements],
        }


@dataclass(frozen=True, slots=True)
class MeasurementSnapshotEvent:
    sequence: int
    event_id: str
    request_id: str
    thread_id: str
    part_uuid: str
    event_type: str
    created_at: str
    snapshot: MeasurementSnapshot

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "request_id": self.request_id,
            "thread_id": self.thread_id,
            "part_uuid": self.part_uuid,
            "event_type": self.event_type,
            "created_at": self.created_at,
            "snapshot": self.snapshot.as_dict(),
        }


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MeasurementSnapshotValidationError(f"{label} must not be empty")
    return value.strip()


def _finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MeasurementSnapshotValidationError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise MeasurementSnapshotValidationError(f"{label} must be finite")
    return result


def _vector(value: object, size: int, label: str):
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != size:
        raise MeasurementSnapshotValidationError(
            f"{label} must contain exactly {size} numeric values"
        )
    return tuple(_finite_number(component, label) for component in value)
