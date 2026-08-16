from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


BUILD_PROFILE_SCHEMA_VERSION = 1
LATEST_BUILD_PROFILE = "latest-build-profile.json"
LATEST_VALIDATOR_PROFILE = "latest-validator-profile.json"


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _isoformat(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _round_ms(value: float) -> float:
    return round(value * 1000.0, 3)


@dataclass(frozen=True)
class ProfileEvent:
    phase: str
    label: str
    duration_ms: float
    status: str
    started_at: str
    part_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "phase": self.phase,
            "label": self.label,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "started_at": self.started_at,
        }
        if self.part_id:
            data["part_id"] = self.part_id
        if self.metadata:
            data["metadata"] = self.metadata
        return data


@dataclass(frozen=True)
class BuildProfilePaths:
    profile_path: Path
    latest_path: Path


class FlowCadProfiler:
    def __init__(
        self,
        *,
        project_id: str,
        project_root: Path,
        command: str,
        build_profile: str | None = None,
    ) -> None:
        self.profile_id = uuid4().hex[:12]
        self.project_id = project_id
        self.project_root = project_root.resolve()
        self.command = command
        self.build_profile = build_profile
        self.started_at = _utc_now()
        self._started_perf = time.perf_counter()
        self.finished_at: datetime | None = None
        self.status = "running"
        self.events: list[ProfileEvent] = []

    @contextmanager
    def measure(
        self,
        phase: str,
        label: str,
        *,
        part_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[None]:
        started_at = _utc_now()
        started_perf = time.perf_counter()
        try:
            yield
        except Exception as exc:
            event_metadata = dict(metadata or {})
            event_metadata["error_type"] = type(exc).__name__
            event_metadata["error"] = str(exc)
            self.events.append(
                ProfileEvent(
                    phase=phase,
                    label=label,
                    duration_ms=_round_ms(time.perf_counter() - started_perf),
                    status="failed",
                    started_at=_isoformat(started_at),
                    part_id=part_id,
                    metadata=event_metadata,
                )
            )
            raise
        self.events.append(
            ProfileEvent(
                phase=phase,
                label=label,
                duration_ms=_round_ms(time.perf_counter() - started_perf),
                status="ok",
                started_at=_isoformat(started_at),
                part_id=part_id,
                metadata=dict(metadata or {}),
            )
        )

    def record_skip(
        self,
        phase: str,
        label: str,
        *,
        part_id: str | None = None,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event_metadata = dict(metadata or {})
        event_metadata["reason"] = reason
        self.events.append(
            ProfileEvent(
                phase=phase,
                label=label,
                duration_ms=0.0,
                status="skipped",
                started_at=_isoformat(_utc_now()),
                part_id=part_id,
                metadata=event_metadata,
            )
        )

    def finish(self, status: str) -> None:
        if self.finished_at is None:
            self.finished_at = _utc_now()
        self.status = status

    @property
    def duration_ms(self) -> float:
        if self.finished_at is None:
            return _round_ms(time.perf_counter() - self._started_perf)
        return round((self.finished_at - self.started_at).total_seconds() * 1000.0, 3)

    def to_dict(self) -> dict[str, Any]:
        events = [event.to_dict() for event in self.events]
        data: dict[str, Any] = {
            "schema_version": BUILD_PROFILE_SCHEMA_VERSION,
            "profile_id": self.profile_id,
            "project_id": self.project_id,
            "project_root": str(self.project_root),
            "command": self.command,
            "started_at": _isoformat(self.started_at),
            "finished_at": _isoformat(self.finished_at) if self.finished_at else None,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "events": events,
            "summary": summarize_profile_events(events),
        }
        if self.build_profile:
            data["build_profile"] = self.build_profile
        return data


def summarize_profile_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, float] = {}
    for event in events:
        phase = str(event["phase"])
        totals[phase] = round(totals.get(phase, 0.0) + float(event["duration_ms"]), 3)

    return {
        "event_count": len(events),
        "totals_by_phase_ms": dict(sorted(totals.items(), key=lambda item: item[1], reverse=True)),
        "slowest_events": slowest_profile_events(events),
    }


def slowest_profile_events(events: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    aggregate_phases = {"build_total"}
    candidates = [
        event
        for event in events
        if event.get("phase") not in aggregate_phases and float(event.get("duration_ms", 0.0)) > 0
    ]
    return sorted(candidates, key=lambda event: float(event["duration_ms"]), reverse=True)[:limit]


def build_profile_dir(local_state_dir: Path) -> Path:
    return local_state_dir / "profiles"


def write_build_profile(profiler: FlowCadProfiler, local_state_dir: Path) -> BuildProfilePaths:
    profile_dir = build_profile_dir(local_state_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    timestamp = profiler.started_at.strftime("%Y%m%dT%H%M%SZ")
    profile_path = profile_dir / f"build-profile-{timestamp}-{profiler.profile_id}.json"
    latest_path = profile_dir / LATEST_BUILD_PROFILE
    payload = json.dumps(profiler.to_dict(), indent=2, sort_keys=True) + "\n"
    profile_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    return BuildProfilePaths(profile_path=profile_path, latest_path=latest_path)


def write_validator_profile(profiler: FlowCadProfiler, local_state_dir: Path) -> BuildProfilePaths:
    profile_dir = build_profile_dir(local_state_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    timestamp = profiler.started_at.strftime("%Y%m%dT%H%M%SZ")
    profile_path = profile_dir / f"validator-profile-{timestamp}-{profiler.profile_id}.json"
    latest_path = profile_dir / LATEST_VALIDATOR_PROFILE
    payload = json.dumps(profiler.to_dict(), indent=2, sort_keys=True) + "\n"
    profile_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")
    return BuildProfilePaths(profile_path=profile_path, latest_path=latest_path)


def latest_build_profile_path(local_state_dir: Path) -> Path:
    return build_profile_dir(local_state_dir) / LATEST_BUILD_PROFILE


def latest_validator_profile_path(local_state_dir: Path) -> Path:
    return build_profile_dir(local_state_dir) / LATEST_VALIDATOR_PROFILE


def load_latest_build_profile(local_state_dir: Path) -> dict[str, Any] | None:
    candidates = [
        path
        for path in (
            latest_build_profile_path(local_state_dir),
            latest_validator_profile_path(local_state_dir),
        )
        if path.exists()
    ]
    if not candidates:
        return None
    path = max(candidates, key=lambda candidate: candidate.stat().st_mtime_ns)
    return json.loads(path.read_text(encoding="utf-8"))


def format_profile_summary(profile: dict[str, Any], *, limit: int = 5) -> str:
    summary = profile.get("summary", {})
    totals = summary.get("totals_by_phase_ms", {})
    slowest = slowest_profile_events(list(profile.get("events", [])), limit=limit)
    command = str(profile.get("command", ""))
    title = "Build profile" if "cad build" in command else "Flow CAD profile"
    lines = [
        f"{title} {profile.get('profile_id', '<unknown>')} ({profile.get('status', 'unknown')})",
        f"Project: {profile.get('project_id', '<unknown>')}",
        f"Command: {command or '<unknown>'}",
        f"Started: {profile.get('started_at', '<unknown>')}",
        f"Total: {float(profile.get('duration_ms', 0.0)):.1f} ms",
        "",
        "Phase totals:",
    ]
    if totals:
        for phase, duration_ms in totals.items():
            lines.append(f"- {phase}: {float(duration_ms):.1f} ms")
    else:
        lines.append("- no timed events")

    lines.extend(["", "Slowest operations:"])
    if slowest:
        for event in slowest:
            part = f" [{event['part_id']}]" if event.get("part_id") else ""
            metadata = event.get("metadata", {}) if isinstance(event.get("metadata"), dict) else {}
            budget = " over budget" if metadata.get("over_budget") else ""
            lines.append(
                f"- {event['phase']}{part}: {event['label']} "
                f"({float(event['duration_ms']):.1f} ms, {event['status']}{budget})"
            )
    else:
        lines.append("- no timed operations")
    return "\n".join(lines)
