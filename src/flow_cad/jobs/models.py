"""Immutable, transport-friendly background-job contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


JsonObject = Mapping[str, Any]


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.CANCELLED}


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: str
    request_id: str
    kind: str
    state: JobState
    phase: str
    progress: float
    message: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None
    elapsed_seconds: float
    cancellation_requested: bool
    payload: JsonObject = field(default_factory=dict)
    result: JsonObject | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "request_id": self.request_id,
            "kind": self.kind,
            "state": self.state.value,
            "phase": self.phase,
            "progress": self.progress,
            "message": self.message,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": self.elapsed_seconds,
            "cancellation_requested": self.cancellation_requested,
            "payload": dict(self.payload),
            "result": dict(self.result) if self.result is not None else None,
            "error": self.error,
        }


@dataclass(frozen=True, slots=True)
class JobEvent:
    sequence: int
    event_id: str
    job_id: str
    event_type: str
    state: JobState
    phase: str
    progress: float
    message: str | None
    elapsed_seconds: float
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event_id": self.event_id,
            "job_id": self.job_id,
            "event_type": self.event_type,
            "state": self.state.value,
            "phase": self.phase,
            "progress": self.progress,
            "message": self.message,
            "elapsed_seconds": self.elapsed_seconds,
            "updated_at": self.updated_at,
        }
