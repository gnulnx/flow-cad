from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flow_cad.viewer.service import ViewerError, ViewerService


class ThreadStorageError(ViewerError):
    """Base storage error for design thread operations."""


class ThreadNotFoundError(ThreadStorageError):
    status_code = 404


class ThreadValidationError(ThreadStorageError):
    status_code = 400


DESIGN_THREADS_SCHEMA_VERSION = 1
THREAD_SCHEMA_VERSION = 1
THREAD_MESSAGE_SCHEMA_VERSION = 1
THREAD_CONTEXT_SNAPSHOT_SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in items:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _safe_thread_id(value: str, *, fallback: str = "thread") -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    slug = slug.strip("._-")
    if not slug:
        slug = fallback
    return slug[:80]


def _ordered_json_files(path: Path) -> list[Path]:
    return sorted(path.glob("*.json"))


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="tmp-", suffix=".json", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        tmp_path.replace(path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        handle.write("\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    lines: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            lines.append(payload)
    return lines


def _normalize_part_ids(value: Any) -> list[str]:
    return _unique_preserve_order(_as_list(value))


def _normalize_tags(value: Any) -> list[str]:
    return _unique_preserve_order([str(tag).strip() for tag in _as_list(value) if str(tag).strip()])


def _snapshot_has_view_image(snapshot: dict[str, Any]) -> bool:
    viewer_state = snapshot.get("viewer_state")
    if not isinstance(viewer_state, dict):
        return False
    screenshot = viewer_state.get("viewport_screenshot") or viewer_state.get("screenshot")
    return isinstance(screenshot, dict) and bool(screenshot.get("data_url") or screenshot.get("attachment_id"))


def _default_thread_payload(thread_id: str, title: str | None, *, now: str) -> dict[str, Any]:
    normalized_title = title.strip() if isinstance(title, str) else ""
    return {
        "schema_version": THREAD_SCHEMA_VERSION,
        "thread_id": thread_id,
        "title": normalized_title or f"Design Thread {thread_id}",
        "status": "active",
        "archived": False,
        "summary": "",
        "created_at": now,
        "updated_at": now,
        "tags": [],
        "linked_part_ids": [],
        "linked_draft_transaction_tokens": [],
        "accepted_artifact_paths": [],
        "warnings": [],
        "message_count": 0,
        "snapshot_count": 0,
    }


@dataclass(frozen=True)
class PartFact:
    part_id: str
    found: bool
    geometry_authority: str | None
    capabilities: dict[str, Any]
    warnings: list[str]
    source_context_available: bool
    artifact_format: str | None
    artifact_path: str | None

    @classmethod
    def missing(cls, part_id: str) -> "PartFact":
        return cls(
            part_id=part_id,
            found=False,
            geometry_authority=None,
            capabilities={},
            warnings=["Part id not found in project",],
            source_context_available=False,
            artifact_format=None,
            artifact_path=None,
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "part_id": self.part_id,
            "found": self.found,
            "source_context_available": self.source_context_available,
        }
        if self.found:
            payload.update(
                {
                    "geometry_authority": self.geometry_authority,
                    "capabilities": self.capabilities,
                    "warnings": self.warnings,
                    "artifact_format": self.artifact_format,
                    "artifact_path": self.artifact_path,
                }
            )
        else:
            payload["warnings"] = self.warnings
        return payload


class DesignThreadService:
    def __init__(self, viewer_service: ViewerService):
        self.viewer_service = viewer_service
        self.root = viewer_service.project_root
        self.threads_root = viewer_service.project.paths.local_state / "design-threads"

    def list_threads(self) -> dict[str, Any]:
        index = self._load_index()
        threads = sorted(index.get("threads", []), key=lambda value: str(value.get("updated_at") or ""), reverse=True)
        return {
            "schema_version": DESIGN_THREADS_SCHEMA_VERSION,
            "updated_at": _utc_now(),
            "count": len(threads),
            "threads": threads,
        }

    def create_thread(self, payload: dict[str, Any]) -> dict[str, Any]:
        requested_id = str(payload.get("thread_id") or f"thread-{uuid.uuid4().hex[:8]}")
        thread_id = _safe_thread_id(requested_id)
        now = _utc_now()
        thread = _default_thread_payload(thread_id, str(payload.get("title") or ""), now=now)

        if isinstance(payload.get("title"), str):
            thread["title"] = str(payload["title"]).strip()
        thread["summary"] = str(payload.get("summary") or "")
        thread["tags"] = _normalize_tags(payload.get("tags"))
        thread["linked_part_ids"] = _normalize_part_ids(payload.get("linked_part_ids"))
        thread["linked_draft_transaction_tokens"] = _normalize_part_ids(payload.get("linked_draft_transaction_tokens"))
        thread["accepted_artifact_paths"] = [
            str(path).strip() for path in _as_list(payload.get("accepted_artifact_paths")) if str(path).strip()
        ]

        index = self._load_index()
        existing = {entry.get("thread_id") for entry in index.get("threads", []) if isinstance(entry, dict)}
        if thread_id in existing:
            thread_id = _safe_thread_id(f"{thread_id}-{uuid.uuid4().hex[:6]}")
            thread["thread_id"] = thread_id

        self._write_thread(thread_id, thread)
        index.setdefault("threads", []).append(
            self._thread_summary(thread_id, thread["title"], thread["status"], thread["archived"], thread["updated_at"])
        )
        self._write_index(index)
        return thread

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        thread = self._require_thread(thread_id)
        thread_id = thread["thread_id"]
        messages = _read_jsonl(self._thread_messages_path(thread_id))
        snapshots = self._thread_snapshots(thread_id)
        thread["messages"] = messages
        thread["context_snapshots"] = snapshots
        thread["message_count"] = len(messages)
        thread["snapshot_count"] = len(snapshots)
        return thread

    def patch_thread(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        thread = self._require_thread(thread_id)
        updated = False

        for field in payload:
            if field not in {
                "title",
                "summary",
                "tags",
                "status",
                "archived",
                "linked_part_ids",
                "linked_draft_transaction_tokens",
                "accepted_artifact_paths",
            }:
                continue
            if field == "title":
                value = str(payload[field]).strip() if payload[field] is not None else ""
                thread["title"] = value
                updated = True
            elif field == "summary":
                thread["summary"] = str(payload[field] or "")
                updated = True
            elif field == "status":
                thread["status"] = str(payload[field] or thread.get("status", "active"))
                updated = True
            elif field == "archived":
                thread["archived"] = bool(payload[field])
                updated = True
            elif field == "tags":
                thread["tags"] = _normalize_tags(payload[field])
                updated = True
            elif field in {"linked_part_ids", "linked_draft_transaction_tokens"}:
                thread[field] = _normalize_part_ids(payload[field])
                updated = True
            elif field == "accepted_artifact_paths":
                thread[field] = [
                    str(path).strip() for path in _as_list(payload[field]) if str(path).strip()
                ]
                updated = True

        if updated:
            thread["updated_at"] = _utc_now()
        self._write_thread(thread_id, thread)
        self._sync_index_entry(thread_id, thread)
        return self.get_thread(thread_id)

    def append_message(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        thread = self._require_thread(thread_id)
        message = {
            "schema_version": THREAD_MESSAGE_SCHEMA_VERSION,
            "message_id": f"msg_{uuid.uuid4().hex}",
            "thread_id": thread["thread_id"],
            "created_at": _utc_now(),
            "type": str(payload.get("type") or "user_message"),
            "role": str(payload.get("role") or "user"),
            "content": payload.get("content", payload.get("text") or payload.get("message")),
            "attachments": _as_list(payload.get("attachments")),
            "metadata": payload.get("metadata", {}),
        }
        if message["content"] is None:
            raise ThreadValidationError("message content is required")

        _append_jsonl(self._thread_messages_path(thread_id), message)

        thread["updated_at"] = _utc_now()
        thread["message_count"] = thread.get("message_count", 0) + 1
        self._write_thread(thread_id, thread)
        self._sync_index_entry(thread_id, thread)
        return message

    def chat_turn(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("message", payload.get("content"))
        if not isinstance(text, str) or not text.strip():
            raise ThreadValidationError("chat message content is required")

        context_payload = payload.get("context_snapshot")
        snapshot: dict[str, Any] | None = None
        metadata: dict[str, Any] = {}
        if isinstance(context_payload, dict):
            snapshot = self.create_context_snapshot(thread_id, context_payload)
            metadata["context_snapshot_id"] = snapshot["snapshot_id"]
            if _snapshot_has_view_image(snapshot):
                metadata["viewport_screenshot"] = True

        user_message = self.append_message(
            thread_id,
            {
                "type": "user_message",
                "role": "user",
                "content": text.strip(),
                "metadata": metadata,
            },
        )
        assistant_message = self.append_message(
            thread_id,
            {
                "type": "assistant_message",
                "role": "assistant",
                "content": self._assistant_reply(text.strip(), snapshot),
                "metadata": {
                    "runtime": "flow_cad_stub",
                    "runtime_status": "configured_stub",
                    **({"context_snapshot_id": snapshot["snapshot_id"]} if snapshot else {}),
                },
            },
        )
        return {
            "thread_id": thread_id,
            "messages": [user_message, assistant_message],
            "context_snapshot": snapshot,
            "thread": self.get_thread(thread_id),
        }

    def create_context_snapshot(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        thread = self._require_thread(thread_id)
        snapshot_id = _safe_thread_id(
            f"snap-{payload.get('snapshot_id') or uuid.uuid4().hex[:12]}",
            fallback="snapshot",
        )
        now = _utc_now()
        viewer_state = dict(payload)
        visible_part_ids = _normalize_part_ids(viewer_state.pop("visible_part_ids", []))
        selected_part_ids = _normalize_part_ids(viewer_state.pop("selected_part_ids", []))

        expanded = self._expand_snapshot_state(
            visible_part_ids=visible_part_ids,
            selected_part_ids=selected_part_ids,
            draft_transaction_token=str(payload.get("draft_transaction_token") or ""),
            viewer_state=viewer_state,
        )

        snapshot = {
            "schema_version": THREAD_CONTEXT_SNAPSHOT_SCHEMA_VERSION,
            "thread_id": thread["thread_id"],
            "snapshot_id": snapshot_id,
            "created_at": now,
            "viewer_state": payload,
            "project": self.viewer_service.runtime_context(),
            "warnings": expanded["warnings"],
            "parts": {
                "visible": [self._part_facts(part_id).to_payload() for part_id in visible_part_ids],
                "selected": [self._part_facts(part_id).to_payload() for part_id in selected_part_ids],
            },
            **expanded,
        }

        snapshot_path = self._thread_snapshot_path(thread_id, snapshot_id)
        _write_json_atomic(snapshot_path, snapshot)

        thread["updated_at"] = now
        thread["snapshot_count"] = thread.get("snapshot_count", 0) + 1
        self._write_thread(thread_id, thread)
        self._sync_index_entry(thread_id, thread)

        # Keep a stable attachments directory for future snapshots with media sidecars.
        (self._thread_attachments_dir(thread_id)).mkdir(parents=True, exist_ok=True)
        return snapshot

    def _expand_snapshot_state(
        self,
        *,
        visible_part_ids: list[str],
        selected_part_ids: list[str],
        draft_transaction_token: str,
        viewer_state: dict[str, Any],
    ) -> dict[str, Any]:
        warnings: list[str] = []
        draft_state: dict[str, Any] | None = None
        if draft_transaction_token:
            try:
                draft_state = self.viewer_service.draft_transaction_status(draft_transaction_token)
            except ViewerError as exc:
                warnings.append(str(exc))
                draft_state = {
                    "token": draft_transaction_token,
                    "status": "unavailable",
                    "error": str(exc),
                }

        return {
            "visible_part_ids": visible_part_ids,
            "selected_part_ids": selected_part_ids,
            "measurements": viewer_state.get("measurements", []),
            "draft_transaction": draft_state or None,
            "warnings": warnings,
            "viewport": {
                "size": viewer_state.get("viewport_size")
                or viewer_state.get("viewport")
                or viewer_state.get("size"),
            },
            "camera": viewer_state.get("camera"),
        }

    def _assistant_reply(self, message: str, snapshot: dict[str, Any] | None) -> str:
        context_bits: list[str] = []
        if snapshot is not None:
            selected = snapshot.get("selected_part_ids", [])
            visible = snapshot.get("visible_part_ids", [])
            project = snapshot.get("project", {})
            if isinstance(selected, list):
                context_bits.append(f"{len(selected)} selected")
            if isinstance(visible, list):
                context_bits.append(f"{len(visible)} visible")
            if isinstance(project, dict) and project.get("active_assembly_id"):
                context_bits.append(f"assembly {project['active_assembly_id']}")
            if _snapshot_has_view_image(snapshot):
                context_bits.append("viewport image attached")

        context_text = f" with context ({', '.join(context_bits)})" if context_bits else ""
        return (
            f"I received your design note{context_text}: {message}\n\n"
            "The Flow CAD chat runtime is using the built-in stub responder right now. "
            "The thread, message, and view context are persisted so a local model adapter can take over this same turn contract."
        )

    def _part_facts(self, part_id: str) -> PartFact:
        try:
            part_payload = self.viewer_service.get_part_payload(part_id)
        except ViewerError:
            return PartFact.missing(part_id)

        try:
            source_context = self.viewer_service.part_source_context(part_id)
            source_available = bool(source_context.get("available"))
        except ViewerError:
            source_available = False

        return PartFact(
            part_id=part_id,
            found=True,
            geometry_authority=part_payload.get("geometry_authority"),
            capabilities=part_payload.get("capabilities") or {},
            warnings=list(part_payload.get("warnings") or []),
            source_context_available=source_available,
            artifact_format=part_payload.get("artifact_format"),
            artifact_path=part_payload.get("artifact_path"),
        )

    def _load_index(self) -> dict[str, Any]:
        payload = _read_json(self._index_path())
        if payload is None:
            return {
                "schema_version": DESIGN_THREADS_SCHEMA_VERSION,
                "threads": [],
            }
        threads = payload.get("threads")
        if not isinstance(threads, list):
            threads = []
        if payload.get("schema_version") != DESIGN_THREADS_SCHEMA_VERSION:
            return {
                "schema_version": DESIGN_THREADS_SCHEMA_VERSION,
                "threads": threads,
            }
        payload["threads"] = threads
        return payload

    def _write_index(self, index_payload: dict[str, Any]) -> None:
        index_payload["schema_version"] = DESIGN_THREADS_SCHEMA_VERSION
        _write_json_atomic(self._index_path(), index_payload)

    def _index_path(self) -> Path:
        return self.threads_root / "index.json"

    def _thread_dir(self, thread_id: str) -> Path:
        safe_thread_id = _safe_thread_id(thread_id, fallback="thread")
        return self.threads_root / safe_thread_id

    def _thread_path(self, thread_id: str) -> Path:
        return self._thread_dir(thread_id) / "thread.json"

    def _thread_messages_path(self, thread_id: str) -> Path:
        return self._thread_dir(thread_id) / "messages.jsonl"

    def _thread_snapshots_dir(self, thread_id: str) -> Path:
        return self._thread_dir(thread_id) / "context-snapshots"

    def _thread_attachments_dir(self, thread_id: str) -> Path:
        return self._thread_dir(thread_id) / "attachments"

    def _thread_snapshot_path(self, thread_id: str, snapshot_id: str) -> Path:
        safe_snapshot_id = _safe_thread_id(snapshot_id, fallback="snapshot")
        return self._thread_snapshots_dir(thread_id) / f"{safe_snapshot_id}.json"

    def _thread_snapshots(self, thread_id: str) -> list[dict[str, Any]]:
        snapshot_dir = self._thread_snapshots_dir(thread_id)
        return [
            _read_json(path) or {"schema_version": THREAD_CONTEXT_SNAPSHOT_SCHEMA_VERSION, "snapshot_id": path.stem}
            for path in _ordered_json_files(snapshot_dir)
            if path.is_file()
        ]

    def _write_thread(self, thread_id: str, thread_payload: dict[str, Any]) -> None:
        thread_payload["schema_version"] = THREAD_SCHEMA_VERSION
        _write_json_atomic(self._thread_path(thread_id), thread_payload)

    def _read_thread(self, thread_id: str) -> dict[str, Any] | None:
        payload = _read_json(self._thread_path(thread_id))
        if payload is None:
            return None
        if payload.get("schema_version") != THREAD_SCHEMA_VERSION:
            return None
        return payload

    def _require_thread(self, thread_id: str) -> dict[str, Any]:
        safe_thread_id = _safe_thread_id(thread_id, fallback="thread")
        payload = self._read_thread(safe_thread_id)
        if payload is None:
            raise ThreadNotFoundError(f"Thread not found: {thread_id}")
        return payload

    def _sync_index_entry(self, thread_id: str, thread: dict[str, Any]) -> None:
        index = self._load_index()
        entries = [
            entry
            for entry in index.get("threads", [])
            if isinstance(entry, dict) and entry.get("thread_id") != thread_id
        ]
        entries.append(
            self._thread_summary(
                thread_id,
                thread.get("title") or "",
                thread.get("status") or "active",
                bool(thread.get("archived")),
                thread.get("updated_at") or _utc_now(),
            )
        )
        index["threads"] = entries
        self._write_index(index)

    @staticmethod
    def _thread_summary(
        thread_id: str,
        title: str,
        status: str,
        archived: bool,
        updated_at: str,
    ) -> dict[str, Any]:
        return {
            "thread_id": thread_id,
            "title": title,
            "status": status,
            "archived": archived,
            "updated_at": updated_at,
        }
