"""STEP file helpers."""

from __future__ import annotations

import re
from pathlib import Path


STABLE_STEP_TIMESTAMP = "2000-01-01T00:00:00"
_FILE_NAME_TIMESTAMP_RE = re.compile(
    r"(FILE_NAME\('[^']*',\s*')([^']*)(')"
)
_GENERATED_OCCURRENCE_ID_RE = re.compile(
    r"(^#\d+\s*=\s*NEXT_ASSEMBLY_USAGE_OCCURRENCE\(\s*')([0-9]+)(')",
    re.MULTILINE,
)


def normalize_generated_occurrence_ids(path: Path) -> bool:
    """Remove OCCT's process-global counter offset from fresh generated STEP.

    Only use on this runtime's new build123d exports, never imported/reference
    STEP. OCCT numbers assembly usage IDs across exports in a warm process. The
    IDs are strings, not the #entity references defining topology/placements.
    Starting each export at one preserves cold-export bytes and relative IDs.
    Labels, relationships, geometry and entity references remain untouched.
    """
    text = path.read_text(encoding="utf-8")
    ids = [int(match.group(2)) for match in _GENERATED_OCCURRENCE_ID_RE.finditer(text)]
    if not ids or min(ids) <= 1:
        return False
    offset = min(ids) - 1
    normalized = _GENERATED_OCCURRENCE_ID_RE.sub(
        lambda match: f"{match.group(1)}{int(match.group(2)) - offset}{match.group(3)}",
        text,
    )
    path.write_text(normalized, encoding="utf-8")
    return True


def normalize_step_file(path: Path, timestamp: str = STABLE_STEP_TIMESTAMP) -> bool:
    """Normalize volatile STEP header fields in-place.

    Open CASCADE writes the current export time into the FILE_NAME header, which
    makes regenerated STEP files appear changed even when geometry is identical.
    Keep generated STEP files trackable by replacing that volatile timestamp with
    a stable value. Geometry and topology DATA sections are untouched.
    """
    text = path.read_text(encoding="utf-8")
    normalized, count = _FILE_NAME_TIMESTAMP_RE.subn(rf"\g<1>{timestamp}\g<3>", text, count=1)
    if count == 0 or normalized == text:
        return False
    path.write_text(normalized, encoding="utf-8")
    return True
