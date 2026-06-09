from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_COUNT_WORDS: dict[str, int] = {
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
_COUNT_WORD_PATTERN = "|".join(_COUNT_WORDS)
_NUMERIC_RE = r"\d+(?:\.\d+)?"

_DIMENSION_RE = re.compile(
    rf"(?P<length>{_NUMERIC_RE})\s*[x×]\s*(?P<width>{_NUMERIC_RE})\s*[x×]\s*(?P<thickness>{_NUMERIC_RE})",
    re.IGNORECASE,
)
_HOLE_COUNT_RE = re.compile(
    rf"\b(?P<count>{_COUNT_WORD_PATTERN}|\d+(?:\.\d+)?)\s+.*?\bholes?\b",
    re.IGNORECASE,
)
_HOLE_METRIC_RE = re.compile(rf"\bM(?P<diameter>{_NUMERIC_RE})\b", re.IGNORECASE)
_HOLE_MM_RE = re.compile(rf"\b(?P<diameter>{_NUMERIC_RE})\s*mm\s+clearance\s+holes?\b", re.IGNORECASE)
_HOLE_OFFSET_RE = re.compile(
    rf"(?P<offset>{_NUMERIC_RE})\s*mm\s+from\s+(?:the\s+)?(?P<edge>front|back|left|right|top|bottom|outside|inside)\s+edge",
    re.IGNORECASE,
)
_ANY_MM_RE = re.compile(rf"\b(?P<value>{_NUMERIC_RE})\s*mm\b", re.IGNORECASE)
_FACE_RE = re.compile(
    r"\b(?:on|at)\s+the\s+(?P<face>front|back|left|right|top|bottom|outside|inside)\s+face\b",
    re.IGNORECASE,
)
_LOUVER_COUNT_RE = re.compile(
    rf"\b(?P<count>{_COUNT_WORD_PATTERN}|\d+(?:\.\d+)?)\s+louvers?\b",
    re.IGNORECASE,
)
_LOUVER_SIZE_RE = re.compile(
    rf"\b(?P<width>{_NUMERIC_RE})\s*[x×]\s*(?P<height>{_NUMERIC_RE})\s*mm\b",
    re.IGNORECASE,
)
_LOUVER_PITCH_RE = re.compile(rf"\bpitch\s+(?P<pitch>{_NUMERIC_RE})\s*mm\b", re.IGNORECASE)
_SEGMENTS_RE = re.compile(r"\s+and\s+|,")

_DEFAULT_LENGTH = 120.0
_DEFAULT_WIDTH = 120.0
_DEFAULT_THICKNESS = 3.0
_DEFAULT_HOLE_OFFSET = 10.0
_DEFAULT_HOLE_MIRROR = 20.0
_DEFAULT_LOUVER_WIDTH = 10.0
_DEFAULT_LOUVER_HEIGHT = 3.0
_DEFAULT_LOUVER_PITCH = 12.0


def _to_float(value: str, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Unable to parse numeric value for {label}: {value}") from exc


def _parse_count(raw: str | None) -> int | None:
    if not raw:
        return None
    lowered = raw.lower()
    if lowered in _COUNT_WORDS:
        return _COUNT_WORDS[lowered]
    numeric = float(lowered)
    if numeric <= 0:
        return None
    return int(numeric)


@dataclass(frozen=True)
class PreviewCommandContext:
    part_id: str | None = None
    length: float | None = None
    width: float | None = None
    thickness: float | None = None
    selected_face: str | None = None
    front_face: str | None = None
    outside_face: str | None = None
    inside_face: str | None = None


@dataclass(frozen=True)
class PreviewOperation:
    name: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {"name": self.name, "parameters": dict(self.parameters)}


@dataclass(frozen=True)
class PreviewParseResult:
    command: str
    operations: tuple[PreviewOperation, ...]
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_payload(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "ok": self.ok,
            "operations": [operation.to_payload() for operation in self.operations],
            "warnings": list(self.warnings),
            "assumptions": list(self.assumptions),
            "errors": list(self.errors),
        }


def _segment_command(command: str) -> list[str]:
    return [segment.strip() for segment in _SEGMENTS_RE.split(command.lower()) if segment.strip()]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _resolve_context_dimensions(context: PreviewCommandContext | None) -> tuple[float, float, float]:
    if context is None:
        return _DEFAULT_LENGTH, _DEFAULT_WIDTH, _DEFAULT_THICKNESS
    return (
        float(context.length if context.length is not None else _DEFAULT_LENGTH),
        float(context.width if context.width is not None else _DEFAULT_WIDTH),
        float(context.thickness if context.thickness is not None else _DEFAULT_THICKNESS),
    )


def _resolve_face(
    alias: str | None,
    context: PreviewCommandContext | None,
    warnings: list[str],
    assumptions: list[str],
) -> str:
    if not alias:
        if context and context.selected_face:
            selected = context.selected_face.lower().strip()
            assumptions.append(f"Using selected face '{selected}' as default.")
            return selected
        warnings.append("No face was explicitly provided.")
        assumptions.append("Assuming 'top' as fallback face.")
        return "top"

    canonical = alias.strip().lower()
    if canonical in {"front", "back", "left", "right", "top", "bottom"}:
        return canonical
    if canonical == "outside":
        if context and context.outside_face:
            return context.outside_face.lower().strip()
        warnings.append("Outside face is ambiguous without context.")
        assumptions.append("Assuming outside = top.")
        return "top"
    if canonical == "inside":
        if context and context.inside_face:
            return context.inside_face.lower().strip()
        warnings.append("Inside face is ambiguous without context.")
        assumptions.append("Assuming inside = bottom.")
        return "bottom"

    if context and context.selected_face:
        selected = context.selected_face.lower().strip()
        assumptions.append(f"Could not resolve face '{alias}', using selected face '{selected}'.")
        return selected

    warnings.append(f"Could not resolve face alias '{alias}'.")
    assumptions.append("Assuming face 'top'.")
    return "top"


def _face_extents(face: str, length: float, width: float, thickness: float) -> tuple[float, float]:
    if face in {"top", "bottom"}:
        return length, width
    if face in {"front", "back"}:
        return length, thickness
    return width, thickness


def _edge_axis(face: str, edge: str) -> int:
    if face in {"top", "bottom"}:
        return 1 if edge in {"front", "back"} else 0
    if face in {"front", "back"}:
        return 1 if edge in {"front", "back"} else 0
    return 0 if edge in {"front", "back"} else 1


def _mirrored_positions(axis_extent: float, count: int) -> list[float]:
    if count <= 1:
        return [axis_extent / 2.0]
    if count == 2:
        offset = _clamp(_DEFAULT_HOLE_MIRROR / 2.0, 0.0, axis_extent / 4.0)
        return [axis_extent / 2.0 - offset, axis_extent / 2.0 + offset]
    step = max(1.0, axis_extent / max(1, count - 1))
    return [idx * step for idx in range(count)]


def _parse_dimensions(segment: str) -> tuple[float, float, float] | None:
    match = _DIMENSION_RE.search(segment)
    if not match:
        return None
    length = _to_float(match.group("length"), "length")
    width = _to_float(match.group("width"), "width")
    thickness = _to_float(match.group("thickness"), "thickness")
    if length <= 0 or width <= 0 or thickness <= 0:
        raise ValueError("Panel dimensions must be positive.")
    return length, width, thickness


def _parse_hole_segment(
    segment: str,
    length: float,
    width: float,
    thickness: float,
    context: PreviewCommandContext | None,
    warnings: list[str],
    assumptions: list[str],
) -> tuple[list[PreviewOperation], bool]:
    count = _parse_count(_HOLE_COUNT_RE.search(segment).group("count")) if _HOLE_COUNT_RE.search(segment) else None
    if count is None:
        return [], False
    if count < 1:
        warnings.append("Hole count must be positive.")
        return [], True

    metric_match = _HOLE_METRIC_RE.search(segment)
    mm_clearance_match = _HOLE_MM_RE.search(segment)
    if not metric_match and not mm_clearance_match:
        mm = _ANY_MM_RE.search(segment)
        if not mm:
            warnings.append("Could not parse hole diameter; skipping hole operation.")
            return [], True
        diameter = _to_float(mm.group("value"), "hole diameter")
    elif metric_match:
        diameter = _to_float(metric_match.group("diameter"), "hole diameter")
    else:
        diameter = _to_float(mm_clearance_match.group("diameter"), "hole diameter")  # type: ignore[union-attr]

    if diameter <= 0:
        warnings.append("Hole diameter must be positive.")
        return [], True

    edge_match = _HOLE_OFFSET_RE.search(segment)
    if edge_match:
        edge = edge_match.group("edge").lower()
        offset = _to_float(edge_match.group("offset"), "hole offset")
    else:
        edge = "front"
        offset = _DEFAULT_HOLE_OFFSET
        warnings.append("Could not find edge offset for holes.")
        assumptions.append("Using default 10 mm offset.")

    face_match = _FACE_RE.search(segment)
    face = _resolve_face(face_match.group("face") if face_match else None, context, warnings, assumptions)

    u_extent, v_extent = _face_extents(face, length, width, thickness)
    if u_extent <= 0 or v_extent <= 0:
        warnings.append("Invalid face extents; falling back to defaults for coordinates.")
        assumptions.append("Using default panel extents 120x120x3 mm.")
        u_extent, v_extent = _DEFAULT_LENGTH, _DEFAULT_WIDTH

    axis = _edge_axis(face, edge)
    if axis == 0:
        x = _clamp(offset, 0.0, u_extent)
        mirror_extent = v_extent
        positions_on_y = _mirrored_positions(mirror_extent, count)
        positions: list[tuple[float, float]] = [(x, _clamp(value, 0.0, v_extent)) for value in positions_on_y]
    else:
        y = _clamp(offset, 0.0, v_extent)
        mirror_extent = u_extent
        positions_on_x = _mirrored_positions(mirror_extent, count)
        positions = [(_clamp(value, 0.0, u_extent), y) for value in positions_on_x]

    if count == 2:
        assumptions.append(f"Interpreting 'two holes' as mirrored pair on face '{face}'.")

    operations: list[PreviewOperation] = []
    for index, (x_pos, y_pos) in enumerate(positions, start=1):
        operations.append(
            PreviewOperation(
                name="add_hole",
                parameters={
                    "face": face,
                    "x": float(x_pos),
                    "y": float(y_pos),
                    "diameter": float(diameter),
                    "through": True,
                    "pair_index": index,
                },
            )
        )
    return operations, True


def _parse_louver_segment(
    segment: str,
    length: float,
    width: float,
    thickness: float,
    context: PreviewCommandContext | None,
    warnings: list[str],
    assumptions: list[str],
) -> tuple[list[PreviewOperation], bool]:
    match = _LOUVER_COUNT_RE.search(segment)
    if not match:
        return [], False
    count = _parse_count(match.group("count"))
    if count is None:
        warnings.append("Louver count must be parseable.")
        return [], True
    if count < 1:
        warnings.append("Louver count must be positive.")
        return [], True

    size_match = _LOUVER_SIZE_RE.search(segment)
    if size_match:
        louver_width = _to_float(size_match.group("width"), "louver width")
        louver_height = _to_float(size_match.group("height"), "louver height")
    else:
        louver_width = _DEFAULT_LOUVER_WIDTH
        louver_height = _DEFAULT_LOUVER_HEIGHT
        assumptions.append("Louver width/height unspecified; using 10x3 mm.")

    if louver_width <= 0 or louver_height <= 0:
        warnings.append("Louver dimensions must be positive.")
        return [], True

    pitch_match = _LOUVER_PITCH_RE.search(segment)
    pitch = _to_float(pitch_match.group("pitch"), "louver pitch") if pitch_match else _DEFAULT_LOUVER_PITCH
    if not pitch_match:
        assumptions.append("Louver pitch unspecified; defaulting 12 mm.")
    if pitch <= 0:
        warnings.append("Louver pitch must be positive.")
        return [], True

    face_match = _FACE_RE.search(segment)
    face = _resolve_face(face_match.group("face") if face_match else None, context, warnings, assumptions)

    u_extent, v_extent = _face_extents(face, length, width, thickness)
    if u_extent <= 0 or v_extent <= 0:
        warnings.append("Invalid face extents; falling back to defaults for louver center.")
        assumptions.append("Using default panel extents 120x120x3 mm.")
        u_extent, v_extent = _DEFAULT_LENGTH, _DEFAULT_WIDTH

    return (
        [
            PreviewOperation(
                name="add_louver_pattern",
                parameters={
                    "face": face,
                    "count": int(count),
                    "pitch": pitch,
                    "x": u_extent / 2.0,
                    "y": v_extent / 2.0,
                    "width": float(louver_width),
                    "height": float(louver_height),
                    "angle": 0.0,
                },
            )
        ],
        True,
    )


def parse_panel_command(
    command: str,
    context: PreviewCommandContext | None = None,
) -> PreviewParseResult:
    normalized = command.strip()
    if not normalized:
        return PreviewParseResult(
            command=command,
            operations=(),
            warnings=("Command was empty.",),
            assumptions=(),
            errors=("No command text.",),
        )

    warnings: list[str] = []
    assumptions: list[str] = []
    errors: list[str] = []
    operations: list[PreviewOperation] = []

    length, width, thickness = _resolve_context_dimensions(context)
    saw_dimension = False

    for segment in _segment_command(normalized):
        parsed_dims = _parse_dimensions(segment)
        if parsed_dims is not None:
            length, width, thickness = parsed_dims
            saw_dimension = True
            operations.append(
                PreviewOperation(
                    "create_box",
                    {"length": length, "width": width, "height": thickness},
                )
            )
            continue

        hole_ops, hole_parsed = _parse_hole_segment(
            segment,
            length,
            width,
            thickness,
            context,
            warnings,
            assumptions,
        )
        if hole_ops:
            operations.extend(hole_ops)
        if hole_parsed:
            continue

        louver_ops, louver_parsed = _parse_louver_segment(
            segment,
            length,
            width,
            thickness,
            context,
            warnings,
            assumptions,
        )
        if louver_ops:
            operations.extend(louver_ops)
        if louver_parsed:
            continue

        if "hole" in segment or "louver" in segment or "panel" in segment:
            warnings.append(f"Could not parse segment deterministically: {segment}")
            errors.append("Unsupported command segment.")

    if not operations:
        errors.append("Unsupported command intent: no supported panel operation found.")

    if context is None and not saw_dimension and any(
        op.name in {"add_hole", "add_louver_pattern"} for op in operations
    ):
        warnings.append("No selected-part context was provided.")
        assumptions.append("Used default 120x120x3 mm panel extents and conservative face assumptions.")

    return PreviewParseResult(
        command=command,
        operations=tuple(operations),
        warnings=tuple(warnings),
        assumptions=tuple(assumptions),
        errors=tuple(errors),
    )
