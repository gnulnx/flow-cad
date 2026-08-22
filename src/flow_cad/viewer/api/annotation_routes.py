"""Thin annotation query/command routes over the append-only review journal."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from flow_cad.annotations import (
    AnnotationContext,
    AnnotationMark,
    AnnotationStore,
    AnnotationStoreError,
    AnnotationValidationError,
    IdempotencyConflictError,
    NormalizedPoint,
)


class AnnotationMarkRequest(BaseModel):
    mark_id: str = Field(min_length=1, max_length=200)
    kind: Literal["pen", "circle", "arrow", "text"]
    points: list[tuple[float, float]] = Field(min_length=1)
    color: str = Field(min_length=1, max_length=100)
    stroke_width: float = Field(default=2.0, ge=0.25, le=20.0)
    text: str | None = Field(default=None, max_length=4_000)
    intent: Literal["review_intent"] = "review_intent"

    def to_mark(self) -> AnnotationMark:
        return AnnotationMark(
            mark_id=self.mark_id,
            kind=self.kind,
            points=tuple(NormalizedPoint(x=point[0], y=point[1]) for point in self.points),
            color=self.color,
            stroke_width=self.stroke_width,
            text=self.text,
            intent=self.intent,
        )


class AnnotationContextRequest(BaseModel):
    camera: dict[str, Any]
    viewport: dict[str, Any]
    artifact_revision: str = Field(min_length=1, max_length=500)
    visible_occurrence_ids: list[str] = Field(default_factory=list)
    viewer_revision: str | None = Field(default=None, max_length=500)

    def to_context(self) -> AnnotationContext:
        return AnnotationContext(
            camera=self.camera,
            viewport=self.viewport,
            artifact_revision=self.artifact_revision,
            visible_occurrence_ids=tuple(self.visible_occurrence_ids),
            viewer_revision=self.viewer_revision,
        )


class SaveAnnotationSnapshotRequest(BaseModel):
    request_id: str | None = Field(default=None, min_length=1, max_length=200)
    hidden: bool = False
    marks: list[AnnotationMarkRequest] = Field(default_factory=list)
    context: AnnotationContextRequest


def create_annotation_router(store: AnnotationStore) -> APIRouter:
    router = APIRouter(prefix="/api/annotations", tags=["annotations"])

    @router.get("/threads/{thread_id}/events")
    def list_events(
        thread_id: str,
        after_sequence: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, object]:
        try:
            events = store.events(thread_id, after_sequence=after_sequence, limit=limit)
        except AnnotationStoreError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"events": [event.as_dict() for event in events], "count": len(events)}

    @router.get("/threads/{thread_id}/latest")
    def latest_snapshot(thread_id: str, response: Response) -> dict[str, object]:
        try:
            snapshot = store.latest_snapshot(thread_id)
        except AnnotationStoreError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if snapshot is None:
            response.status_code = 204
            return {}
        return snapshot.as_dict()

    @router.post("/threads/{thread_id}/snapshots", status_code=201)
    def save_snapshot(
        thread_id: str,
        request: SaveAnnotationSnapshotRequest,
        response: Response,
    ) -> dict[str, object]:
        try:
            event, created = store.save_snapshot(
                thread_id=thread_id,
                marks=tuple(mark.to_mark() for mark in request.marks),
                context=request.context.to_context(),
                hidden=request.hidden,
                request_id=request.request_id,
            )
        except IdempotencyConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (AnnotationStoreError, AnnotationValidationError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        response.status_code = 201 if created else 200
        return {"created": created, "event": event.as_dict()}

    return router
