from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from .draft_operations import draft_operation_registry
from .preview_commands import PreviewParseResult, parse_panel_command

PlanType = Literal["questions", "draft_plan", "concept_plan"]
StepType = Literal["question", "analysis", "operation", "decision", "validation"]
IntentStatus = Literal["covered", "partial", "unsupported", "needs_decision", "verification_only"]
ExecutionReadiness = Literal["ready", "partial_requires_review", "needs_questions", "concept_only"]


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
_SKETCH_OUTLINE_TERMS = ("sketch", "outline", "profile", "curve", "contour", "freehand", "drawing")
_SKETCH_REVISION_PHRASE_TERMS = (
    "not following",
    "not matching",
    "not match",
    "not aligned",
)
_SKETCH_REVISION_CONTEXT_TERMS = (
    "curve",
    "curves",
    "original sketch",
    "sketch outline",
    "draft sketch",
)

_PLATE_TERMS = ("plate", "panel", "base", "part", "body", "bracket", "tray")
_PILLAR_TERMS = ("pillar", "pillars", "boss", "bosses", "standoff", "standoffs", "post", "posts")
_INSERT_TERMS = ("insert", "inserts", "pocket", "pockets", "recess", "recesses", "shelf", "shelves")
_SLOT_TERMS = ("slot", "slots", "wire pass", "wire-pass", "cutout", "cutouts")
_LOUVER_TERMS = ("louver", "louvers", "vent", "vents")
_MIRROR_PATTERN_TERMS = ("mirror", "mirrored", "pattern", "repeat", "repeated", "each corner", "all 4 corners", "all four corners")
_SIDE_FACE_TERMS = (
    "external face",
    "external faces",
    "side face",
    "side faces",
    "outside face",
    "outside faces",
    "front face",
    "front faces",
    "back face",
    "back faces",
    "left face",
    "left faces",
    "right face",
    "right faces",
)
_NON_OVERLAP_TERMS = ("not overlap", "no overlap", "avoid overlap", "clear of", "do not intersect", "not intersect")
_ADVANCED_SURFACE_TERMS = ("fillet", "fillets", "chamfer", "chamfers", "shell", "hollow", "loft", "sweep")
_RELOCATION_TERMS = ("move", "relocate", "shift")
_RELOCATABLE_FEATURE_TERMS = _HOLE_TERMS + _PILLAR_TERMS + _INSERT_TERMS + _SLOT_TERMS + _LOUVER_TERMS


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
class IntentItem:
    requirement_id: str
    kind: str
    summary: str
    status: IntentStatus
    severity: str = "required"
    parameters: dict[str, Any] = field(default_factory=dict)
    mapped_operations: tuple[str, ...] = ()
    missing_capabilities: tuple[str, ...] = ()
    verification: tuple[str, ...] = ()
    source_evidence: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "kind": self.kind,
            "summary": self.summary,
            "status": self.status,
            "severity": self.severity,
            "parameters": dict(self.parameters),
            "mapped_operations": list(self.mapped_operations),
            "missing_capabilities": list(self.missing_capabilities),
            "verification": list(self.verification),
            "source_evidence": list(self.source_evidence),
        }


@dataclass(frozen=True)
class IntentCoverage:
    execution_readiness: ExecutionReadiness
    can_auto_execute: bool
    total_count: int
    covered_count: int
    partial_count: int
    unsupported_count: int
    needs_decision_count: int
    verification_only_count: int
    summary: str
    blocking_items: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, Any]:
        return {
            "execution_readiness": self.execution_readiness,
            "can_auto_execute": self.can_auto_execute,
            "total_count": self.total_count,
            "covered_count": self.covered_count,
            "partial_count": self.partial_count,
            "unsupported_count": self.unsupported_count,
            "needs_decision_count": self.needs_decision_count,
            "verification_only_count": self.verification_only_count,
            "summary": self.summary,
            "blocking_items": list(self.blocking_items),
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
    intent_items: tuple[IntentItem, ...] = ()
    coverage: IntentCoverage | None = None
    verification: tuple[str, ...] = ()

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
            "intent_items": [item.to_payload() for item in self.intent_items],
            "coverage": self.coverage.to_payload() if self.coverage else None,
            "verification": list(self.verification),
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


def _operation_ids(parse_result: PreviewParseResult | None) -> set[str]:
    if parse_result is None:
        return set()
    return {operation.name for operation in parse_result.operations}


def _context_has_target(context_snapshot: dict[str, Any] | None) -> bool:
    if not isinstance(context_snapshot, dict):
        return False
    selected = context_snapshot.get("selected_part_ids")
    if isinstance(selected, list) and any(isinstance(value, str) and value.strip() for value in selected):
        return True
    visible = context_snapshot.get("visible_part_ids")
    if isinstance(visible, list) and any(isinstance(value, str) and value.strip().startswith("draft:") for value in visible):
        return True
    draft_token = context_snapshot.get("draft_transaction_token") or context_snapshot.get("draft_transaction")
    if isinstance(draft_token, dict):
        draft_token = draft_token.get("token") or draft_token.get("transaction_token")
    return isinstance(draft_token, str) and bool(draft_token.strip())


def _count_hint(text: str, terms: tuple[str, ...]) -> int | None:
    number_words = {
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
    }
    if "all 4 corners" in text or "all four corners" in text:
        return 4
    term_pattern = "|".join(re.escape(term) for term in terms)
    match = re.search(rf"\b(?P<count>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b[^.]*?\b(?:{term_pattern})\b", text)
    if not match:
        return None
    raw = match.group("count").lower()
    if raw in number_words:
        return number_words[raw]
    try:
        return int(raw)
    except ValueError:
        return None


def _dimension_triplet(text: str) -> tuple[float, float, float] | None:
    match = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:x|×|by|byu)\s*"
        r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:x|×|by|byu)\s*"
        r"(\d+(?:\.\d+)?)\s*(?:mm)?",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return float(match.group(1)), float(match.group(2)), float(match.group(3))


def _status_counts(items: tuple[IntentItem, ...]) -> dict[str, int]:
    return {
        "covered": sum(1 for item in items if item.status == "covered"),
        "partial": sum(1 for item in items if item.status == "partial"),
        "unsupported": sum(1 for item in items if item.status == "unsupported"),
        "needs_decision": sum(1 for item in items if item.status == "needs_decision"),
        "verification_only": sum(1 for item in items if item.status == "verification_only"),
    }


def _coverage_for_items(
    items: tuple[IntentItem, ...],
    *,
    fallback_readiness: ExecutionReadiness = "ready",
    can_auto_execute_fallback: bool = True,
) -> IntentCoverage:
    counts = _status_counts(items)
    blocking = tuple(
        item.requirement_id
        for item in items
        if item.status in {"unsupported", "needs_decision"}
        or (item.status == "partial" and item.severity == "required")
    )
    if counts["needs_decision"] or counts["unsupported"]:
        readiness: ExecutionReadiness = "partial_requires_review"
    elif any(item.status == "partial" and item.severity == "required" for item in items):
        readiness = "partial_requires_review"
    else:
        readiness = fallback_readiness
    can_auto_execute = can_auto_execute_fallback and readiness == "ready"
    if not items:
        can_auto_execute = False
    summary = (
        f"{counts['covered']} covered, {counts['partial']} partial, "
        f"{counts['unsupported']} unsupported, {counts['needs_decision']} need decisions, "
        f"{counts['verification_only']} verification-only."
    )
    return IntentCoverage(
        execution_readiness=readiness,
        can_auto_execute=can_auto_execute,
        total_count=len(items),
        covered_count=counts["covered"],
        partial_count=counts["partial"],
        unsupported_count=counts["unsupported"],
        needs_decision_count=counts["needs_decision"],
        verification_only_count=counts["verification_only"],
        summary=summary,
        blocking_items=blocking,
    )


def _planner_verification_steps(items: tuple[IntentItem, ...]) -> tuple[str, ...]:
    verification: list[str] = []
    for item in items:
        verification.extend(item.verification)
    verification.append("Review intent coverage before executing draft operations.")
    verification.append("After preview, compare draft facts against every intent item.")
    return tuple(dict.fromkeys(step for step in verification if step))


def _extract_intent_items(
    brief: DesignBrief,
    parse_result: PreviewParseResult | None,
    *,
    context_snapshot: dict[str, Any] | None = None,
) -> tuple[IntentItem, ...]:
    text = brief.normalized_text
    operations = _operation_ids(parse_result)
    items: list[IntentItem] = []
    dimensions = _dimension_triplet(text)
    has_target_context = _context_has_target(context_snapshot)

    feature_request_has_target = has_target_context and (
        _contains_any(text, _PILLAR_TERMS)
        or _contains_any(text, _HOLE_TERMS)
        or _contains_any(text, _INSERT_TERMS)
        or _contains_any(text, _SLOT_TERMS)
        or _contains_any(text, _LOUVER_TERMS)
        or "mounting" in text
    )
    if (
        _contains_any(text, _PLATE_TERMS)
        or "create_box" in operations
        or "create_sketch_profile" in operations
        or feature_request_has_target
    ):
        mapped = tuple(op for op in ("create_box", "create_sketch_profile") if op in operations)
        if mapped:
            status: IntentStatus = "covered"
            missing: tuple[str, ...] = ()
        elif dimensions:
            status = "partial"
            missing = ("base_geometry_operation_mapping",)
        elif has_target_context:
            status = "covered"
            missing = ()
        else:
            status = "needs_decision"
            missing = ("base_dimensions_or_selected_target",)
        items.append(
            IntentItem(
                requirement_id="base-geometry",
                kind="base_geometry",
                summary="Base plate/panel/body geometry.",
                status=status,
                parameters={
                    **({"dimensions_mm": dimensions} if dimensions else {}),
                    **({"target_context": "selected_or_active_draft"} if has_target_context else {}),
                },
                mapped_operations=mapped,
                missing_capabilities=missing,
                verification=("Check preview bounding box dimensions.",),
                source_evidence=("prompt.base_geometry",),
            )
        )

    if "hole" in text or "holes" in text or "screw" in text or "mounting" in text or "add_hole" in operations:
        count = _count_hint(text, _HOLE_TERMS + ("screw", "screws", "mounting"))
        diameter = _first_metric_value(text, ("m", "hole", "holes", "screw", "mounting")) or _first_mm_match(text)
        side_face = _contains_any(text, _SIDE_FACE_TERMS)
        complex_target = bool(_contains_any(text, _PILLAR_TERMS) or side_face)
        if "add_hole" in operations and not complex_target:
            status = "covered"
            missing = ()
        elif "add_hole" in _DRAFT_OPERATION_IDS:
            status = "partial" if complex_target else "covered"
            missing = ("target_local_frame_resolution",) if complex_target else ()
        else:
            status = "unsupported"
            missing = ("add_hole",)
        items.append(
            IntentItem(
                requirement_id="holes",
                kind="hole_pattern",
                summary="Round mounting/screw holes.",
                status=status,
                parameters={
                    **({"count": count} if count else {}),
                    **({"diameter_or_metric_mm": diameter} if diameter else {}),
                    "side_face_target": side_face,
                },
                mapped_operations=("add_hole",) if "add_hole" in _DRAFT_OPERATION_IDS else (),
                missing_capabilities=missing,
                verification=("Check hole count, centers, diameters, and face normals.",),
                source_evidence=("prompt.holes",),
            )
        )

    if _contains_any(text, _RELOCATION_TERMS) and _contains_any(text, _RELOCATABLE_FEATURE_TERMS):
        items.append(
            IntentItem(
                requirement_id="feature-relocation",
                kind="feature_relocation",
                summary="Move or retarget existing feature geometry.",
                status="unsupported",
                mapped_operations=(),
                missing_capabilities=("move_existing_feature_operation", "source_feature_resolution"),
                verification=("Check original feature identity, target face, and post-edit source regeneration.",),
                source_evidence=("prompt.feature_relocation",),
            )
        )

    if _contains_any(text, _COUNTERBORE_TERMS) or "add_counterbore" in operations:
        status = "covered" if "add_counterbore" in operations else "partial"
        items.append(
            IntentItem(
                requirement_id="counterbores",
                kind="counterbore_pattern",
                summary="Counterbore pockets for fasteners.",
                status=status,
                mapped_operations=("add_counterbore",),
                missing_capabilities=() if status == "covered" else ("exact_counterbore_locations",),
                verification=("Check counterbore diameters, depths, and concentricity with holes.",),
                source_evidence=("prompt.counterbore",),
            )
        )

    if _contains_any(text, _PILLAR_TERMS):
        count = _count_hint(text, _PILLAR_TERMS)
        height = _first_metric_value(text, ("pillar", "pillars", "boss", "bosses", "standoff", "standoffs", "height", "tall"))
        needs_cross_section = not _contains_any(text, ("square", "rectangular", "block"))
        items.append(
            IntentItem(
                requirement_id="pillars",
                kind="boss_or_pillar",
                summary="Raised pillars/bosses/standoffs attached to base geometry.",
                status="partial",
                parameters={
                    **({"count": count} if count else {}),
                    **({"height_mm": height} if height else {}),
                    "location_hint": "corners" if "corner" in text else None,
                },
                mapped_operations=("add_raised_wall",),
                missing_capabilities=(
                    "cylindrical_or_named_boss_primitive" if needs_cross_section else "pillar_template",
                    "pillar_local_feature_frame",
                ),
                verification=("Check pillar count, height, footprint, and attachment to base.",),
                source_evidence=("prompt.pillars",),
            )
        )

    if _contains_any(text, _INSERT_TERMS):
        depth = _first_metric_value(text, _INSERT_TERMS)
        items.append(
            IntentItem(
                requirement_id="inserts",
                kind="insert_or_recess",
                summary="Insert pocket, shelf, or recessed plate interface.",
                status="unsupported",
                parameters={**({"depth_mm": depth} if depth else {})},
                mapped_operations=(),
                missing_capabilities=("insert_pocket_or_recess_operation",),
                verification=("Check pocket depth, landing face, and retained wall thickness.",),
                source_evidence=("prompt.inserts",),
            )
        )

    if _contains_any(text, _SLOT_TERMS) or "add_slot" in operations:
        items.append(
            IntentItem(
                requirement_id="slots-cutouts",
                kind="slot_or_cutout",
                summary="Slots, wire passes, or rectangular cutouts.",
                status="covered" if "add_slot" in operations else "partial",
                mapped_operations=("add_slot",),
                missing_capabilities=() if "add_slot" in operations else ("slot_dimensions_or_locations",),
                verification=("Check slot length, width, face, and clearance.",),
                source_evidence=("prompt.slots",),
            )
        )

    if _contains_any(text, _LOUVER_TERMS) or "add_louver_pattern" in operations:
        items.append(
            IntentItem(
                requirement_id="louvers",
                kind="louver_pattern",
                summary="Repeated louver/vent pattern.",
                status="covered" if "add_louver_pattern" in operations else "partial",
                mapped_operations=("add_louver_pattern",),
                missing_capabilities=() if "add_louver_pattern" in operations else ("louver_count_pitch_or_face",),
                verification=("Check louver count, pitch, size, and face.",),
                source_evidence=("prompt.louvers",),
            )
        )

    if _contains_any(text, _MIRROR_PATTERN_TERMS):
        items.append(
            IntentItem(
                requirement_id="patterns",
                kind="pattern_or_symmetry",
                summary="Repeated, mirrored, or corner-distributed feature placement.",
                status="covered" if any(op in operations for op in ("add_hole", "add_louver_pattern", "mirror_features")) else "partial",
                mapped_operations=tuple(op for op in ("add_hole", "add_louver_pattern", "mirror_features") if op in _DRAFT_OPERATION_IDS),
                missing_capabilities=() if any(op in operations for op in ("add_hole", "add_louver_pattern")) else ("pattern_seed_geometry",),
                verification=("Check repeated feature count and symmetry.",),
                source_evidence=("prompt.pattern",),
            )
        )

    if _contains_any(text, _NON_OVERLAP_TERMS) or "interior" in text:
        items.append(
            IntentItem(
                requirement_id="non-overlap",
                kind="constraint",
                summary="Feature clearance/non-overlap constraint.",
                status="verification_only",
                mapped_operations=(),
                verification=("Run focused validator or geometry check for feature overlap/intersection.",),
                source_evidence=("prompt.clearance_constraint",),
            )
        )

    if _contains_any(text, _ADVANCED_SURFACE_TERMS):
        items.append(
            IntentItem(
                requirement_id="advanced-surface",
                kind="advanced_surface_modeling",
                summary="Advanced direct/surface modeling operation.",
                status="unsupported",
                mapped_operations=(),
                missing_capabilities=("fillet_chamfer_shell_loft_sweep_operations",),
                verification=("Requires source-level CAD implementation or new draft operation before preview.",),
                source_evidence=("prompt.advanced_surface",),
            )
        )

    if brief.has_context_annotations:
        items.append(
            IntentItem(
                requirement_id="visual-intent",
                kind="annotation_or_sketch",
                summary="Viewport annotation/sketch intent must be preserved.",
                status="partial",
                mapped_operations=("create_sketch_profile",),
                missing_capabilities=("exact_annotation_to_face_projection",),
                verification=("Compare interpreted profile and marks against the source annotation image.",),
                source_evidence=("context_snapshot.annotations",),
            )
        )

    # Preserve stable order while avoiding duplicate broad items in small prompts.
    seen: set[str] = set()
    unique_items: list[IntentItem] = []
    for item in items:
        if item.requirement_id in seen:
            continue
        seen.add(item.requirement_id)
        unique_items.append(item)
    return tuple(unique_items)


def _map_panel_parse_to_plan(
    parse_result: PreviewParseResult,
    *,
    brief: DesignBrief,
    context_snapshot: dict[str, Any] | None = None,
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
    intent_items = _extract_intent_items(brief, parse_result, context_snapshot=context_snapshot)
    coverage = _coverage_for_items(intent_items, can_auto_execute_fallback=bool(operation_count))
    assumptions: list[str] = []
    if parse_result.warnings:
        assumptions.extend([str(warning) for warning in parse_result.warnings])
    missing = ["review draft changes before accept"]
    missing.extend(item.summary for item in intent_items if item.requirement_id in set(coverage.blocking_items))
    evidence = (
        SourceEvidence(kind="parser", ref="preview_commands.parse_panel_command", summary="Deterministic panel parser"),
        SourceEvidence(kind="intent_audit", ref="design_planner.intent_items", summary=coverage.summary),
    )
    return DesignPlan(
        plan_id=f"plan_{uuid.uuid4().hex[:12]}",
        plan_type="draft_plan",
        status="proposed" if coverage.can_auto_execute else "partial_requires_review",
        brief=brief,
        steps=tuple(steps),
        known_facts=tuple(facts),
        missing_decisions=tuple(dict.fromkeys(missing)),
        assumptions=tuple(assumptions),
        confidence=0.96 if operation_count and coverage.can_auto_execute else 0.58,
        source_evidence=evidence,
        intent_items=intent_items,
        coverage=coverage,
        verification=_planner_verification_steps(intent_items),
    )


def _make_question_plan(brief: DesignBrief) -> DesignPlan:
    intent_items = _extract_intent_items(brief, None)
    coverage = _coverage_for_items(
        intent_items,
        fallback_readiness="needs_questions",
        can_auto_execute_fallback=False,
    )
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
            SourceEvidence(kind="intent_audit", ref="design_planner.intent_items", summary=coverage.summary),
        ),
        intent_items=intent_items,
        coverage=coverage,
        verification=_planner_verification_steps(intent_items),
    )


def _make_concept_plan(brief: DesignBrief) -> DesignPlan:
    intent_items = _extract_intent_items(brief, None)
    coverage = _coverage_for_items(
        intent_items,
        fallback_readiness="concept_only",
        can_auto_execute_fallback=False,
    )
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
            SourceEvidence(kind="intent_audit", ref="design_planner.intent_items", summary=coverage.summary),
        ),
        intent_items=intent_items,
        coverage=coverage,
        verification=_planner_verification_steps(intent_items),
    )


def _make_audited_draft_plan(
    brief: DesignBrief,
    context_snapshot: dict[str, Any] | None,
) -> DesignPlan:
    intent_items = _extract_intent_items(brief, None, context_snapshot=context_snapshot)
    coverage = _coverage_for_items(
        intent_items,
        fallback_readiness="partial_requires_review",
        can_auto_execute_fallback=False,
    )
    steps = (
        DesignPlanStep(
            step_type="analysis",
            step_id="audit-intent-coverage",
            summary="Audit requested CAD intent against the registered draft operation surface.",
            confidence=0.9,
            source_evidence=("design_planner.intent_items", "draft_operations.registry"),
        ),
        DesignPlanStep(
            step_type="decision",
            step_id="resolve-blocking-intent",
            summary="Resolve unsupported or partial intent before running automatic draft mutation.",
            confidence=0.86,
            source_evidence=("coverage.blocking_items",),
        ),
    )
    missing = tuple(
        item.summary
        for item in intent_items
        if item.requirement_id in set(coverage.blocking_items)
    )
    return DesignPlan(
        plan_id=f"plan_{uuid.uuid4().hex[:12]}",
        plan_type="draft_plan",
        status="partial_requires_review",
        brief=brief,
        steps=steps,
        known_facts=("Request contains draft mutation intent, but no complete deterministic operation path was found.",),
        missing_decisions=missing or ("Resolve planner blocking items before mutation.",),
        assumptions=(),
        confidence=0.7,
        source_evidence=(
            SourceEvidence(kind="intent_audit", ref="design_planner.intent_items", summary=coverage.summary),
        ),
        intent_items=intent_items,
        coverage=coverage,
        verification=_planner_verification_steps(intent_items),
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


def _is_feature_relocation_intent(brief: DesignBrief) -> bool:
    return _contains_any(brief.normalized_text, _RELOCATION_TERMS) and _contains_any(
        brief.normalized_text,
        _RELOCATABLE_FEATURE_TERMS,
    )


def _is_annotation_intent(brief: DesignBrief) -> bool:
    return brief.has_context_annotations and (
        _contains_any(brief.normalized_text, _ANNOTATION_TERMS)
        or _contains_any(brief.normalized_text, _ANNOTATED_DRAFT_TERMS)
    )


def _is_sketch_revision_intent(brief: DesignBrief) -> bool:
    return (
        brief.has_draft_transaction_token
        and _contains_any(brief.normalized_text, _SKETCH_REVISION_PHRASE_TERMS)
        and _contains_any(brief.normalized_text, _SKETCH_REVISION_CONTEXT_TERMS)
    )


def _should_build_sketch_profile(brief: DesignBrief, *, is_revision: bool) -> bool:
    return is_revision or _contains_any(brief.normalized_text, _SKETCH_OUTLINE_TERMS)


def _sketch_profile_operation_id(brief: DesignBrief) -> str:
    if _contains_any(brief.normalized_text, ("sketch", "freehand", "drawing")):
        return "create_sketch_profile"
    return "create_extruded_profile"


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


def _map_annotations_to_plan(
    message_text: str,
    context_snapshot: dict[str, Any] | None,
    *,
    is_revision: bool = False,
) -> DesignPlan:
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
    wants_profile = _should_build_sketch_profile(brief, is_revision=is_revision)

    if wants_profile:
        profile_operation_id = _sketch_profile_operation_id(brief)
        steps.append(
            DesignPlanStep(
                step_type="operation",
                step_id="cleaned-sketch-profile",
                summary="Create an interpreted sketch/profile outline before downstream edits.",
                operation_id=profile_operation_id,
                parameters={"source": "annotations" if brief.has_context_annotations else "draft_context"},
                confidence=0.9,
                source_evidence=("context_snapshot.annotations", "draft_context"),
            )
        )

    if wants_counterbore:
        steps.extend(_counterbore_ops_from_annotations(centers, normalized))
    elif wants_holes:
        steps.extend(_hole_ops_from_annotations(centers))
    elif not wants_profile:
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
    intent_items = _extract_intent_items(brief, None, context_snapshot=context_snapshot)
    coverage = _coverage_for_items(
        intent_items,
        can_auto_execute_fallback=not any(item.status in {"unsupported", "needs_decision"} for item in intent_items),
    )

    return DesignPlan(
        plan_id=f"plan_{uuid.uuid4().hex[:12]}",
        plan_type="draft_plan",
        status="proposed" if coverage.can_auto_execute else "partial_requires_review",
        brief=brief,
        steps=tuple(steps),
        known_facts=(
            f"{len(annotations)} annotation source records were provided.",
            "Sketch intent path is non-exact until geometry is reified in project runtime.",
        ),
        missing_decisions=(
            "Final annotation-to-face projection assumptions",
            "Exact hole depth/counterbore stack strategy per mark"
            if (wants_counterbore or wants_holes)
            else "Profile interpretation tolerance and simplification strategy",
        ),
        assumptions=(
            "Assuming face default is top in the absence of explicit face hint.",
        ),
        confidence=0.82,
        source_evidence=(
            SourceEvidence(kind="context_snapshot", ref="annotations", summary="User-supplied annotations found"),
            SourceEvidence(kind="intent_audit", ref="design_planner.intent_items", summary=coverage.summary),
        ),
        intent_items=intent_items,
        coverage=coverage,
        verification=_planner_verification_steps(intent_items),
    )


def plan_design_turn(
    message_text: str,
    context_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a deterministic planning payload from a chat message.
    """
    brief = _build_brief(message_text, context_snapshot)
    is_revision = _is_sketch_revision_intent(brief)

    if _is_annotation_intent(brief) or is_revision:
        return _map_annotations_to_plan(message_text, context_snapshot, is_revision=is_revision).to_payload()

    parsed = parse_panel_command(brief.message_text)
    if parsed.ok and parsed.operations:
        return _map_panel_parse_to_plan(parsed, brief=brief, context_snapshot=context_snapshot).to_payload()

    if _contains_any(brief.normalized_text, _ADVANCED_SURFACE_TERMS):
        return _make_concept_plan(brief).to_payload()

    if _is_broad_request(brief):
        return _make_question_plan(brief).to_payload()

    if _is_feature_relocation_intent(brief):
        return _make_concept_plan(brief).to_payload()

    audit_items = _extract_intent_items(brief, None, context_snapshot=context_snapshot)
    if audit_items and (
        brief.has_draft_transaction_token
        or _context_has_target(context_snapshot)
        or any(item.status in {"partial", "unsupported", "needs_decision", "verification_only"} for item in audit_items)
    ):
        return _make_audited_draft_plan(brief, context_snapshot).to_payload()

    return _make_concept_plan(brief).to_payload()


def intent_planner_verification_cases() -> tuple[dict[str, Any], ...]:
    """Return representative planner cases used by tests and manual verification."""
    return (
        {
            "id": "simple_plate",
            "message": "create a plate that is 100 x 120 x 10 mm",
            "expect_plan_type": "draft_plan",
            "expect_readiness": "ready",
            "expect_kinds": ("base_geometry",),
        },
        {
            "id": "corner_holes",
            "message": "create a 120 x 80 x 4 mm panel with four M4 holes in each corner",
            "expect_plan_type": "draft_plan",
            "expect_readiness": "ready",
            "expect_kinds": ("base_geometry", "hole_pattern", "pattern_or_symmetry"),
        },
        {
            "id": "slots_and_louvers",
            "message": "make a 140 x 60 x 3 mm side panel with five louvers and two wire slots",
            "expect_plan_type": "draft_plan",
            "expect_readiness": "partial_requires_review",
            "expect_kinds": ("base_geometry", "slot_or_cutout", "louver_pattern"),
        },
        {
            "id": "simple_louver_panel",
            "message": "create a 100 x 50 x 3 mm panel with five louvers pitch 10mm",
            "expect_plan_type": "draft_plan",
            "expect_readiness": "ready",
            "expect_kinds": ("base_geometry", "louver_pattern"),
        },
        {
            "id": "selected_context_standoffs",
            "message": "add four 25mm tall standoffs in the corners with M3 side holes",
            "context_snapshot": {"selected_part_ids": ["example_block"]},
            "expect_plan_type": "draft_plan",
            "expect_readiness": "partial_requires_review",
            "expect_kinds": ("base_geometry", "boss_or_pillar", "hole_pattern"),
        },
        {
            "id": "pillar_insert_complex",
            "message": (
                "Add pillars in all 4 corners. Each pillar should be 40mm tall. Pillars should be insert 3mm "
                "for plates that attach to the pillars on all 4 sides. Each pillar needs 4 mounting holes. "
                "2 on each external face. The M4 mounting holes should not overlap on the interior of the pillars."
            ),
            "expect_plan_type": "draft_plan",
            "expect_readiness": "partial_requires_review",
            "expect_kinds": ("hole_pattern", "boss_or_pillar", "insert_or_recess", "constraint"),
        },
        {
            "id": "insert_keepout",
            "message": "add a 3mm recessed insert pocket and keep all M4 screw holes clear of the interior",
            "context_snapshot": {"selected_part_ids": ["example_block"]},
            "expect_plan_type": "draft_plan",
            "expect_readiness": "partial_requires_review",
            "expect_kinds": ("base_geometry", "hole_pattern", "insert_or_recess", "constraint"),
        },
        {
            "id": "feature_relocation_runtime_path",
            "message": "Move the holes to the front face.",
            "context_snapshot": {"selected_part_ids": ["example_block"]},
            "expect_plan_type": "concept_plan",
            "expect_readiness": "partial_requires_review",
            "expect_kinds": ("hole_pattern", "feature_relocation"),
        },
        {
            "id": "battery_tray_wire_slots",
            "message": "make a battery tray 180 x 80 x 20 mm with side wire pass slots",
            "expect_plan_type": "draft_plan",
            "expect_readiness": "partial_requires_review",
            "expect_kinds": ("base_geometry", "slot_or_cutout"),
        },
        {
            "id": "robot_head_questions",
            "message": "Make a robot head",
            "expect_plan_type": "questions",
            "expect_readiness": "needs_questions",
            "expect_kinds": (),
        },
        {
            "id": "advanced_surface_unsupported",
            "message": "make a curved enclosure with fillets, shell it hollow, and loft the nose",
            "expect_plan_type": "concept_plan",
            "expect_readiness": "partial_requires_review",
            "expect_kinds": ("advanced_surface_modeling",),
        },
        {
            "id": "chamfered_mount_concept",
            "message": "make a rounded motor mount with chamfers and a curved swept cable relief",
            "expect_plan_type": "concept_plan",
            "expect_readiness": "partial_requires_review",
            "expect_kinds": ("advanced_surface_modeling",),
        },
        {
            "id": "annotation_counterbore",
            "message": "Use this drawing to add counterbore points from the sketch",
            "context_snapshot": {
                "annotations": [
                    {"kind": "circle", "x": 0.25, "y": 0.33, "radius": 0.04},
                    {"kind": "circle", "x": 0.75, "y": 0.66, "radius": 0.04},
                ],
                "draft_transaction_token": "tx-verify",
            },
            "expect_plan_type": "draft_plan",
            "expect_readiness": "partial_requires_review",
            "expect_kinds": ("counterbore_pattern", "annotation_or_sketch"),
        },
    )


def verify_intent_planner_cases() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    ok = True
    for case in intent_planner_verification_cases():
        payload = plan_design_turn(
            str(case["message"]),
            case.get("context_snapshot") if isinstance(case.get("context_snapshot"), dict) else None,
        )
        coverage = payload.get("coverage") if isinstance(payload.get("coverage"), dict) else {}
        kinds = {
            item.get("kind")
            for item in payload.get("intent_items", [])
            if isinstance(item, dict)
        }
        failures: list[str] = []
        if payload.get("plan_type") != case["expect_plan_type"]:
            failures.append(f"plan_type={payload.get('plan_type')!r}")
        if coverage.get("execution_readiness") != case["expect_readiness"]:
            failures.append(f"execution_readiness={coverage.get('execution_readiness')!r}")
        for expected_kind in case.get("expect_kinds", ()):
            if expected_kind not in kinds:
                failures.append(f"missing intent kind {expected_kind!r}")
        case_ok = not failures
        ok = ok and case_ok
        results.append(
            {
                "id": case["id"],
                "ok": case_ok,
                "failures": failures,
                "plan_type": payload.get("plan_type"),
                "execution_readiness": coverage.get("execution_readiness"),
                "coverage": coverage,
                "intent_kinds": sorted(kind for kind in kinds if isinstance(kind, str)),
            }
        )
    return {
        "ok": ok,
        "case_count": len(results),
        "results": results,
    }


if __name__ == "__main__":  # pragma: no cover - manual verification entrypoint
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Inspect or verify the Flow CAD intent planner.")
    parser.add_argument("message", nargs="*", help="Message to plan. Omit with --verify to run the matrix.")
    parser.add_argument("--verify", action="store_true", help="Run the built-in verification matrix.")
    args = parser.parse_args()

    if args.verify:
        report = verify_intent_planner_cases()
    else:
        report = plan_design_turn(" ".join(args.message))
    print(json.dumps(report, indent=2, sort_keys=True))
