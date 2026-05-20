"""STEP file helpers."""

from __future__ import annotations

import re
from pathlib import Path


STABLE_STEP_TIMESTAMP = "2000-01-01T00:00:00"
_FILE_NAME_TIMESTAMP_RE = re.compile(
    r"(FILE_NAME\('[^']*',\s*')([^']*)(')"
)


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
