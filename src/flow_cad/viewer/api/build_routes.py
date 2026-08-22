"""Immediate command routes for replacement scoped part builds."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from flow_cad.build import BuildContractError, PartBuildService, PartNotFoundError
from flow_cad.jobs import IdempotencyConflictError, JobStoreError


class PartBuildRequest(BaseModel):
    request_id: str


def create_part_build_router(service: PartBuildService) -> APIRouter:
    router = APIRouter(
        prefix="/api/workbench/v1/parts",
        tags=["part build commands"],
    )

    @router.post("/{part_key_or_uuid}/build", status_code=202)
    def submit_part_build(
        part_key_or_uuid: str,
        request: PartBuildRequest,
    ) -> dict[str, object]:
        try:
            submission = service.submit(
                request_id=request.request_id,
                part_key_or_uuid=part_key_or_uuid,
            )
        except PartNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except IdempotencyConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except BuildContractError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except JobStoreError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "created": submission.created,
            "job": submission.job.as_dict(),
        }

    return router
