"""Immediate command routes for replacement scoped part builds."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from flow_cad.build import (
    BuildContractError,
    PartBuildService,
    PartNotFoundError,
    ProjectBuildService,
)
from flow_cad.jobs import IdempotencyConflictError, JobStoreError


class PartBuildRequest(BaseModel):
    request_id: str
    generate_snapshots: bool = False


class ProjectBuildRequest(BaseModel):
    request_id: str
    mode: Literal["default", "changed", "assembly-preview", "handoff"] = "default"
    create_report: bool = True
    create_bundle: bool = False
    generate_stl: bool = True
    generate_snapshots: bool = False


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
                generate_snapshots=request.generate_snapshots,
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


def create_project_build_router(service: ProjectBuildService) -> APIRouter:
    router = APIRouter(
        prefix="/api/workbench/v1/build",
        tags=["project build commands"],
    )

    @router.post("", status_code=202)
    def submit_project_build(request: ProjectBuildRequest) -> dict[str, object]:
        try:
            submission = service.submit(
                request_id=request.request_id,
                mode=request.mode,
                create_report=request.create_report,
                create_bundle=request.create_bundle,
                generate_stl=request.generate_stl,
                generate_snapshots=request.generate_snapshots,
            )
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
