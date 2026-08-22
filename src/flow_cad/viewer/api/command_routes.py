"""Fast idempotent metadata commands for the replacement workbench."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from flow_cad.registry import sync_project
from flow_cad.viewer.services import InventoryService


class RefreshRequest(BaseModel):
    part_id: str | None = None
    force_model_refetch: bool = False


def create_workbench_command_router(project_root: Path) -> APIRouter:
    root = project_root.resolve()
    inventory = InventoryService(root)
    router = APIRouter(prefix="/api", tags=["workbench commands"])

    @router.post("/reload")
    def reload_project() -> dict[str, Any]:
        try:
            result = sync_project(root)
            snapshot = inventory.inventory()
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "ok": True,
            "revision": result.revision,
            "changed": result.changed,
            "elapsed_ms": result.elapsed_ms,
            "part_count": result.part_count,
            "occurrence_count": result.occurrence_count,
            "artifact_revisions": _artifact_revisions(snapshot),
        }

    @router.post("/refresh")
    def refresh_project(request: RefreshRequest) -> dict[str, Any]:
        try:
            result = sync_project(root)
            snapshot = inventory.inventory(search=request.part_id) if request.part_id else inventory.inventory()
        except Exception as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        parts = snapshot["parts"]
        if request.part_id:
            parts = [
                part
                for part in parts
                if part["key"] == request.part_id or request.part_id in part["aliases"]
            ]
            if not parts:
                raise HTTPException(status_code=404, detail=f"part not found: {request.part_id}")
        return {
            "ok": True,
            "revision": result.revision,
            "changed": result.changed,
            "force_model_refetch": request.force_model_refetch,
            "rendered_artifacts": [_rendered_artifact(part) for part in parts],
        }

    return router


def _artifact_revisions(snapshot: dict[str, Any]) -> dict[str, str]:
    return {
        str(part["uuid"]): str(part["artifact_revision"])
        for part in snapshot["parts"]
        if part["artifact_revision"] is not None
    }


def _rendered_artifact(part: dict[str, Any]) -> dict[str, Any]:
    display = next(
        (artifact for artifact in part["artifacts"] if artifact["kind"] == "stl"),
        None,
    )
    return {
        "id": part["key"],
        "part_uuid": part["uuid"],
        "artifact_path": display["relative_path"] if display else None,
        "artifact_size": display["byte_count"] if display else None,
        "artifact_hash": part["display_revision"],
        "model_url": part["model_url"],
        "authority_hash": part["artifact_revision"],
    }
