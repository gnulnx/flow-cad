"""Ephemeral in-assembly placement for disposable review artifacts."""

from __future__ import annotations

import json
import os
import tempfile
from hashlib import sha256
from copy import deepcopy
from pathlib import Path
from typing import Any


class PreviewPlacementError(ValueError):
    """The requested preview replacement cannot be resolved safely."""


class PreviewPlacementStore:
    """Persist viewer-only replacement state below ignored ``.flow`` state."""

    SCHEMA_VERSION = 1

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.path = self.project_root / ".flow" / "workbench" / "preview-placement.json"

    def activate(
        self,
        snapshot: dict[str, Any],
        *,
        preview_part_id: str,
        target_part_id: str,
    ) -> dict[str, Any]:
        preview = _resolve_part(snapshot, preview_part_id)
        target = _resolve_part(snapshot, target_part_id)
        if preview["uuid"] == target["uuid"]:
            raise PreviewPlacementError("preview and replacement target must be different parts")
        existing = self.read()
        if (
            existing is not None
            and existing.get("manifest_sha256") == snapshot.get("manifest_sha256")
            and existing.get("preview_part_uuid") == preview["uuid"]
            and existing.get("target_part_uuid") == target["uuid"]
        ):
            return existing
        if not preview.get("model_url"):
            raise PreviewPlacementError(f"preview part has no display artifact: {preview_part_id}")
        occurrences = target.get("occurrences")
        if not isinstance(occurrences, list) or not occurrences:
            raise PreviewPlacementError(f"replacement target has no assembly occurrences: {target_part_id}")

        placement = {
            "schema_version": self.SCHEMA_VERSION,
            "manifest_sha256": snapshot.get("manifest_sha256"),
            "registry_revision": snapshot.get("revision"),
            "preview_part_uuid": preview["uuid"],
            "preview_part_key": preview["key"],
            "target_part_uuid": target["uuid"],
            "target_part_key": target["key"],
            "occurrences": deepcopy(occurrences),
        }
        self._write(placement)
        return placement

    def clear(self) -> bool:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return False
        return True

    def read(self) -> dict[str, Any] | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        if not isinstance(payload, dict) or payload.get("schema_version") != self.SCHEMA_VERSION:
            return None
        return payload

    def revision(self) -> str:
        try:
            content = self.path.read_bytes()
        except OSError:
            return "none"
        return sha256(content).hexdigest()

    def apply(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        placement = self.read()
        if placement is None or placement.get("manifest_sha256") != snapshot.get("manifest_sha256"):
            return snapshot

        preview_uuid = str(placement.get("preview_part_uuid") or "")
        target_uuid = str(placement.get("target_part_uuid") or "")
        occurrences = placement.get("occurrences")
        if not preview_uuid or not target_uuid or not isinstance(occurrences, list) or not occurrences:
            return snapshot

        preview_found = False
        for part in snapshot.get("parts", []):
            if part.get("uuid") == preview_uuid:
                preview_found = True
                part["occurrences"] = deepcopy(occurrences)
                part["preview_of_uuid"] = target_uuid
                part["preview_of_key"] = placement.get("target_part_key")
                part["warnings"] = list(part.get("warnings", [])) + [
                    f"Viewer preview replaces {placement.get('target_part_key') or target_uuid} in assembly context."
                ]
            elif part.get("uuid") == target_uuid:
                part["occurrences"] = []
                part["preview_replaced_by_uuid"] = preview_uuid

        if preview_found:
            snapshot["preview_placement"] = deepcopy(placement)
        return snapshot

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.path.parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            temporary_path.replace(self.path)
        finally:
            temporary_path.unlink(missing_ok=True)


def _resolve_part(snapshot: dict[str, Any], identifier: str) -> dict[str, Any]:
    normalized = identifier.strip()
    for part in snapshot.get("parts", []):
        if normalized in {str(part.get("uuid") or ""), str(part.get("key") or "")}:
            return part
        if normalized in {str(alias) for alias in part.get("aliases", [])}:
            return part
    raise PreviewPlacementError(f"part not found: {identifier}")
