"""Thin saved-measurement routes over the append-only snapshot journal."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field

from flow_cad.measurement.snapshot_models import (
    MeasurementLabelState,
    MeasurementSnapshotValidationError,
)
from flow_cad.measurement.snapshot_store import (
    MeasurementSnapshotIdempotencyConflictError,
    MeasurementSnapshotStore,
    MeasurementSnapshotStoreError,
)


class MeasurementLabelStateRequest(BaseModel):
    measurement_id: str = Field(min_length=1, max_length=200)
    kind: Literal["distance", "edge_length"]
    title: str = Field(min_length=1, max_length=500)
    quality: Literal["exact", "approximate"]
    start_mm: tuple[float, float, float]
    end_mm: tuple[float, float, float]
    total_mm: float = Field(ge=0)
    delta_mm: tuple[float, float, float]
    feature_ids: list[str] = Field(default_factory=list, max_length=2)
    hidden: bool = False
    pinned: bool = False
    label_offset_px: tuple[float, float] = (0.0, 0.0)

    def to_state(self) -> MeasurementLabelState:
        return MeasurementLabelState(
            measurement_id=self.measurement_id,
            kind=self.kind,
            title=self.title,
            quality=self.quality,
            start_mm=self.start_mm,
            end_mm=self.end_mm,
            total_mm=self.total_mm,
            delta_mm=self.delta_mm,
            feature_ids=tuple(self.feature_ids),
            hidden=self.hidden,
            pinned=self.pinned,
            label_offset_px=self.label_offset_px,
        )


class SaveMeasurementSnapshotRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=200)
    artifact_revision: str = Field(min_length=64, max_length=64)
    measurements: list[MeasurementLabelStateRequest] = Field(default_factory=list)


def create_measurement_snapshot_router(store: MeasurementSnapshotStore) -> APIRouter:
    router = APIRouter(prefix="/api/measurements", tags=["saved measurements"])

    @router.get("/threads/{thread_id}/parts/{part_uuid}/snapshots")
    def list_snapshots(
        thread_id: str,
        part_uuid: str,
        after_sequence: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> dict[str, object]:
        try:
            events = store.snapshots(
                thread_id,
                part_uuid,
                after_sequence=after_sequence,
                limit=limit,
            )
        except MeasurementSnapshotStoreError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"events": [event.as_dict() for event in events], "count": len(events)}

    @router.get("/threads/{thread_id}/parts/{part_uuid}/latest")
    def latest_snapshot(
        thread_id: str,
        part_uuid: str,
        response: Response,
    ) -> dict[str, object]:
        try:
            snapshot = store.latest_snapshot(thread_id, part_uuid)
        except MeasurementSnapshotStoreError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if snapshot is None:
            response.status_code = 204
            return {}
        return snapshot.as_dict()

    @router.post("/threads/{thread_id}/parts/{part_uuid}/snapshots", status_code=201)
    def save_snapshot(
        thread_id: str,
        part_uuid: str,
        request: SaveMeasurementSnapshotRequest,
        response: Response,
    ) -> dict[str, object]:
        try:
            event, created = store.save_snapshot(
                thread_id=thread_id,
                part_uuid=part_uuid,
                artifact_revision=request.artifact_revision,
                measurements=tuple(measurement.to_state() for measurement in request.measurements),
                request_id=request.request_id,
            )
        except MeasurementSnapshotIdempotencyConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (MeasurementSnapshotStoreError, MeasurementSnapshotValidationError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        response.status_code = 201 if created else 200
        return {"created": created, "event": event.as_dict()}

    return router
