"""Immediate command route for strict-manifest production release gates."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from flow_cad.jobs import IdempotencyConflictError, JobStoreError

from .service import ReleaseGateError, ReleaseGateService


class ReleaseGateRequest(BaseModel):
    request_id: str


def create_release_gate_router(service: ReleaseGateService) -> APIRouter:
    router = APIRouter(
        prefix="/api/workbench/v1/release",
        tags=["release commands"],
    )

    @router.post("/gate", status_code=202)
    def submit_release_gate(request: ReleaseGateRequest) -> dict[str, object]:
        try:
            submission = service.submit(request_id=request.request_id)
        except IdempotencyConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ReleaseGateError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except JobStoreError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except (OSError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "created": submission.created,
            "job": submission.job.as_dict(),
        }

    return router
