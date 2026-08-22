"""Read-only HTTP routes for the replacement workbench."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse

from flow_cad.registry.db import RegistryError
from flow_cad.viewer.services import (
    ArtifactChangedError,
    ContentAddressedModelService,
    InvalidArtifactDigestError,
    InventoryService,
    ModelNotFoundError,
    UnsafeArtifactPathError,
)


def create_query_router(
    project_root: Path,
    *,
    max_concurrent_model_verifications: int = 2,
) -> APIRouter:
    """Create query routes that can be composed with independent command routers."""

    root = project_root.resolve()
    inventory = InventoryService(root)
    models = ContentAddressedModelService(
        root,
        max_concurrent_verifications=max_concurrent_model_verifications,
    )
    router = APIRouter(prefix="/api", tags=["workbench queries"])

    @router.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ready" if inventory.index_path.is_file() else "needs_sync",
            "registry_available": inventory.index_path.is_file(),
        }

    @router.get("/project")
    def project() -> dict[str, object]:
        try:
            return inventory.project()
        except RegistryError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/parts")
    def parts(
        include_retired: bool = True,
        search: str | None = Query(default=None, max_length=256),
        limit: int | None = Query(default=None, ge=0, le=10_000),
    ) -> dict[str, object]:
        try:
            return inventory.inventory(
                include_retired=include_retired,
                search=search,
                limit=limit,
            )
        except RegistryError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.get("/models/{artifact_sha256}")
    async def model(artifact_sha256: str, request: Request) -> Response:
        try:
            resolved = await models.resolve(artifact_sha256)
        except InvalidArtifactDigestError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except (ModelNotFoundError, FileNotFoundError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ArtifactChangedError, UnsafeArtifactPathError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RegistryError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        headers = _immutable_headers(
            resolved.sha256,
            kind=resolved.kind,
            geometry_authority=resolved.geometry_authority,
        )
        if _etag_matches(request.headers.get("if-none-match"), resolved.sha256):
            return Response(status_code=304, headers=headers)
        return FileResponse(
            resolved.path,
            media_type=resolved.media_type,
            headers=headers,
        )

    return router


def _immutable_headers(
    digest: str,
    *,
    kind: str,
    geometry_authority: str,
) -> dict[str, str]:
    return {
        "Cache-Control": "public, max-age=31536000, immutable",
        "ETag": f'"{digest}"',
        "X-Content-SHA256": digest,
        "X-Flow-CAD-Artifact-Kind": kind,
        "X-Flow-CAD-Geometry-Authority": geometry_authority,
    }


def _etag_matches(value: str | None, digest: str) -> bool:
    if value is None:
        return False
    accepted = {item.strip() for item in value.split(",")}
    return "*" in accepted or f'"{digest}"' in accepted or f'W/"{digest}"' in accepted
