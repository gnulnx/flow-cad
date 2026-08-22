"""Small immutable models shared by chat storage and provider adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


JsonObject = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ContextPacket:
    """CAD context captured at the instant a user submits a turn."""

    selected_part_uuid: str | None = None
    visible_occurrence_ids: tuple[str, ...] = ()
    artifact_hashes: Mapping[str, str] = field(default_factory=dict)
    camera: JsonObject = field(default_factory=dict)
    measurements: tuple[JsonObject, ...] = ()
    annotations: tuple[JsonObject, ...] = ()
    viewport_attachment: JsonObject | None = None
    viewer_revision: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "selected_part_uuid": self.selected_part_uuid,
            "visible_occurrence_ids": list(self.visible_occurrence_ids),
            "artifact_hashes": dict(self.artifact_hashes),
            "camera": dict(self.camera),
            "measurements": [dict(item) for item in self.measurements],
            "annotations": [dict(item) for item in self.annotations],
            "viewport_attachment": (
                dict(self.viewport_attachment) if self.viewport_attachment is not None else None
            ),
            "viewer_revision": self.viewer_revision,
        }


@dataclass(frozen=True, slots=True)
class ChatEvent:
    sequence: int
    event_id: str
    thread_id: str
    turn_id: str | None
    event_type: str
    created_at: str
    payload: JsonObject


@dataclass(frozen=True, slots=True)
class ChatThread:
    thread_id: str
    title: str
    created_at: str
    updated_at: str
    events: tuple[ChatEvent, ...]
