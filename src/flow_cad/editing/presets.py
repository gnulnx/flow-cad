from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HolePreset:
    id: str
    label: str
    diameter_mm: float

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "diameter_mm": self.diameter_mm,
        }


HOLE_PRESETS: dict[str, HolePreset] = {
    "m4_clearance": HolePreset("m4_clearance", "M4 clearance", 4.5),
    "m5_clearance": HolePreset("m5_clearance", "M5 clearance", 5.5),
}


def hole_preset(preset_id: str) -> HolePreset:
    try:
        return HOLE_PRESETS[preset_id]
    except KeyError as exc:
        raise ValueError(f"Unsupported hole preset: {preset_id}") from exc


def hole_presets_payload() -> dict[str, dict[str, Any]]:
    return {
        preset_id: preset.to_payload()
        for preset_id, preset in HOLE_PRESETS.items()
    }
