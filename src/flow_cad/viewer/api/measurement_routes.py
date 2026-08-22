"""Exact-measurement query and extraction-job routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from flow_cad.jobs import IdempotencyConflictError, JobService, JobStoreError
from flow_cad.measurement import (
    ArtifactBytesChangedError,
    ArtifactRevisionMismatchError,
    ExactFeatureService,
    ExactGeometryUnavailableError,
    InvalidArtifactRevisionError,
    PartNotFoundError,
)
from flow_cad.registry.db import RegistryError


class ExactFeatureExtractionRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=256)
    artifact_revision: str = Field(min_length=64, max_length=64)


def create_measurement_router(
    project_root: Path,
    *,
    job_service: JobService,
) -> APIRouter:
    """Create exact-feature routes over an injected shared job service."""

    service = ExactFeatureService(project_root)
    router = APIRouter(prefix="/api", tags=["exact measurement"])

    @router.get("/parts/{part_uuid}/exact-features")
    def exact_features(part_uuid: str, artifact_revision: str) -> JSONResponse:
        try:
            lookup = service.lookup(part_uuid, artifact_revision)
        except Exception as exc:
            raise _http_error(exc) from exc
        if lookup.payload is not None:
            return JSONResponse(
                status_code=200,
                content={**lookup.payload, "cache_hit": True},
                headers=_revision_headers(lookup.binding.artifact_revision),
            )
        return JSONResponse(
            status_code=202,
            content={
                "status": "job_required",
                "part_uuid": lookup.binding.part_uuid,
                "artifact_revision": lookup.binding.artifact_revision,
                "geometry_authority": "step_kernel",
                "quality": "exact",
                "job_request": {
                    **service.job_contract(lookup.binding),
                    "method": "POST",
                    "url": f"/api/parts/{lookup.binding.part_uuid}/exact-features/jobs",
                    "requires_request_id": True,
                },
            },
            headers=_revision_headers(lookup.binding.artifact_revision),
        )

    @router.post("/parts/{part_uuid}/exact-features/jobs")
    def queue_exact_features(
        part_uuid: str,
        request: ExactFeatureExtractionRequest,
    ) -> JSONResponse:
        try:
            lookup = service.lookup(part_uuid, request.artifact_revision)
        except Exception as exc:
            raise _http_error(exc) from exc
        if lookup.payload is not None:
            return JSONResponse(
                status_code=200,
                content={**lookup.payload, "cache_hit": True},
                headers=_revision_headers(lookup.binding.artifact_revision),
            )

        binding = lookup.binding

        def work(context) -> dict[str, Any]:
            return service.extract_and_cache(
                binding.part_uuid,
                binding.artifact_revision,
                report=context.report,
                checkpoint=context.checkpoint,
            )

        contract = service.job_contract(binding)
        try:
            submission = job_service.submit(
                request_id=request.request_id,
                kind=str(contract["kind"]),
                payload=contract,
                work=work,
            )
        except IdempotencyConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except JobStoreError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        job = submission.job
        return JSONResponse(
            status_code=202,
            content={
                "status": job.state.value,
                "part_uuid": binding.part_uuid,
                "artifact_revision": binding.artifact_revision,
                "created": submission.created,
                "job": job.as_dict(),
                "job_url": f"/api/workbench/v1/jobs/{job.job_id}",
                "events_url": f"/api/workbench/v1/jobs/{job.job_id}/stream",
                "cancel_url": f"/api/workbench/v1/jobs/{job.job_id}/cancel",
                "result_url": (
                    f"/api/parts/{binding.part_uuid}/exact-features"
                    f"?artifact_revision={binding.artifact_revision}"
                ),
            },
            headers=_revision_headers(binding.artifact_revision),
        )

    return router


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidArtifactRevisionError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, PartNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ExactGeometryUnavailableError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ArtifactRevisionMismatchError):
        return HTTPException(
            status_code=409,
            detail={
                "code": "artifact_revision_mismatch",
                "message": str(exc),
                "stale": True,
                "requested_revision": exc.requested_revision,
                "current_revision": exc.current_revision,
            },
        )
    if isinstance(exc, ArtifactBytesChangedError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, RegistryError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _revision_headers(artifact_revision: str) -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "ETag": f'"{artifact_revision}"',
        "X-Flow-CAD-Artifact-Revision": artifact_revision,
        "X-Flow-CAD-Geometry-Authority": "step_kernel",
    }
