"""Observable query, cancellation, and SSE routes for bounded workbench jobs."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from flow_cad.jobs import JobNotFoundError, JobService, JobState, JobStoreError


def create_job_router(service: JobService) -> APIRouter:
    router = APIRouter(prefix="/api/workbench/v1/jobs", tags=["jobs"])

    @router.get("")
    def list_jobs(
        state: JobState | None = None,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, object]:
        jobs = service.store.list(state=state, limit=limit)
        return {"jobs": [job.as_dict() for job in jobs], "count": len(jobs)}

    @router.get("/{job_id}")
    def get_job(job_id: str) -> dict[str, object]:
        try:
            return service.get(job_id).as_dict()
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.get("/{job_id}/events")
    def get_events(
        job_id: str,
        after_sequence: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, object]:
        try:
            service.get(job_id)
            events = service.events(
                job_id=job_id,
                after_sequence=after_sequence,
                limit=limit,
            )
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"events": [event.as_dict() for event in events], "count": len(events)}

    @router.get("/{job_id}/stream")
    def stream_events(job_id: str, after_sequence: int = Query(default=0, ge=0)) -> StreamingResponse:
        try:
            service.get(job_id)
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        async def event_stream():
            cursor = after_sequence
            yield "retry: 250\n\n"
            while True:
                events = service.events(job_id=job_id, after_sequence=cursor, limit=100)
                for event in events:
                    cursor = event.sequence
                    payload = json.dumps(event.as_dict(), sort_keys=True, separators=(",", ":"))
                    yield f"id: {event.sequence}\nevent: {event.event_type}\ndata: {payload}\n\n"
                record = service.get(job_id)
                if record.state.terminal and not service.events(
                    job_id=job_id,
                    after_sequence=cursor,
                    limit=1,
                ):
                    break
                await asyncio.sleep(0.1)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post("/{job_id}/cancel", status_code=202)
    def cancel_job(job_id: str) -> dict[str, object]:
        try:
            return service.cancel(job_id).as_dict()
        except JobNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except JobStoreError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return router
