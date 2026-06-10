from __future__ import annotations

import base64
import binascii
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


class VisualEvidenceNotFoundError(ThreadStorageError):
    status_code = 404


class VisualEvidenceRequestNotFoundError(ThreadStorageError):
    status_code = 404


DESIGN_THREADS_SCHEMA_VERSION = 1
THREAD_SCHEMA_VERSION = 1
THREAD_MESSAGE_SCHEMA_VERSION = 1
THREAD_CONTEXT_SNAPSHOT_SCHEMA_VERSION = 1
THREAD_DRAFT_EVENT_SCHEMA_VERSION = 1
THREAD_VISUAL_EVIDENCE_REQUEST_SCHEMA_VERSION = 1
THREAD_VISUAL_EVIDENCE_PRESETS = {"front", "back", "left", "right", "top", "bottom", "iso"}
THREAD_VISUAL_EVIDENCE_DEFAULT_PRESET = "iso"
THREAD_VISUAL_EVIDENCE_DEFAULT_SOURCE = "agent"
THREAD_VISUAL_EVIDENCE_REQUEST_STATUSES = {"pending", "fulfilled", "failed"}
VALID_ANNOTATION_KINDS = {"note", "circle", "freehand"}


def _clamp_normalized(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _is_png_payload(mime_type: str | None) -> bool:
    return bool(mime_type and mime_type.split(";", maxsplit=1)[0].strip().lower() == "image/png")


def _parse_data_url(value: str) -> tuple[bytes, str]:
    prefix = "data:"
    if not value.startswith(prefix):
        raise ThreadValidationError("data_url must start with 'data:'")

    header, _, encoded = value.partition(",")
    if not encoded:
        raise ThreadValidationError("data_url is missing encoded payload")
    header = header[5:]
    content_type = "image/png"
    if ";base64" not in header:
        raise ThreadValidationError("data_url must be base64 encoded")
    mime_type = header.split(";", maxsplit=1)[0].strip().lower()
    if mime_type:
        content_type = mime_type

    try:
        return _decode_base64_bytes(encoded), content_type
    except ValueError as exc:
        raise ThreadValidationError("data_url does not contain valid base64 data") from exc


def _decode_base64_bytes(value: str) -> bytes:
    payload = value.strip()
    try:
        return base64.b64decode(payload, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ThreadValidationError("image_data is not valid base64") from exc


def _is_png_data(payload: bytes) -> bool:
    return payload.startswith(b"\x89PNG\r\n\x1a\n")


def _normalize_view_preset(value: Any) -> str:
    if value is None:
        return THREAD_VISUAL_EVIDENCE_DEFAULT_PRESET
    if not isinstance(value, str):
        raise ThreadValidationError("visual evidence view/preset must be a string")

    preset = value.strip().lower()
    if not preset:
        return THREAD_VISUAL_EVIDENCE_DEFAULT_PRESET
    if preset not in THREAD_VISUAL_EVIDENCE_PRESETS:
        raise ThreadValidationError(
            f"visual evidence preset '{preset}' is invalid (expected one of: "
            f"{', '.join(sorted(THREAD_VISUAL_EVIDENCE_PRESETS))})"
        )
    return preset


def _normalize_visual_evidence_source(value: Any) -> str:
    if value is None:
        return THREAD_VISUAL_EVIDENCE_DEFAULT_SOURCE
    if not isinstance(value, str):
        raise ThreadValidationError("visual evidence source must be a string")

    source = value.strip().lower()
    return source or THREAD_VISUAL_EVIDENCE_DEFAULT_SOURCE


def _normalize_viewport_screenshot_input(payload: Any) -> tuple[bytes, str]:
    if not isinstance(payload, dict):
        raise ThreadValidationError("viewport screenshot payload must be an object")

    data_url = payload.get("data_url")
    image_data = payload.get("image_data")
    content_type = payload.get("content_type")

    if isinstance(data_url, str) and data_url.strip():
        image_bytes, detected_type = _parse_data_url(data_url.strip())
    elif isinstance(image_data, str) and image_data.strip():
        image_bytes = _decode_base64_bytes(image_data.strip())
        detected_type = str(content_type).strip().lower() if isinstance(content_type, str) else "image/png"
    else:
        raise ThreadValidationError("viewport screenshot requires data_url or image_data")

    final_content_type = str(content_type).strip().lower() if isinstance(content_type, str) else detected_type
    if not _is_png_payload(final_content_type):
        raise ThreadValidationError("viewport screenshot content_type must be image/png")

    if not image_bytes:
        raise ThreadValidationError("viewport screenshot payload is empty")
    return image_bytes, final_content_type


def _normalize_annotations(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []

    items = list(raw)
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind", "")).strip().lower()
        if kind not in VALID_ANNOTATION_KINDS:
            continue
        annotation_id = _safe_thread_id(str(item.get("id") or f"ann_{uuid.uuid4().hex}"), fallback="ann")
        if kind == "note":
            annotation = {
                "id": annotation_id,
                "kind": "note",
                "text": str(item.get("text", "")).strip(),
                "x": _clamp_normalized(item.get("x", 0.0)),
                "y": _clamp_normalized(item.get("y", 0.0)),
            }
        else:
            if kind == "freehand":
                raw_points = item.get("points")
                if not isinstance(raw_points, list):
                    continue
                points: list[dict[str, float]] = []
                for point in raw_points:
                    if not isinstance(point, dict):
                        continue
                    points.append(
                        {
                            "x": _clamp_normalized(point.get("x", 0.0)),
                            "y": _clamp_normalized(point.get("y", 0.0)),
                        }
                    )
                if len(points) < 2:
                    continue
                width = item.get("width", 0.006)
                try:
                    normalized_width = max(0.001, min(0.05, float(width)))
                except (TypeError, ValueError):
                    normalized_width = 0.006
                annotation = {
                    "id": annotation_id,
                    "kind": "freehand",
                    "points": points,
                    "color": str(item.get("color") or "#f97316"),
                    "width": normalized_width,
                }
                normalized.append(annotation)
                continue
            center = item.get("center")
            if isinstance(center, dict):
                x = center.get("x", 0.0)
                y = center.get("y", 0.0)
            else:
                x = item.get("x", 0.0)
                y = item.get("y", 0.0)
            annotation = {
                "id": annotation_id,
                "kind": "circle",
                "x": _clamp_normalized(x),
                "y": _clamp_normalized(y),
                "radius": _clamp_normalized(item.get("radius", 0.0)),
            }
        normalized.append(annotation)
    return normalized


def _normalize_viewport_screenshot_for_snapshot(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    normalized: dict[str, Any] = {
        "kind": str(value.get("kind") or "viewport_screenshot"),
    }
    annotations = _normalize_annotations(value.get("annotations"))
    if annotations:
        normalized["annotations"] = annotations

    attachment_id = value.get("attachment_id")
    if isinstance(attachment_id, str) and attachment_id.strip():
        normalized["attachment_id"] = _safe_thread_id(attachment_id, fallback="att")
    elif isinstance(value.get("data_url"), str) and value.get("data_url").strip():
        normalized["data_url"] = value.get("data_url").strip()
    else:
        return None

    if isinstance(value.get("content_type"), str) and value.get("content_type"):
        normalized["content_type"] = str(value.get("content_type")).strip()
    if isinstance(value.get("backend_revision"), (int, float, str)) and str(value.get("backend_revision")).strip():
        normalized["backend_revision"] = str(value.get("backend_revision")).strip()

    return normalized


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        integer = int(value)
    except (TypeError, ValueError):
        return None
    if integer <= 0:
        return None
    return integer


def _normalize_visual_evidence_input(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ThreadValidationError("visual evidence payload must be an object")

    data_url = payload.get("data_url")
    image_data = payload.get("image_data")
    content_type = payload.get("content_type")

    if isinstance(data_url, str) and data_url.strip():
        image_bytes, detected_content_type = _parse_data_url(data_url.strip())
    elif isinstance(image_data, str) and image_data.strip():
        image_bytes = _decode_base64_bytes(image_data.strip())
        detected_content_type = str(content_type).strip().lower() if isinstance(content_type, str) else "image/png"
    else:
        raise ThreadValidationError("visual evidence requires data_url or image_data")

    final_content_type = str(content_type).strip().lower() if isinstance(content_type, str) else detected_content_type
    if not _is_png_payload(final_content_type):
        raise ThreadValidationError("visual evidence content_type must be image/png")
    if not image_bytes:
        raise ThreadValidationError("visual evidence payload is empty")
    if not _is_png_data(image_bytes):
        raise ThreadValidationError("visual evidence content is not a valid PNG image")

    preset = payload.get("preset")
    if preset is None:
        preset = payload.get("view")
    preset = _normalize_view_preset(preset)
    source = _normalize_visual_evidence_source(payload.get("source"))

    selected_ids = _normalize_string_list(payload.get("selected_ids"))
    visible_ids = _normalize_string_list(payload.get("visible_ids"))
    part_ids = _normalize_string_list(payload.get("part_ids"))
    purpose = str(payload.get("purpose") or "").strip()

    width = _normalize_positive_int(payload.get("width"))
    height = _normalize_positive_int(payload.get("height"))
    camera = payload.get("camera") if isinstance(payload.get("camera"), dict) else None
    viewport = payload.get("viewport") if isinstance(payload.get("viewport"), dict) else None
    metadata = _as_mapping(payload.get("metadata"))

    return {
        "artifact_id": payload.get("artifact_id"),
        "source": source,
        "preset": preset,
        "width": width,
        "height": height,
        "selected_ids": selected_ids,
        "visible_ids": visible_ids,
        "part_ids": part_ids,
        "purpose": purpose if purpose else None,
        "camera": camera,
        "viewport": viewport,
        "metadata": metadata,
        "content_type": final_content_type,
        "image_bytes": image_bytes,
    }


def _normalize_visual_evidence_request_input(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ThreadValidationError("visual evidence request payload must be an object")

    preset = payload.get("preset")
    if preset is None:
        preset = payload.get("view")
    metadata = _as_mapping(payload.get("metadata"))
    purpose = str(payload.get("purpose") or "").strip()

    return {
        "request_id": payload.get("request_id"),
        "source": _normalize_visual_evidence_source(payload.get("source")),
        "preset": _normalize_view_preset(preset),
        "width": _normalize_positive_int(payload.get("width")),
        "height": _normalize_positive_int(payload.get("height")),
        "selected_ids": _normalize_string_list(payload.get("selected_ids")),
        "visible_ids": _normalize_string_list(payload.get("visible_ids")),
        "part_ids": _normalize_string_list(payload.get("part_ids")),
        "purpose": purpose if purpose else None,
        "metadata": metadata,
    }


def _normalize_visual_evidence_request_status(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ThreadValidationError("visual evidence request status must be a string")
    status = value.strip().lower()
    if not status:
        return None
    if status not in THREAD_VISUAL_EVIDENCE_REQUEST_STATUSES:
        raise ThreadValidationError(
            f"visual evidence request status '{status}' is invalid (expected one of: "
            f"{', '.join(sorted(THREAD_VISUAL_EVIDENCE_REQUEST_STATUSES))})"
        )
    return status


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


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


def _safe_relative_path(value: Any, *, base: Path | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    candidate = Path(text)
    if any(part in {"", "..", "."} for part in candidate.parts):
        return None
    if candidate.is_absolute():
        if base is None:
            return None
        try:
            resolved = candidate.resolve()
            return str(resolved.relative_to(base))
        except (OSError, ValueError):
            return None
    return text.replace("\\", "/")


def _normalize_string_list(value: Any) -> list[str]:
    return _unique_preserve_order([item for item in _as_str_list(value) if item])


def _read_reports(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [value for value in payload if isinstance(value, dict)]
    return []

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


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix="tmp-", suffix=path.suffix, dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
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
        "visual_evidence": [],
        "visual_evidence_count": 0,
        "visual_evidence_requests": [],
        "visual_evidence_request_count": 0,
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
        attachments = self._thread_attachments(thread_id)
        visual_evidence = self._thread_visual_evidence(thread_id)
        visual_evidence_requests = self._thread_visual_evidence_requests(thread_id)
        thread["messages"] = messages
        thread["context_snapshots"] = snapshots
        thread["attachments"] = attachments
        thread["visual_evidence"] = visual_evidence
        thread["visual_evidence_requests"] = visual_evidence_requests
        thread["message_count"] = len(messages)
        thread["snapshot_count"] = len(snapshots)
        thread["attachment_count"] = len(attachments)
        thread["visual_evidence_count"] = len(visual_evidence)
        thread["visual_evidence_request_count"] = len(visual_evidence_requests)
        return thread

    def add_visual_evidence(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_thread(thread_id)
        input_data = _normalize_visual_evidence_input(payload)

        artifact_id = _safe_thread_id(str(input_data["artifact_id"] or f"ve_{uuid.uuid4().hex}"), fallback="evidence")
        now = _utc_now()

        self._thread_visual_evidence_dir(thread_id).mkdir(parents=True, exist_ok=True)
        png_path = self._thread_visual_evidence_png_path(thread_id, artifact_id)
        metadata_path = self._thread_visual_evidence_metadata_path(thread_id, artifact_id)
        _write_bytes_atomic(png_path, input_data["image_bytes"])

        metadata = {
            "artifact_id": artifact_id,
            "kind": "visual_evidence",
            "source": input_data["source"],
            "view": input_data["preset"],
            "content_type": input_data["content_type"],
            "filename": png_path.name,
            "path": str(png_path.relative_to(self.threads_root)),
            "image_url": f"/api/design-threads/{thread_id}/visual-evidence/{artifact_id}/image",
            "metadata_path": str(metadata_path.relative_to(self.threads_root)),
            "created_at": now,
            "width": input_data["width"],
            "height": input_data["height"],
            "selected_ids": input_data["selected_ids"],
            "visible_ids": input_data["visible_ids"],
            "part_ids": input_data["part_ids"],
            "purpose": input_data["purpose"],
            "camera": input_data["camera"],
            "viewport": input_data["viewport"],
            "metadata": input_data["metadata"],
        }
        _write_json_atomic(metadata_path, metadata)

        return metadata

    def request_visual_evidence(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        thread = self._require_thread(thread_id)
        thread_id = thread["thread_id"]
        input_data = _normalize_visual_evidence_request_input(payload)

        request_id = _safe_thread_id(str(input_data["request_id"] or f"ver_{uuid.uuid4().hex}"), fallback="ver")
        now = _utc_now()
        request = {
            "schema_version": THREAD_VISUAL_EVIDENCE_REQUEST_SCHEMA_VERSION,
            "request_id": request_id,
            "thread_id": thread_id,
            "status": "pending",
            "source": input_data["source"],
            "view": input_data["preset"],
            "width": input_data["width"],
            "height": input_data["height"],
            "selected_ids": input_data["selected_ids"],
            "visible_ids": input_data["visible_ids"],
            "part_ids": input_data["part_ids"],
            "purpose": input_data["purpose"],
            "metadata": input_data["metadata"],
            "created_at": now,
            "updated_at": now,
            "artifact_id": None,
            "error": None,
        }
        _write_json_atomic(self._thread_visual_evidence_request_path(thread_id, request_id), request)
        return request

    def list_visual_evidence_requests(self, thread_id: str, status: str | None = None) -> dict[str, Any]:
        thread = self._require_thread(thread_id)
        normalized_status = _normalize_visual_evidence_request_status(status)
        requests = self._thread_visual_evidence_requests(thread["thread_id"])
        if normalized_status:
            requests = [
                request
                for request in requests
                if str(request.get("status") or "").strip().lower() == normalized_status
            ]
        return {
            "ok": True,
            "thread_id": thread["thread_id"],
            "status": normalized_status,
            "count": len(requests),
            "visual_evidence_requests": requests,
        }

    def get_visual_evidence_request(self, thread_id: str, request_id: str) -> dict[str, Any]:
        self._require_thread(thread_id)
        safe_request_id = _safe_thread_id(request_id, fallback="ver")
        request = _read_json(self._thread_visual_evidence_request_path(thread_id, safe_request_id))
        if request is None:
            raise VisualEvidenceRequestNotFoundError(
                f"Visual evidence request not found: {safe_request_id} in thread {thread_id}"
            )
        return request

    def fulfill_visual_evidence_request(self, thread_id: str, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = self.get_visual_evidence_request(thread_id, request_id)
        if str(request.get("status") or "").strip().lower() != "pending":
            raise ThreadValidationError(f"Visual evidence request is already {request.get('status') or 'closed'}")

        input_payload = payload if isinstance(payload, dict) else {}
        request_metadata = _as_mapping(request.get("metadata"))
        payload_metadata = _as_mapping(input_payload.get("metadata"))
        evidence_payload = {
            **input_payload,
            "source": input_payload.get("source") or request.get("source") or "agent",
            "view": input_payload.get("view") or request.get("view") or THREAD_VISUAL_EVIDENCE_DEFAULT_PRESET,
            "selected_ids": input_payload.get("selected_ids") or request.get("selected_ids") or [],
            "visible_ids": input_payload.get("visible_ids") or request.get("visible_ids") or [],
            "part_ids": input_payload.get("part_ids") or request.get("part_ids") or [],
            "purpose": input_payload.get("purpose") or request.get("purpose"),
            "metadata": {
                **request_metadata,
                **payload_metadata,
                "visual_evidence_request_id": request["request_id"],
                "requested_at": request.get("created_at"),
            },
        }
        evidence = self.add_visual_evidence(thread_id, evidence_payload)

        now = _utc_now()
        request.update(
            {
                "status": "fulfilled",
                "artifact_id": evidence["artifact_id"],
                "error": None,
                "fulfilled_at": now,
                "updated_at": now,
            }
        )
        _write_json_atomic(self._thread_visual_evidence_request_path(thread_id, request["request_id"]), request)
        return {"ok": True, "request": request, "visual_evidence": evidence}

    def fail_visual_evidence_request(self, thread_id: str, request_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = self.get_visual_evidence_request(thread_id, request_id)
        if str(request.get("status") or "").strip().lower() != "pending":
            raise ThreadValidationError(f"Visual evidence request is already {request.get('status') or 'closed'}")

        error = "Visual evidence request failed"
        if isinstance(payload, dict) and isinstance(payload.get("error"), str) and payload["error"].strip():
            error = payload["error"].strip()
        now = _utc_now()
        request.update(
            {
                "status": "failed",
                "error": error,
                "failed_at": now,
                "updated_at": now,
            }
        )
        _write_json_atomic(self._thread_visual_evidence_request_path(thread_id, request["request_id"]), request)
        return {"ok": True, "request": request}

    def get_visual_evidence(self, thread_id: str, artifact_id: str) -> dict[str, Any]:
        self._require_thread(thread_id)
        safe_artifact_id = _safe_thread_id(artifact_id, fallback="evidence")
        metadata_path = self._thread_visual_evidence_metadata_path(thread_id, safe_artifact_id)
        metadata = _read_json(metadata_path)
        if metadata is None:
            raise VisualEvidenceNotFoundError(
                f"Visual evidence not found: {safe_artifact_id} in thread {thread_id}"
            )
        return metadata

    def get_visual_evidence_image(self, thread_id: str, artifact_id: str) -> Path:
        self._require_thread(thread_id)
        safe_artifact_id = _safe_thread_id(artifact_id, fallback="evidence")
        png_path = self._thread_visual_evidence_png_path(thread_id, safe_artifact_id)
        if not png_path.exists():
            raise VisualEvidenceNotFoundError(f"Visual evidence image not found: {safe_artifact_id} in thread {thread_id}")
        return png_path

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
        return self._append_event_message(
            thread,
            {
                "type": str(payload.get("type") or "user_message"),
                "role": str(payload.get("role") or "user"),
                "content": payload.get("content", payload.get("text") or payload.get("message")),
                "attachments": _as_list(payload.get("attachments")),
                "metadata": _as_mapping(payload.get("metadata")),
            },
        )

    def append_draft_event(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        thread = self._require_thread(thread_id)
        raw_content = _as_mapping(payload.get("content"))
        nested_content = _as_mapping(raw_content.get("content"))
        content = dict(nested_content or raw_content)
        if nested_content:
            for key, value in raw_content.items():
                if key == "content":
                    continue
                content.setdefault(key, value)
        metadata = _as_mapping(payload.get("metadata"))
        action = str(
            payload.get("action")
            or payload.get("event")
            or content.get("action")
            or metadata.get("action")
            or ""
        ).strip().lower()
        if not action:
            raise ThreadValidationError("draft event action is required")
        content["action"] = action
        content["status"] = str(content.get("status") or payload.get("status") or "ok")

        token_candidates: list[str] = _normalize_string_list(
            [
                content.get("draft_transaction_token"),
                content.get("transaction_token"),
                content.get("token"),
                payload.get("transaction_token"),
                payload.get("draft_transaction_token"),
                payload.get("token"),
                metadata.get("transaction_token"),
                metadata.get("draft_transaction_token"),
                metadata.get("token"),
            ]
        )
        if not token_candidates and action in {"accept", "accepted", "discard", "applied", "apply", "preview", "begin", "reset"}:
            operation = _as_mapping(content.get("operation"))
            extra = _as_mapping(operation.get("transaction"))
            token_candidates = _normalize_string_list([extra.get("transaction_token"), extra.get("token")])
        if token_candidates:
            token = token_candidates[0]
        else:
            token = None
        if token is not None:
            content["draft_transaction_token"] = token
            thread["linked_draft_transaction_tokens"] = _unique_preserve_order(
                _as_str_list(thread.get("linked_draft_transaction_tokens", [])) + [token]
            )

        accepted_paths = self._draft_accept_artifact_paths(action=action, payload=payload, content=content)
        if accepted_paths:
            thread["accepted_artifact_paths"] = _unique_preserve_order(
                _normalize_string_list(thread.get("accepted_artifact_paths", [])) + accepted_paths
            )
            metadata["accepted_artifact_paths"] = accepted_paths

        metadata["action"] = action
        metadata["thread_version"] = thread["thread_id"]
        if token is not None:
            metadata["draft_transaction_token"] = token

        return self._append_event_message(
            thread,
            {
                "schema_version": THREAD_DRAFT_EVENT_SCHEMA_VERSION,
                "type": "draft_event",
                "role": "system",
                "content": content,
                "attachments": _as_list(payload.get("attachments")),
                "metadata": metadata,
            },
        )

    def append_validator_event(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        thread = self._require_thread(thread_id)
        event_type = str(payload.get("event_type") or payload.get("type") or "tool_result").lower()
        if event_type not in {"tool_result", "review_event"}:
            event_type = "tool_result"

        content = _as_mapping(payload.get("content"))
        base = {
            key: value
            for key, value in payload.items()
            if key not in {"metadata", "type", "event_type"}
        }
        if content:
            base.update(content)
        content = base
        metadata = _as_mapping(payload.get("metadata"))
        report_ids, report_summaries = self._collect_report_evidence(payload, content, metadata)
        profile_ids, profile_summaries = self._collect_profile_evidence(payload, content, metadata)
        if report_ids:
            metadata["report_ids"] = report_ids
        if report_summaries:
            metadata["report_summaries"] = report_summaries
        if profile_ids:
            metadata["profile_ids"] = profile_ids
        if profile_summaries:
            metadata["profile_summaries"] = profile_summaries

        return self._append_event_message(
            thread,
            {
                "schema_version": THREAD_MESSAGE_SCHEMA_VERSION,
                "type": event_type,
                "role": "system",
                "content": content,
                "attachments": _as_list(payload.get("attachments")),
                "metadata": metadata,
            },
        )

    def _append_event_message(
        self,
        thread: dict[str, Any],
        payload: dict[str, Any],
        *,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        thread_id = thread["thread_id"]
        message = {
            "message_id": f"msg_{uuid.uuid4().hex}",
            "thread_id": thread_id,
            "created_at": created_at or _utc_now(),
            "type": str(payload.get("type") or "user_message"),
            "role": str(payload.get("role") or "user"),
            "content": payload.get("content"),
            "attachments": _as_list(payload.get("attachments")),
            "metadata": _as_mapping(payload.get("metadata")),
            "schema_version": THREAD_MESSAGE_SCHEMA_VERSION,
        }
        if message["type"] == "draft_event" and message.get("schema_version") != THREAD_DRAFT_EVENT_SCHEMA_VERSION:
            message["schema_version"] = THREAD_DRAFT_EVENT_SCHEMA_VERSION
        if payload.get("schema_version"):
            message["schema_version"] = payload["schema_version"]

        if message["content"] is None:
            raise ThreadValidationError("message content is required")

        _append_jsonl(self._thread_messages_path(thread_id), message)

        thread["updated_at"] = _utc_now()
        thread["message_count"] = thread.get("message_count", 0) + 1
        self._write_thread(thread_id, thread)
        self._sync_index_entry(thread_id, thread)
        return message

    def _draft_accept_artifact_paths(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        content: dict[str, Any],
    ) -> list[str]:
        if action not in {"accept", "accepted"}:
            return []
        candidates: list[str] = []
        keys = [
            "source_patch_path",
            "source_patch_relative_path",
            "generated_source_path",
            "generated_source_relative_path",
            "validator_stub_path",
            "validator_stub_relative_path",
            "acceptance_manifest_path",
            "acceptance_manifest_relative_path",
        ]
        for source in (
            payload,
            content,
            _as_mapping(payload.get("acceptance")),
            _as_mapping(content.get("acceptance")),
        ):
            for key in keys:
                path = _safe_relative_path(source.get(key), base=self.root)
                if path is not None and path not in candidates:
                    candidates.append(path)
            accepted_artifacts = _as_mapping(source.get("artifacts"))
            for item in accepted_artifacts.values() if isinstance(accepted_artifacts, dict) else []:
                path = _safe_relative_path(item, base=self.root)
                if path is not None and path not in candidates:
                    candidates.append(path)

        candidate_paths = _normalize_string_list(payload.get("accepted_artifact_paths"))
        candidate_paths.extend(_normalize_string_list(content.get("accepted_artifact_paths")))
        for path in candidate_paths:
            normalized = _safe_relative_path(path, base=self.root)
            if normalized is not None and normalized not in candidates:
                candidates.append(normalized)
        return candidates

    def _collect_report_evidence(
        self,
        payload: dict[str, Any],
        content: dict[str, Any],
        metadata: dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        ids: list[str] = []
        summaries: list[str] = []
        for source in (payload, content, metadata, _as_mapping(payload.get("data")), _as_mapping(content.get("data"))):
            ids.extend(self._collect_ids_from_reports(source))
            summaries.extend(self._collect_summaries_from_reports(source))
        return _unique_preserve_order(ids), _unique_preserve_order(summaries)

    def _collect_profile_evidence(
        self,
        payload: dict[str, Any],
        content: dict[str, Any],
        metadata: dict[str, Any],
    ) -> tuple[list[str], list[str]]:
        ids: list[str] = []
        summaries: list[str] = []
        for source in (payload, content, metadata, _as_mapping(payload.get("data")), _as_mapping(content.get("data"))):
            ids.extend(self._collect_ids_from_profiles(source))
            summaries.extend(self._collect_summaries_from_profiles(source))
        return _unique_preserve_order(ids), _unique_preserve_order(summaries)

    @staticmethod
    def _collect_ids_from_reports(payload: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        direct = payload.get("report_id")
        if isinstance(direct, str) and direct.strip():
            ids.append(direct.strip())
        for report in _read_reports(payload.get("reports")):
            if isinstance(report.get("metadata"), dict):
                report_id = report.get("metadata").get("id")
                if isinstance(report_id, str) and report_id.strip():
                    ids.append(report_id.strip())
            if isinstance(report.get("id"), str) and report["id"].strip():
                ids.append(report["id"].strip())
            if isinstance(report.get("report_id"), str) and report["report_id"].strip():
                ids.append(report["report_id"].strip())
        return ids

    @staticmethod
    def _collect_ids_from_profiles(payload: dict[str, Any]) -> list[str]:
        ids: list[str] = []
        direct = payload.get("profile_id")
        if isinstance(direct, str) and direct.strip():
            ids.append(direct.strip())
        for profile in _read_reports(payload.get("profiles")):
            if isinstance(profile.get("profile_id"), str) and profile["profile_id"].strip():
                ids.append(profile["profile_id"].strip())
            metadata = _as_mapping(profile.get("metadata"))
            nested = metadata.get("profile_id")
            if isinstance(nested, str) and nested.strip():
                ids.append(nested.strip())
        return ids

    @staticmethod
    def _collect_summaries_from_reports(payload: dict[str, Any]) -> list[str]:
        summaries: list[str] = []
        direct = payload.get("summary")
        if isinstance(direct, str) and direct.strip():
            summaries.append(direct.strip())
        for report in _read_reports(payload.get("reports")):
            if isinstance(report.get("summary"), str) and report["summary"].strip():
                summaries.append(str(report["summary"]).strip())
            metadata = _as_mapping(report.get("metadata"))
            for key in ("summary", "status", "result_summary"):
                if isinstance(metadata.get(key), str) and metadata[key].strip():
                    summaries.append(metadata[key].strip())
        return summaries

    @staticmethod
    def _collect_summaries_from_profiles(payload: dict[str, Any]) -> list[str]:
        summaries: list[str] = []
        direct = payload.get("summary")
        if isinstance(direct, str) and direct.strip():
            summaries.append(direct.strip())
        for profile in _read_reports(payload.get("profiles")):
            if isinstance(profile.get("summary"), str) and profile["summary"].strip():
                summaries.append(profile["summary"].strip())
            status = profile.get("status")
            if isinstance(status, str) and status.strip():
                summaries.append(status.strip())
        return summaries

    def chat_turn(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        prepared = self.begin_chat_turn(thread_id, payload)
        text = prepared["message_text"]
        snapshot = prepared["context_snapshot"]

        assistant_metadata = {
            "runtime": "flow_cad_stub",
            "runtime_status": "configured_stub",
            **({"context_snapshot_id": snapshot["snapshot_id"]} if snapshot else {}),
        }
        assistant_message = self.append_message(
            thread_id,
            {
                "type": "assistant_message",
                "role": "assistant",
                "content": self._assistant_reply(text, snapshot),
                "metadata": assistant_metadata,
            },
        )
        return {
            "thread_id": thread_id,
            "messages": [prepared["user_message"], assistant_message],
            "context_snapshot": snapshot,
            "thread": self.get_thread(thread_id),
        }

    def begin_chat_turn(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        text = payload.get("message", payload.get("content"))
        if not isinstance(text, str) or not text.strip():
            raise ThreadValidationError("chat message content is required")
        message_text = text.strip()

        context_payload = payload.get("context_snapshot")
        snapshot: dict[str, Any] | None = None
        incoming_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        metadata: dict[str, Any] = dict(incoming_metadata)
        attachments = _normalize_part_ids(payload.get("attachments"))
        if isinstance(context_payload, dict):
            snapshot = self.create_context_snapshot(thread_id, context_payload)
            metadata["context_snapshot_id"] = snapshot["snapshot_id"]
            if _snapshot_has_view_image(snapshot):
                metadata["viewport_screenshot"] = True
                viewer_state = snapshot.get("viewer_state")
                screenshot = viewer_state.get("viewport_screenshot") if isinstance(viewer_state, dict) else None
                if isinstance(screenshot, dict) and isinstance(screenshot.get("attachment_id"), str):
                    attachment_id = _safe_thread_id(str(screenshot["attachment_id"]), fallback="att")
                    metadata["viewport_attachment_id"] = attachment_id
                    if attachment_id not in attachments:
                        attachments.append(attachment_id)

        user_message = self.append_message(
            thread_id,
            {
                "type": "user_message",
                "role": "user",
                "content": message_text,
                "attachments": attachments,
                "metadata": metadata,
            },
        )
        return {
            "thread_id": thread_id,
            "message_text": message_text,
            "user_message": user_message,
            "context_snapshot": snapshot,
            "thread": self.get_thread(thread_id),
        }

    def assistant_context_packet(
        self,
        thread_id: str,
        *,
        context_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        thread = self.get_thread(thread_id)
        snapshots = thread.get("context_snapshots") if isinstance(thread.get("context_snapshots"), list) else []
        snapshot = context_snapshot or (snapshots[-1] if snapshots else None)
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        viewer_state = snapshot.get("viewer_state") if isinstance(snapshot.get("viewer_state"), dict) else {}
        screenshot = viewer_state.get("viewport_screenshot")
        viewport_screenshot: str | None = None
        if isinstance(screenshot, dict) and isinstance(screenshot.get("attachment_id"), str):
            viewport_screenshot = str(screenshot["attachment_id"])

        validator_report_ids: list[str] = []
        profile_ids: list[str] = []
        for message in thread.get("messages", []):
            if not isinstance(message, dict):
                continue
            metadata = _as_mapping(message.get("metadata"))
            validator_report_ids.extend(_as_str_list(metadata.get("report_ids")))
            profile_ids.extend(_as_str_list(metadata.get("profile_ids")))

        return {
            "thread_id": thread_id,
            "project": snapshot.get("project") if isinstance(snapshot.get("project"), dict) else self.viewer_service.runtime_context(),
            "viewer": {
                "selected_part_ids": snapshot.get("selected_part_ids", []),
                "visible_part_ids": snapshot.get("visible_part_ids", []),
                "measurements": snapshot.get("measurements", []),
                "viewport_size": snapshot.get("viewport", {}).get("size") if isinstance(snapshot.get("viewport"), dict) else None,
                "viewport_screenshot": viewport_screenshot,
            },
            "draft_transaction_token": (
                snapshot.get("draft_transaction", {}).get("transaction_token")
                if isinstance(snapshot.get("draft_transaction"), dict)
                else None
            )
            or (
                snapshot.get("draft_transaction", {}).get("token")
                if isinstance(snapshot.get("draft_transaction"), dict)
                else None
            ),
            "validator_report_ids": _unique_preserve_order(validator_report_ids),
            "profile_ids": _unique_preserve_order(profile_ids),
            "attachments": [
                {
                    "attachment_id": item.get("attachment_id"),
                    "kind": item.get("kind"),
                    "annotation_count": len(item.get("annotations", [])) if isinstance(item.get("annotations"), list) else 0,
                }
                for item in thread.get("attachments", [])
                if isinstance(item, dict)
            ],
            "message_count": len(thread.get("messages", [])) if isinstance(thread.get("messages"), list) else 0,
        }

    def add_viewport_screenshot_attachment(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._require_thread(thread_id)
        image_bytes, content_type = _normalize_viewport_screenshot_input(payload)

        attachment_id = _safe_thread_id(
            str(payload.get("attachment_id") or f"att_{uuid.uuid4().hex}"),
            fallback="att",
        )
        selected_part_ids = _normalize_part_ids(payload.get("selected_part_ids"))
        visible_part_ids = _normalize_part_ids(payload.get("visible_part_ids"))
        annotations = _normalize_annotations(payload.get("annotations"))

        backend_revision: int | None = None
        if isinstance(payload.get("backend_revision"), bool):
            backend_revision = int(payload["backend_revision"])
        elif isinstance(payload.get("backend_revision"), int):
            backend_revision = payload["backend_revision"]
        elif isinstance(payload.get("backend_revision"), str) and str(payload["backend_revision"]).strip():
            try:
                backend_revision = int(float(payload["backend_revision"]))
            except ValueError:
                backend_revision = None
        elif isinstance(payload.get("backend_revision"), float):
            backend_revision = int(payload["backend_revision"])

        camera = payload.get("camera") if isinstance(payload.get("camera"), dict) else None
        viewport = payload.get("viewport") if isinstance(payload.get("viewport"), dict) else None

        self._thread_attachments_dir(thread_id).mkdir(parents=True, exist_ok=True)
        png_path = self._thread_attachment_png_path(thread_id, attachment_id)
        metadata_path = self._thread_attachment_metadata_path(thread_id, attachment_id)
        _write_bytes_atomic(png_path, image_bytes)

        created_at = _utc_now()
        metadata = {
            "attachment_id": attachment_id,
            "kind": "viewport_screenshot",
            "content_type": content_type,
            "filename": png_path.name,
            "path": str(png_path.relative_to(self.threads_root)),
            "created_at": created_at,
            "selected_part_ids": selected_part_ids,
            "visible_part_ids": visible_part_ids,
            "backend_revision": backend_revision,
            "camera": camera,
            "viewport": viewport,
            "annotations": annotations,
            "metadata_path": str(metadata_path.relative_to(self.threads_root)),
        }
        _write_json_atomic(metadata_path, metadata)

        return {
            "attachment_id": attachment_id,
            "kind": "viewport_screenshot",
            "content_type": content_type,
            "filename": png_path.name,
            "path": metadata["path"],
            "metadata_path": metadata["metadata_path"],
            "selected_part_ids": selected_part_ids,
            "visible_part_ids": visible_part_ids,
            "annotations": annotations,
            "created_at": created_at,
        }

    def create_context_snapshot(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        thread = self._require_thread(thread_id)
        snapshot_id = _safe_thread_id(
            f"snap-{payload.get('snapshot_id') or uuid.uuid4().hex[:12]}",
            fallback="snapshot",
        )
        now = _utc_now()
        viewer_state = dict(payload)
        if "viewport_screenshot" in viewer_state:
            normalized_screenshot = _normalize_viewport_screenshot_for_snapshot(viewer_state["viewport_screenshot"])
            if normalized_screenshot is not None:
                viewer_state["viewport_screenshot"] = normalized_screenshot
            else:
                viewer_state.pop("viewport_screenshot")
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
            "viewer_state": viewer_state,
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

    def _thread_visual_evidence_dir(self, thread_id: str) -> Path:
        return self._thread_dir(thread_id) / "visual-evidence"

    def _thread_visual_evidence_requests_dir(self, thread_id: str) -> Path:
        return self._thread_visual_evidence_dir(thread_id) / "requests"

    def _thread_attachment_png_path(self, thread_id: str, attachment_id: str) -> Path:
        return self._thread_attachments_dir(thread_id) / f"{_safe_thread_id(attachment_id, fallback='att')}.png"

    def _thread_attachment_metadata_path(self, thread_id: str, attachment_id: str) -> Path:
        return self._thread_attachment_png_path(thread_id, attachment_id).with_suffix(".json")

    def _thread_visual_evidence_png_path(self, thread_id: str, artifact_id: str) -> Path:
        return self._thread_visual_evidence_dir(thread_id) / f"{_safe_thread_id(artifact_id, fallback='evidence')}.png"

    def _thread_visual_evidence_metadata_path(self, thread_id: str, artifact_id: str) -> Path:
        return self._thread_visual_evidence_png_path(thread_id, artifact_id).with_suffix(".json")

    def _thread_visual_evidence_request_path(self, thread_id: str, request_id: str) -> Path:
        safe_request_id = _safe_thread_id(request_id, fallback="ver")
        return self._thread_visual_evidence_requests_dir(thread_id) / f"{safe_request_id}.json"

    def _thread_snapshot_path(self, thread_id: str, snapshot_id: str) -> Path:
        safe_snapshot_id = _safe_thread_id(snapshot_id, fallback="snapshot")
        return self._thread_snapshots_dir(thread_id) / f"{safe_snapshot_id}.json"

    def _thread_attachments(self, thread_id: str) -> list[dict[str, Any]]:
        attachments_dir = self._thread_attachments_dir(thread_id)
        return [
            _read_json(path) or {"attachment_id": path.stem, "kind": "unknown"}
            for path in _ordered_json_files(attachments_dir)
            if path.is_file()
        ]

    def _thread_visual_evidence(self, thread_id: str) -> list[dict[str, Any]]:
        visual_evidence_dir = self._thread_visual_evidence_dir(thread_id)
        return [
            _read_json(path) or {"artifact_id": path.stem, "kind": "visual_evidence"}
            for path in _ordered_json_files(visual_evidence_dir)
            if path.is_file()
        ]

    def _thread_visual_evidence_requests(self, thread_id: str) -> list[dict[str, Any]]:
        requests_dir = self._thread_visual_evidence_requests_dir(thread_id)
        return [
            _read_json(path) or {"request_id": path.stem, "status": "unknown"}
            for path in _ordered_json_files(requests_dir)
            if path.is_file()
        ]

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
