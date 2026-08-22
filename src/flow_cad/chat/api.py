"""Thin HTTP routes over provider-independent chat storage."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .dispatch import ChatDispatchError, ChatDispatchService
from .models import ChatEvent, ChatThread, ContextPacket
from .store import ChatStore, ChatStoreError, ThreadNotFoundError


class CreateThreadRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class ContextPacketRequest(BaseModel):
    selected_part_uuid: str | None = None
    visible_occurrence_ids: list[str] = Field(default_factory=list)
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    camera: dict[str, Any] = Field(default_factory=dict)
    measurements: list[dict[str, Any]] = Field(default_factory=list)
    annotations: list[dict[str, Any]] = Field(default_factory=list)
    viewport_attachment: dict[str, Any] | None = None
    viewer_revision: str | None = None

    def to_context(self) -> ContextPacket:
        return ContextPacket(
            selected_part_uuid=self.selected_part_uuid,
            visible_occurrence_ids=tuple(self.visible_occurrence_ids),
            artifact_hashes=self.artifact_hashes,
            camera=self.camera,
            measurements=tuple(self.measurements),
            annotations=tuple(self.annotations),
            viewport_attachment=self.viewport_attachment,
            viewer_revision=self.viewer_revision,
        )


class BeginTurnRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    context: ContextPacketRequest = Field(default_factory=ContextPacketRequest)
    request_id: str | None = Field(default=None, min_length=1, max_length=200)


def create_chat_query_router(
    store: ChatStore,
    dispatch: ChatDispatchService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/chat", tags=["chat-query"])

    @router.get("/provider")
    def get_provider_status() -> dict[str, object]:
        if dispatch is None:
            return {
                "provider": None,
                "available": False,
                "status": "unavailable",
                "running_turns": 0,
                "queued_turns": 0,
                "max_concurrent_turns": 0,
                "max_queued_turns": 0,
                "execution_policy": {
                    "sandbox": "read-only",
                    "approval_policy": "never",
                },
                "diagnostics": {
                    "executable_available": False,
                    "authenticated": False,
                    "auth_method": None,
                    "last_failure_reason": None,
                    "last_rpc_method": None,
                },
            }
        return dispatch.status()

    @router.get("/threads")
    def list_threads() -> dict[str, object]:
        threads = store.list_threads()
        return {
            "threads": [_thread_summary(thread) for thread in threads],
            "count": len(threads),
        }

    @router.get("/threads/{thread_id}")
    def get_thread(thread_id: str, after_sequence: int = 0) -> dict[str, object]:
        try:
            thread = store.get_thread(thread_id)
        except ThreadNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        events = tuple(event for event in thread.events if event.sequence > after_sequence)
        return {
            **_thread_summary(thread),
            "events": [_event_payload(event) for event in events],
            "after_sequence": after_sequence,
        }

    @router.get("/threads/{thread_id}/turns/{turn_id}/stream")
    def stream_turn(
        thread_id: str,
        turn_id: str,
        after_sequence: int = 0,
    ) -> StreamingResponse:
        """Stream one durable turn and close after its terminal event."""

        try:
            store.turn_events(thread_id, turn_id)
        except ThreadNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ChatStoreError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

        async def event_stream():
            cursor = after_sequence
            while True:
                events = tuple(
                    event
                    for event in store.turn_events(thread_id, turn_id)
                    if event.sequence > cursor
                )
                terminal_seen = False
                for event in events:
                    cursor = event.sequence
                    terminal_seen = event.event_type in {
                        "assistant_completed",
                        "assistant_failed",
                        "turn_cancelled",
                    }
                    payload = json.dumps(
                        _event_payload(event),
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    yield (
                        f"id: {event.sequence}\n"
                        f"event: {event.event_type}\n"
                        f"data: {payload}\n\n"
                    )
                if terminal_seen:
                    break
                await asyncio.sleep(0.05)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
            },
        )

    return router


def create_chat_command_router(
    store: ChatStore,
    dispatch: ChatDispatchService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/chat", tags=["chat-command"])

    @router.post("/threads", status_code=201)
    def create_thread(request: CreateThreadRequest) -> dict[str, object]:
        try:
            thread = store.create_thread(request.title)
        except ChatStoreError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return _thread_summary(thread)

    @router.post("/threads/{thread_id}/turns", status_code=202)
    def begin_turn(thread_id: str, request: BeginTurnRequest) -> dict[str, object]:
        try:
            user, assistant = store.begin_turn(
                thread_id,
                request.content,
                request.context.to_context(),
                request_id=request.request_id,
            )
        except ThreadNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ChatStoreError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        dispatch_result = (
            dispatch.start_turn(thread_id, str(user.turn_id))
            if dispatch is not None and user.turn_id is not None
            else {"provider": None, "status": "awaiting_dispatch", "created": False}
        )
        return {
            "thread_id": thread_id,
            "turn_id": user.turn_id,
            "events": [_event_payload(user), _event_payload(assistant)],
            "provider": dispatch_result["provider"],
            "provider_status": dispatch_result["status"],
        }

    @router.post("/threads/{thread_id}/turns/{turn_id}/cancel", status_code=202)
    def cancel_turn(thread_id: str, turn_id: str) -> dict[str, object]:
        try:
            if dispatch is None:
                event = store.append_turn_event(
                    thread_id,
                    turn_id,
                    "turn_cancelled",
                    {"status": "cancelled", "provider": None},
                )
                accepted = True
            else:
                event, accepted = dispatch.cancel_turn(thread_id, turn_id)
        except ThreadNotFoundError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ChatStoreError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ChatDispatchError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return {
            "event": _event_payload(event),
            "accepted": accepted,
            "provider_status": "cancelled",
        }

    return router


def _thread_summary(thread: ChatThread) -> dict[str, object]:
    return {
        "thread_id": thread.thread_id,
        "title": thread.title,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
        "last_sequence": thread.events[-1].sequence,
    }


def _event_payload(event: ChatEvent) -> dict[str, object]:
    return {
        "sequence": event.sequence,
        "event_id": event.event_id,
        "thread_id": event.thread_id,
        "turn_id": event.turn_id,
        "event_type": event.event_type,
        "created_at": event.created_at,
        "payload": dict(event.payload),
    }
