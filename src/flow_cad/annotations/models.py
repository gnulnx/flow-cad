"""Kernel-free contracts for normalized viewport review annotations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


JsonObject = Mapping[str, Any]
SUPPORTED_MARK_KINDS = frozenset({"pen", "circle", "arrow", "text"})
REVIEW_INTENT = "review_intent"


class AnnotationValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class NormalizedPoint:
    """A viewport-relative point; it deliberately carries no CAD feature identity."""

    x: float
    y: float

    def __post_init__(self) -> None:
        for value, label in ((self.x, "x"), (self.y, "y")):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise AnnotationValidationError(f"annotation point {label} must be numeric")
            if not 0.0 <= float(value) <= 1.0:
                raise AnnotationValidationError(
                    f"annotation point {label} must be normalized between 0 and 1"
                )

    def as_list(self) -> list[float]:
        return [float(self.x), float(self.y)]

    @classmethod
    def from_value(cls, value: object) -> NormalizedPoint:
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
            raise AnnotationValidationError("annotation points must be [x, y] pairs")
        return cls(x=value[0], y=value[1])  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class AnnotationMark:
    mark_id: str
    kind: str
    points: tuple[NormalizedPoint, ...]
    color: str
    stroke_width: float
    text: str | None = None
    intent: str = REVIEW_INTENT

    def __post_init__(self) -> None:
        if not self.mark_id.strip():
            raise AnnotationValidationError("annotation mark_id must not be empty")
        if self.kind not in SUPPORTED_MARK_KINDS:
            raise AnnotationValidationError(f"unsupported annotation kind: {self.kind}")
        expected = {"circle": 2, "arrow": 2, "text": 1}
        if self.kind == "pen" and not self.points:
            raise AnnotationValidationError("pen annotations require at least one point")
        if self.kind in expected and len(self.points) != expected[self.kind]:
            raise AnnotationValidationError(
                f"{self.kind} annotations require exactly {expected[self.kind]} point(s)"
            )
        if self.kind == "text" and not (self.text or "").strip():
            raise AnnotationValidationError("text annotations require non-empty text")
        if self.kind != "text" and self.text is not None:
            raise AnnotationValidationError("only text annotations may contain text")
        if not self.color.strip():
            raise AnnotationValidationError("annotation color must not be empty")
        if isinstance(self.stroke_width, bool) or not isinstance(self.stroke_width, (int, float)):
            raise AnnotationValidationError("annotation stroke_width must be numeric")
        if not 0.25 <= float(self.stroke_width) <= 20.0:
            raise AnnotationValidationError("annotation stroke_width must be between 0.25 and 20")
        if self.intent != REVIEW_INTENT:
            raise AnnotationValidationError(
                "viewport annotation is review intent, not CAD topology"
            )

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mark_id": self.mark_id,
            "kind": self.kind,
            "points": [point.as_list() for point in self.points],
            "color": self.color,
            "stroke_width": float(self.stroke_width),
            "intent": self.intent,
        }
        if self.text is not None:
            payload["text"] = self.text
        return payload

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> AnnotationMark:
        raw_points = payload.get("points")
        if not isinstance(raw_points, Sequence) or isinstance(raw_points, (str, bytes)):
            raise AnnotationValidationError("annotation points must be a list")
        return cls(
            mark_id=_required_text(payload.get("mark_id"), "mark_id"),
            kind=_required_text(payload.get("kind"), "kind"),
            points=tuple(NormalizedPoint.from_value(point) for point in raw_points),
            color=_required_text(payload.get("color"), "color"),
            stroke_width=payload.get("stroke_width", 2.0),  # type: ignore[arg-type]
            text=str(payload["text"]) if payload.get("text") is not None else None,
            intent=str(payload.get("intent", REVIEW_INTENT)),
        )


@dataclass(frozen=True, slots=True)
class AnnotationContext:
    """The render state necessary to understand normalized markup later."""

    camera: JsonObject
    viewport: JsonObject
    artifact_revision: str
    visible_occurrence_ids: tuple[str, ...]
    viewer_revision: str | None = None

    def __post_init__(self) -> None:
        if not self.camera:
            raise AnnotationValidationError("annotation context camera must not be empty")
        if "position" not in self.camera or "up" not in self.camera:
            raise AnnotationValidationError(
                "annotation context camera must include position and up"
            )
        if "target" not in self.camera and "quaternion" not in self.camera:
            raise AnnotationValidationError(
                "annotation context camera must include target or quaternion"
            )
        if not self.viewport:
            raise AnnotationValidationError("annotation context viewport must not be empty")
        for dimension in ("width", "height"):
            value = self.viewport.get(dimension)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise AnnotationValidationError(
                    f"annotation context viewport {dimension} must be positive"
                )
        if not self.artifact_revision.strip():
            raise AnnotationValidationError("annotation context artifact_revision must not be empty")
        if any(not occurrence_id.strip() for occurrence_id in self.visible_occurrence_ids):
            raise AnnotationValidationError("visible occurrence IDs must not be empty")
        if len(set(self.visible_occurrence_ids)) != len(self.visible_occurrence_ids):
            raise AnnotationValidationError("visible occurrence IDs must be unique")

    def as_dict(self) -> dict[str, Any]:
        return {
            "camera": dict(self.camera),
            "viewport": dict(self.viewport),
            "artifact_revision": self.artifact_revision,
            "visible_occurrence_ids": list(self.visible_occurrence_ids),
            "viewer_revision": self.viewer_revision,
        }

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> AnnotationContext:
        camera = payload.get("camera")
        viewport = payload.get("viewport")
        occurrences = payload.get("visible_occurrence_ids", [])
        if not isinstance(camera, Mapping):
            raise AnnotationValidationError("annotation context camera must be an object")
        if not isinstance(viewport, Mapping):
            raise AnnotationValidationError("annotation context viewport must be an object")
        if not isinstance(occurrences, Sequence) or isinstance(occurrences, (str, bytes)):
            raise AnnotationValidationError("visible_occurrence_ids must be a list")
        return cls(
            camera=dict(camera),
            viewport=dict(viewport),
            artifact_revision=_required_text(
                payload.get("artifact_revision"), "artifact_revision"
            ),
            visible_occurrence_ids=tuple(str(item) for item in occurrences),
            viewer_revision=(
                str(payload["viewer_revision"])
                if payload.get("viewer_revision") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class AnnotationSnapshot:
    snapshot_id: str
    thread_id: str
    created_at: str
    hidden: bool
    marks: tuple[AnnotationMark, ...]
    context: AnnotationContext
    intent: str = REVIEW_INTENT

    def __post_init__(self) -> None:
        if self.intent != REVIEW_INTENT:
            raise AnnotationValidationError(
                "viewport annotation is review intent, not CAD topology"
            )
        if not self.snapshot_id.strip() or not self.thread_id.strip() or not self.created_at.strip():
            raise AnnotationValidationError("annotation snapshot identity must not be empty")

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "thread_id": self.thread_id,
            "created_at": self.created_at,
            "hidden": self.hidden,
            "marks": [mark.as_dict() for mark in self.marks],
            "context": self.context.as_dict(),
            "intent": self.intent,
        }


@dataclass(frozen=True, slots=True)
class AnnotationEvent:
    sequence: int
    event_id: str
    request_id: str
    thread_id: str
    event_type: str
    created_at: str
    snapshot: AnnotationSnapshot

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "request_id": self.request_id,
            "thread_id": self.thread_id,
            "event_type": self.event_type,
            "created_at": self.created_at,
            "snapshot": self.snapshot.as_dict(),
        }


def _required_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AnnotationValidationError(f"annotation {label} must not be empty")
    return value.strip()
