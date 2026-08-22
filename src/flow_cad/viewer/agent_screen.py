from __future__ import annotations

import base64
import binascii
import json
import re
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flow_cad.viewer.service import ViewerService


class AgentScreenError(RuntimeError):
    status_code = 400


class AgentScreenNotFoundError(AgentScreenError):
    status_code = 404


class AgentScreenRequestNotFoundError(AgentScreenError):
    status_code = 404


AGENT_SCREEN_SCHEMA_VERSION = 1
AGENT_SCREEN_REQUEST_SCHEMA_VERSION = 1
AGENT_SCREEN_REQUEST_STATUSES = {"pending", "fulfilled", "failed"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _safe_id(value: str, *, fallback: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    return safe or f"{fallback}_{uuid.uuid4().hex}"


def _decode_base64(value: str) -> bytes:
    try:
        return base64.b64decode(value.strip(), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise AgentScreenError("image_data is not valid base64") from exc


def _parse_png_payload(payload: dict[str, Any]) -> tuple[bytes, str]:
    data_url = payload.get("data_url")
    image_data = payload.get("image_data")
    content_type = str(payload.get("content_type") or "image/png").split(";", maxsplit=1)[0].strip().lower()
    if content_type != "image/png":
        raise AgentScreenError("agent screen capture content_type must be image/png")

    if isinstance(data_url, str) and data_url.strip():
        header, separator, encoded = data_url.strip().partition(",")
        if not separator or ";base64" not in header or not header.startswith("data:"):
            raise AgentScreenError("data_url must be a base64 PNG data URL")
        image_bytes = _decode_base64(encoded)
    elif isinstance(image_data, str) and image_data.strip():
        image_bytes = _decode_base64(image_data)
    else:
        raise AgentScreenError("agent screen capture requires data_url or image_data")

    if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AgentScreenError("agent screen capture payload is not PNG data")
    return image_bytes, "image/png"


def _normalize_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _as_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


class AgentScreenService:
    """Project-local storage for explicit workbench screenshots for agents."""

    def __init__(self, project: ViewerService | Path):
        if isinstance(project, Path):
            self.viewer_service = None
            self.project_root = project.resolve()
            self.root = self.project_root / ".flow" / "agent-screen"
        else:
            self.viewer_service = project
            self.project_root = project.project_root
            self.root = project.project.paths.local_state / "agent-screen"

    def capture(self, payload: dict[str, Any]) -> dict[str, Any]:
        image_bytes, content_type = _parse_png_payload(payload if isinstance(payload, dict) else {})
        capture_id = _safe_id(str(payload.get("capture_id") or f"screen_{uuid.uuid4().hex}"), fallback="screen")
        now = _utc_now()
        width = _normalize_int(payload.get("width"))
        height = _normalize_int(payload.get("height"))
        request_id = payload.get("request_id")
        request_id = _safe_id(str(request_id), fallback="screen-request") if isinstance(request_id, str) and request_id else None

        self.root.mkdir(parents=True, exist_ok=True)
        image_path = self.root / f"{capture_id}.png"
        metadata_path = self.root / f"{capture_id}.json"
        tmp_image = image_path.with_suffix(".png.tmp")
        tmp_image.write_bytes(image_bytes)
        tmp_image.replace(image_path)

        metadata = {
            "schema_version": AGENT_SCREEN_SCHEMA_VERSION,
            "capture_id": capture_id,
            "kind": "agent_screen_capture",
            "content_type": content_type,
            "filename": image_path.name,
            "path": str(image_path.relative_to(self.project_root)),
            "metadata_path": str(metadata_path.relative_to(self.project_root)),
            "image_url": f"/api/agent-screen/captures/{capture_id}/image",
            "created_at": now,
            "width": width,
            "height": height,
            "selected_ids": _as_string_list(payload.get("selected_ids")),
            "visible_ids": _as_string_list(payload.get("visible_ids")),
            "active_part_id": str(payload.get("active_part_id") or "").strip() or None,
            "backend_revision": payload.get("backend_revision"),
            "rendered_artifacts": payload.get("rendered_artifacts") if isinstance(payload.get("rendered_artifacts"), list) else [],
            "viewport": payload.get("viewport") if isinstance(payload.get("viewport"), dict) else {},
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            "request_id": request_id,
        }
        _write_json(metadata_path, metadata)
        _write_json(self.root / "latest.json", metadata)

        if request_id:
            request = self.get_request(request_id)
            request.update(
                {
                    "status": "fulfilled",
                    "capture_id": capture_id,
                    "error": None,
                    "fulfilled_at": now,
                    "updated_at": now,
                }
            )
            _write_json(self._request_path(request_id), request)

        return metadata

    def latest(self) -> dict[str, Any]:
        metadata = _read_json(self.root / "latest.json")
        if metadata is None:
            raise AgentScreenNotFoundError("No agent screen capture is available yet")
        return metadata

    def image_path(self, capture_id: str | None = None) -> Path:
        if capture_id is None or capture_id == "latest":
            capture_id = str(self.latest()["capture_id"])
        safe_id = _safe_id(capture_id, fallback="screen")
        path = self.root / f"{safe_id}.png"
        if not path.exists():
            raise AgentScreenNotFoundError(f"Agent screen image not found: {safe_id}")
        return path

    def request_capture(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload if isinstance(payload, dict) else {}
        request_id = _safe_id(str(payload.get("request_id") or f"screen_request_{uuid.uuid4().hex}"), fallback="screen-request")
        now = _utc_now()
        request = {
            "schema_version": AGENT_SCREEN_REQUEST_SCHEMA_VERSION,
            "request_id": request_id,
            "kind": "agent_screen_request",
            "status": "pending",
            "purpose": str(payload.get("purpose") or "agent-screen").strip() or "agent-screen",
            "width": _normalize_int(payload.get("width")),
            "height": _normalize_int(payload.get("height")),
            "metadata": payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
            "created_at": now,
            "updated_at": now,
            "capture_id": None,
            "error": None,
        }
        self.requests_dir.mkdir(parents=True, exist_ok=True)
        _write_json(self._request_path(request_id), request)
        return request

    def list_requests(self, status: str | None = None) -> dict[str, Any]:
        normalized_status = status.strip().lower() if isinstance(status, str) and status.strip() else None
        if normalized_status and normalized_status not in AGENT_SCREEN_REQUEST_STATUSES:
            raise AgentScreenError(
                f"agent screen request status '{normalized_status}' is invalid "
                f"(expected one of: {', '.join(sorted(AGENT_SCREEN_REQUEST_STATUSES))})"
            )
        requests = []
        if self.requests_dir.exists():
            for path in sorted(self.requests_dir.glob("*.json"), key=lambda item: item.stat().st_mtime):
                request = _read_json(path)
                if isinstance(request, dict):
                    requests.append(request)
        if normalized_status:
            requests = [request for request in requests if request.get("status") == normalized_status]
        return {"ok": True, "status": normalized_status, "count": len(requests), "requests": requests}

    def latest_request(self, status: str | None = "pending") -> dict[str, Any]:
        requests = self.list_requests(status=status)["requests"]
        if not requests:
            raise AgentScreenRequestNotFoundError("No matching agent screen request is available")
        return requests[-1]

    def get_request(self, request_id: str) -> dict[str, Any]:
        safe_id = _safe_id(request_id, fallback="screen-request")
        request = _read_json(self._request_path(safe_id))
        if request is None:
            raise AgentScreenRequestNotFoundError(f"Agent screen request not found: {safe_id}")
        return request

    def fail_request(self, request_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload if isinstance(payload, dict) else {}
        request = self.get_request(request_id)
        now = _utc_now()
        request.update(
            {
                "status": "failed",
                "error": str(payload.get("error") or "Agent screen capture failed"),
                "failed_at": now,
                "updated_at": now,
            }
        )
        _write_json(self._request_path(str(request["request_id"])), request)
        return request

    @property
    def requests_dir(self) -> Path:
        return self.root / "requests"

    def _request_path(self, request_id: str) -> Path:
        return self.requests_dir / f"{_safe_id(request_id, fallback='screen-request')}.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = path.read_text(encoding="utf-8")
        value = json.loads(payload)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        tmp_path = Path(handle.name)
    tmp_path.replace(path)
