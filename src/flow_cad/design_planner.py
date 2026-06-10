from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from .draft_operations import draft_operation_registry
from .preview_commands import PreviewParseResult, parse_panel_command

PlanType = Literal["questions", "draft_plan", "concept_plan"]
StepType = Literal["question", "analysis", "operation", "decision", "validation"]


def _panel_operation_ids() -> set[str]:
    return {operation.operation_id for operation in draft_operation_registry()}


_DRAFT_OPERATION_IDS = _panel_operation_ids()


_ANNOTATION_TERMS = (
    "annotated",
    "annotation",
    "draw",
    "drawing",
    "sketch",
    "footprint",
    "shape",
    "outline",
    "freehand",
    "viewport",
    "shown",
    "similar",
)
_ANNOTATED_DRAFT_TERMS = ("plate", "panel", "part", "hole", "holes", "counterbore", "counter bore", "screw", "screws")
_BROAD_HEADROOM_TERMS = ("robot", "head", "housing", "enclosure", "chassis", "mount")
_COUNTERBORE_TERMS = ("counterbore", "counter-bore", "counterbored", "counter bores", "counterbored")
_HOLE_TERMS = ("hole", "holes", "hole mark", "pin")


@dataclass(frozen=True)
class SourceEvidence:
    kind: str
    ref: str
    summary: str | None = None

    def to_payload(self) -> dict[str, str | None]:
        return {"kind": self.kind, "ref": self.ref, "summary": self.summary}


@dataclass(frozen=True)
class DesignBrief:
    brief_id: str
    goal: str
    message_text: str
    normalized_text: str
    has_context_annotations: bool
    has_draft_transaction_token: bool
    has_dimension_tokens: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "brief_id": self.brief_id,
            "goal": self.goal,
            "message_text": self.message_text,
            "normalized_text": self.normalized_text,
            "has_context_annotations": self.has_context_annotations,
            "has_draft_transaction_token": self.has_draft_transaction_token,
            "has_dimension_tokens": self.has_dimension_tokens,
        }


@dataclass(frozen=True)
class DesignPlanStep:
    step_type: StepType
    step_id: str
    summary: str
    operation_id: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    source_evidence: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "step_type": self.step_type,
            "step_id": self.step_id,
            "summary": self.summary,
            "operation_id": self.operation_id,
            "parameters": dict(self.parameters),
            "confidence": self.confidence,
            "source_evidence": list(self.source_evidence),
        }
        return payload


@dataclass(frozen=True)
class DesignPlan:
    plan_id: str
    plan_type: PlanType
    status: str
    brief: DesignBrief
    steps: tuple[DesignPlanStep, ...]
    known_facts: tuple[str, ...]
    missing_decisions: tuple[str, ...]
    assumptions: tuple[str, ...]
    confidence: float
    source_evidence: tuple[SourceEvidence, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "plan_type": self.plan_type,
            "status": self.status,
            "brief": self.brief.to_payload(),
            "steps": [step.to_payload() for step in self.steps],
            "known_facts": list(self.known_facts),
            "missing_decisions": list(self.missing_decisions),
            "assumptions": list(self.assumptions),
            "confidence": self.confidence,
            "source_evidence": [evidence.to_payload() for evidence in self.source_evidence],
        }


def _strip(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _extract_annotations(context_snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(context_snapshot, dict):
        return []
    candidates: list[Any] = []
    candidates.extend(_to_list(context_snapshot.get("annotations")))
    viewer_state = context_snapshot.get("viewer_state")
    if isinstance(viewer_state, dict):
        candidates.extend(_to_list(viewer_state.get("annotations")))
        nested_viewer_state = viewer_state.get("viewer_state")
        if isinstance(nested_viewer_state, dict):
            candidates.extend(_to_list(nested_viewer_state.get("annotations")))
    return [ann for ann in candidates if isinstance(ann, dict)]


def _to_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return list(value)


def _normalize_annotations(annotation: dict[str, Any]) -> tuple[float, float] | None:
    point = annotation.get("point")
    if isinstance(point, dict):
        x = point.get("x")
        y = point.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            return float(x), float(y)

    x = annotation.get("x")
    y = annotation.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        return float(x), float(y)

    points = annotation.get("points")
    if isinstance(points, list) and len(points) >= 2:
        coords = []
        for point in points:
            if not isinstance(point, dict):
                continue
            px = point.get("x")
            py = point.get("y")
            if isinstance(px, (int, float)) and isinstance(py, (int, float)):
                coords.append((float(px), float(py)))
        if coords:
            xs, ys = zip(*coords)
            return sum(xs) / len(xs), sum(ys) / len(ys)
    return None


def _annotation_centers(annotations: list[dict[str, Any]]) -> list[tuple[float, float]]:
    centers: list[tuple[float, float]] = []
    for annotation in annotations:
        center = _normalize_annotations(annotation)
        if center is not None:
            centers.append(center)
    if not centers:
        return [(0.5, 0.5)]
    return centers


def _first_mm_match(text: str) -> float | None:
    match = re.search(r"\b(\d+(?:\.\d+)?)\s*mm\b", text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _first_metric_value(text: str, terms: tuple[str, ...]) -> float | None:
    for term in terms:
        token_pattern = rf"\b{re.escape(term)}\s*[\-:]?\s*(\d+(?:\.\d+)?)\s*mm\b"
        match = re.search(token_pattern, text, re.IGNORECASE)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                return None
    return _first_mm_match(text)


def _map_panel_parse_to_plan(
    parse_result: PreviewParseResult,
    *,
    brief: DesignBrief,
) -> DesignPlan:
    steps: list[DesignPlanStep] = []
    operation_count = 0
    for index, operation in enumerate(parse_result.operations, start=1):
        operation_id = operation.name if operation.name in _DRAFT_OPERATION_IDS else None
        if operation_id is None:
            continue
        operation_count += 1
        steps.append(
            DesignPlanStep(
                step_type="operation",
                step_id=f"apply-{operation_id}-{index}",
                summary=f"Execute deterministic {operation_id} operation.",
                operation_id=operation_id,
                parameters=dict(operation.parameters),
                confidence=0.95,
                source_evidence=("preview_commands.parse_panel_command", "draft_operations.registry"),
            )
        )

    if operation_count:
        steps.append(
            DesignPlanStep(
                step_type="operation",
                step_id="preview-model",
                summary="Preview the draft transaction after deterministic edits.",
                operation_id="preview",
                parameters={},
                confidence=0.92,
                source_evidence=("draft_operations.preview",),
            )
        )

    facts: list[str] = [
        parse_result.command
    ]
    assumptions: list[str] = []
    if parse_result.warnings:
        assumptions.extend([str(warning) for warning in parse_result.warnings])
    missing = ("review draft changes before accept",)
    evidence = (
        SourceEvidence(kind="parser", ref="preview_commands.parse_panel_command", summary="Deterministic panel parser"),
    )
    return DesignPlan(
        plan_id=f"plan_{uuid.uuid4().hex[:12]}",
        plan_type="draft_plan",
        status="proposed",
        brief=brief,
        steps=tuple(steps),
        known_facts=tuple(facts),
        missing_decisions=missing,
        assumptions=tuple(assumptions),
        confidence=0.96 if operation_count else 0.58,
        source_evidence=evidence,
    )


def _make_question_plan(brief: DesignBrief) -> DesignPlan:
    steps = (
        DesignPlanStep(
            step_type="question",
            step_id="question-purpose",
            summary="What is the purpose/use of this component and what constraints should it satisfy?",
        ),
        DesignPlanStep(
            step_type="question",
            step_id="question-size",
            summary="What is the approximate size envelope (length, width, height or footprint) you want?",
        ),
        DesignPlanStep(
            step_type="question",
            step_id="question-mounting",
            summary="How should this mount or attach to the rest of the system (screw pattern, bosses, and mating interface)?",
        ),
        DesignPlanStep(
            step_type="question",
            step_id="question-sensors-openings",
            summary="What sensors/connectors/openings, clearances, or wire passes must this include?",
        ),
        DesignPlanStep(
            step_type="question",
            step_id="question-style-manufacturing",
            summary="Any manufacturing/material/style preferences (3D print, CNC, wall thickness, chamfers, finish)?",
        ),
    )
    return DesignPlan(
        plan_id=f"plan_{uuid.uuid4().hex[:12]}",
        plan_type="questions",
        status="needs_user_input",
        brief=brief,
        steps=steps,
        known_facts=("User request is broad and underspecified.",),
        missing_decisions=(
            "purpose/use",
            "size envelope",
            "mounting/interface",
            "openings and sensors",
            "manufacturing/material/style",
        ),
        assumptions=(),
        confidence=0.84,
        source_evidence=(
            SourceEvidence(kind="message", ref="semantic_intent", summary="Broad prompt lacked explicit geometry"),
        ),
    )


def _make_concept_plan(brief: DesignBrief) -> DesignPlan:
    steps = (
        DesignPlanStep(
            step_type="analysis",
            step_id="synthesize-brief",
            summary="Synthesize the request into a concept direction and candidate geometry family.",
            confidence=0.72,
            source_evidence=("message_semantics",),
        ),
        DesignPlanStep(
            step_type="question",
            step_id="question-missing",
            summary="Confirm constraints missing from the request before proposing a draft plan.",
            confidence=0.66,
        ),
    )
    return DesignPlan(
        plan_id=f"plan_{uuid.uuid4().hex[:12]}",
        plan_type="concept_plan",
        status="proposed",
        brief=brief,
        steps=steps,
        known_facts=("Request is partially structured but not directly parseable into deterministic draft operations.",),
        missing_decisions=("exact dimensions", "constraints", "material choice"),
        assumptions=("Assume user wants a conservative additive-manufacturable concept until clarified.",),
        confidence=0.64,
        source_evidence=(
            SourceEvidence(kind="message", ref="heuristic_concept_classification", summary="Non-deterministic request"),
        ),
    )


def _build_brief(message_text: str, context_snapshot: dict[str, Any] | None) -> DesignBrief:
    normalized_text = _strip(message_text).lower()
    annotations = _extract_annotations(context_snapshot)
    has_annotations = bool(annotations)
    draft_token = None
    if isinstance(context_snapshot, dict):
        draft_token = (
            context_snapshot.get("draft_transaction_token")
            or context_snapshot.get("draft_transaction")
            or None
        )
        if isinstance(draft_token, dict):
            draft_token = draft_token.get("token") or draft_token.get("transaction_token")
    has_draft_token = isinstance(draft_token, str) and bool(draft_token.strip())
    has_dimension_tokens = bool(re.search(r"\b\d+\s*(?:x|×|by)\s*\d+", normalized_text))
    return DesignBrief(
        brief_id=f"brief_{uuid.uuid4().hex[:12]}",
        goal=_strip(message_text),
        message_text=message_text,
        normalized_text=normalized_text,
        has_context_annotations=has_annotations,
        has_draft_transaction_token=has_draft_token,
        has_dimension_tokens=has_dimension_tokens,
    )


def _is_broad_request(brief: DesignBrief) -> bool:
    return (
        _contains_any(brief.normalized_text, _BROAD_HEADROOM_TERMS)
        and not brief.has_dimension_tokens
        and not brief.has_context_annotations
    )


def _is_annotation_intent(brief: DesignBrief) -> bool:
    return brief.has_context_annotations and (
        _contains_any(brief.normalized_text, _ANNOTATION_TERMS)
        or _contains_any(brief.normalized_text, _ANNOTATED_DRAFT_TERMS)
    )


def _counterbore_ops_from_annotations(
    centers: list[tuple[float, float]],
    message_text: str,
) -> list[DesignPlanStep]:
    diameter = _first_metric_value(message_text, ("counterbore", "counter-bore", "cbore")) or 6.0
    depth = _first_metric_value(message_text, ("depth", "deep")) or 2.5
    max_centers = centers or [(0.5, 0.5)]
    steps: list[DesignPlanStep] = []
    for index, (x, y) in enumerate(max_centers[:4], start=1):
        steps.append(
            DesignPlanStep(
                step_type="operation",
                step_id=f"counterbore-{index}",
                summary="Apply a counterbore operation at the extracted annotated location.",
                operation_id="add_counterbore",
                parameters={
                    "face": "top",
                    "x": float(x),
                    "y": float(y),
                    "diameter": float(diameter),
                    "depth": float(depth),
                },
                confidence=0.87,
                source_evidence=("annotation_intent", "derive_footprint_from_annotations"),
            )
        )
    return steps


def _hole_ops_from_annotations(centers: list[tuple[float, float]]) -> list[DesignPlanStep]:
    steps: list[DesignPlanStep] = []
    for index, (x, y) in enumerate(centers, start=1):
        steps.append(
            DesignPlanStep(
                step_type="operation",
                step_id=f"hole-{index}",
                summary="Apply a hole at the extracted annotated location.",
                operation_id="add_hole",
                parameters={
                    "face": "top",
                    "x": float(x),
                    "y": float(y),
                    "diameter": 3.0,
                    "through": True,
                },
                confidence=0.83,
                source_evidence=("annotation_intent", "locate_hole_marks"),
            )
        )
    return steps


def _map_annotations_to_plan(message_text: str, context_snapshot: dict[str, Any] | None) -> DesignPlan:
    annotations = _extract_annotations(context_snapshot)
    brief = _build_brief(message_text, context_snapshot)
    centers = _annotation_centers(annotations)
    steps = [
        DesignPlanStep(
            step_type="analysis",
            step_id="derive_footprint_from_annotations",
            summary="Derive footprint from annotation extents and context.",
            confidence=0.91,
            source_evidence=("context_snapshot.annotations",),
        ),
        DesignPlanStep(
            step_type="analysis",
            step_id="locate_hole_marks",
            summary="Locate candidate hole / counterbore marks from annotations.",
            confidence=0.89,
            source_evidence=("context_snapshot.annotations",),
        ),
    ]

    normalized = brief.normalized_text
    wants_counterbore = _contains_any(normalized, _COUNTERBORE_TERMS)
    wants_holes = _contains_any(normalized, _HOLE_TERMS)

    if wants_counterbore:
        steps.extend(_counterbore_ops_from_annotations(centers, normalized))
    elif wants_holes:
        steps.extend(_hole_ops_from_annotations(centers))

    if not wants_counterbore and not wants_holes:
        steps.extend(_hole_ops_from_annotations(centers[:1]))

    steps.append(
        DesignPlanStep(
            step_type="operation",
            step_id="preview",
            summary="Preview the draft transaction generated from sketch intent.",
            operation_id="preview",
            parameters={},
            confidence=0.9,
            source_evidence=("draft_operations.preview",),
        )
    )

    return DesignPlan(
        plan_id=f"plan_{uuid.uuid4().hex[:12]}",
        plan_type="draft_plan",
        status="proposed",
        brief=brief,
        steps=tuple(steps),
        known_facts=(
            f"{len(annotations)} annotation source records were provided.",
            "Sketch intent path is non-exact until geometry is reified in project runtime.",
        ),
        missing_decisions=(
            "Final annotation-to-face projection assumptions",
            "Exact hole depth/counterbore stack strategy per mark",
        ),
        assumptions=(
            "Assuming face default is top in the absence of explicit face hint.",
        ),
        confidence=0.82,
        source_evidence=(
            SourceEvidence(kind="context_snapshot", ref="annotations", summary="User-supplied annotations found"),
        ),
    )


def plan_design_turn(
    message_text: str,
    context_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a deterministic planning payload from a chat message.
    """
    brief = _build_brief(message_text, context_snapshot)

    if _is_annotation_intent(brief):
        return _map_annotations_to_plan(message_text, context_snapshot).to_payload()

    parsed = parse_panel_command(brief.message_text)
    if parsed.ok and parsed.operations:
        return _map_panel_parse_to_plan(parsed, brief=brief).to_payload()

    if _is_broad_request(brief):
        return _make_question_plan(brief).to_payload()

    return _make_concept_plan(brief).to_payload()
