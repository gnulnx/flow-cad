from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Mapping
from pathlib import Path

from fastapi.testclient import TestClient

from flow_cad.chat import ChatDispatchService, ChatStore, ContextPacket
from flow_cad.chat.providers import ProviderCancellation, ProviderEvent
from flow_cad.viewer.api import create_workbench_app


TERMINAL_EVENTS = {"assistant_completed", "assistant_failed", "turn_cancelled"}


class FakeProvider:
    name = "fake-provider"
    available = True

    def __init__(
        self,
        events: tuple[ProviderEvent, ...] = (ProviderEvent("completed"),),
        *,
        block: bool = False,
    ) -> None:
        self.events = events
        self.block = block
        self.calls: list[dict[str, object]] = []
        self.release = threading.Event()
        self.started = threading.Condition()
        self.started_count = 0
        self.cancellation_seen = threading.Event()

    def stream_turn(
        self,
        *,
        thread_id: str,
        turn_id: str,
        prompt: str,
        context: Mapping[str, object],
        cancellation: ProviderCancellation,
    ) -> Iterator[ProviderEvent]:
        self.calls.append(
            {
                "thread_id": thread_id,
                "turn_id": turn_id,
                "prompt": prompt,
                "context": dict(context),
            }
        )
        with self.started:
            self.started_count += 1
            self.started.notify_all()
        if self.block:
            while not self.release.wait(0.01):
                if cancellation.cancelled:
                    self.cancellation_seen.set()
                    yield ProviderEvent("cancelled", "Turn cancelled.")
                    return
        for event in self.events:
            yield event

    def wait_for_starts(self, count: int, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        with self.started:
            while self.started_count < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"provider did not start {count} turns")
                self.started.wait(remaining)


def _begin(store: ChatStore, content: str = "Inspect the selected part") -> str:
    _, assistant = store.begin_turn(
        "default",
        content,
        ContextPacket(selected_part_uuid="part-1", viewer_revision="7"),
    )
    assert assistant.turn_id is not None
    return assistant.turn_id


def _wait_for_terminal(
    store: ChatStore, turn_id: str, timeout: float = 2.0
) -> tuple[str, ...]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        event_types = tuple(
            event.event_type for event in store.turn_events("default", turn_id)
        )
        if any(event_type in TERMINAL_EVENTS for event_type in event_types):
            return event_types
        time.sleep(0.01)
    raise TimeoutError(f"chat turn did not finish: {turn_id}")


def test_dispatch_persists_bounded_provider_events_after_optimistic_rows(
    tmp_path: Path,
) -> None:
    store = ChatStore(tmp_path)
    turn_id = _begin(store)
    provider = FakeProvider(
        (
            ProviderEvent("progress", "Connecting.", {"phase": "connecting"}),
            ProviderEvent("reasoning", "Checking exact context."),
            ProviderEvent("tool", "Inspected selected part.", {"phase": "completed"}),
            ProviderEvent("content", "The mounting centers are aligned."),
            ProviderEvent("completed", details={"provider_turn_id": "provider-turn-1"}),
        )
    )
    dispatch = ChatDispatchService(store, provider, recover_pending=False)
    try:
        result = dispatch.start_turn("default", turn_id)
        assert result == {
            "provider": "fake-provider",
            "status": "queued",
            "created": True,
        }
        _wait_for_terminal(store, turn_id)

        events = store.turn_events("default", turn_id)
        assert [event.event_type for event in events[:2]] == [
            "user_message",
            "assistant_created",
        ]
        assert [event.event_type for event in events[2:]] == [
            "assistant_progress",
            "assistant_progress",
            "assistant_progress",
            "assistant_progress",
            "assistant_delta",
            "assistant_completed",
        ]
        assert events[-2].payload["content"] == "The mounting centers are aligned."
        assert events[-1].payload["provider_turn_id"] == "provider-turn-1"
        assert provider.calls == [
            {
                "thread_id": "default",
                "turn_id": turn_id,
                "prompt": "Inspect the selected part",
                "context": {
                    "selected_part_uuid": "part-1",
                    "visible_occurrence_ids": [],
                    "artifact_hashes": {},
                    "camera": {},
                    "measurements": [],
                    "annotations": [],
                    "viewport_attachment": None,
                    "viewer_revision": "7",
                },
            }
        ]
    finally:
        dispatch.shutdown()


def test_dispatch_recovers_nonterminal_turns_and_bounds_capacity(
    tmp_path: Path,
) -> None:
    store = ChatStore(tmp_path)
    first = _begin(store, "First")
    second = _begin(store, "Second")
    third = _begin(store, "Third")
    provider = FakeProvider(block=True)
    dispatch = ChatDispatchService(
        store,
        provider,
        max_concurrency=1,
        max_queued_turns=1,
    )
    try:
        provider.wait_for_starts(1)
        status = dispatch.status()
        assert status["running_turns"] == 1
        assert status["queued_turns"] == 1
        assert status["status"] == "busy"

        third_events = store.turn_events("default", third)
        assert third_events[-1].event_type == "assistant_failed"
        assert third_events[-1].payload["reason"] == "dispatch_capacity"

        provider.release.set()
        _wait_for_terminal(store, first)
        _wait_for_terminal(store, second)
        provider.wait_for_starts(2)
        assert [call["prompt"] for call in provider.calls] == ["First", "Second"]
    finally:
        provider.release.set()
        dispatch.shutdown()


def test_dispatch_serializes_turns_that_share_a_provider_thread(tmp_path: Path) -> None:
    store = ChatStore(tmp_path)
    first = _begin(store, "First")
    second = _begin(store, "Second")
    provider = FakeProvider(block=True)
    dispatch = ChatDispatchService(
        store,
        provider,
        max_concurrency=2,
        max_queued_turns=2,
        recover_pending=False,
    )
    try:
        dispatch.start_turn("default", first)
        provider.wait_for_starts(1)
        dispatch.start_turn("default", second)
        time.sleep(0.05)
        assert provider.started_count == 1

        provider.release.set()
        provider.wait_for_starts(2)
        _wait_for_terminal(store, first)
        _wait_for_terminal(store, second)
        assert [call["prompt"] for call in provider.calls] == ["First", "Second"]
    finally:
        provider.release.set()
        dispatch.shutdown()


def test_workbench_api_exposes_provider_status_and_cancels_active_turn(
    tmp_path: Path,
) -> None:
    provider = FakeProvider(block=True)
    app = create_workbench_app(tmp_path, chat_provider=provider)
    with TestClient(app) as client:
        status = client.get("/api/chat/provider")
        assert status.status_code == 200
        assert status.json() == {
            "provider": "fake-provider",
            "available": True,
            "status": "ready",
            "running_turns": 0,
            "queued_turns": 0,
            "max_concurrent_turns": 1,
            "max_queued_turns": 8,
            "execution_policy": {
                "sandbox": "read-only",
                "approval_policy": "never",
            },
            "diagnostics": {},
        }

        submitted = client.post(
            "/api/chat/threads/default/turns",
            json={
                "content": "Inspect only",
                "request_id": "cancel-request",
                "context": {"selected_part_uuid": "part-1"},
            },
        )
        assert submitted.status_code == 202
        assert [event["event_type"] for event in submitted.json()["events"]] == [
            "user_message",
            "assistant_created",
        ]
        provider.wait_for_starts(1)

        repeated = client.post(
            "/api/chat/threads/default/turns",
            json={
                "content": "Ignored duplicate content",
                "request_id": "cancel-request",
            },
        )
        assert repeated.status_code == 202
        assert repeated.json()["turn_id"] == submitted.json()["turn_id"]
        assert provider.started_count == 1

        turn_id = submitted.json()["turn_id"]
        cancelled = client.post(f"/api/chat/threads/default/turns/{turn_id}/cancel")
        assert cancelled.status_code == 202
        assert cancelled.json()["accepted"] is True
        assert cancelled.json()["event"]["event_type"] == "turn_cancelled"
        assert provider.cancellation_seen.wait(2.0)

        events = client.get("/api/chat/threads/default").json()["events"]
        turn_events = [event for event in events if event["turn_id"] == turn_id]
        assert turn_events[-1]["event_type"] == "turn_cancelled"
        assert [event["event_type"] for event in turn_events[:2]] == [
            "user_message",
            "assistant_created",
        ]


def test_unavailable_provider_leaves_retryable_durable_failure(tmp_path: Path) -> None:
    app = create_workbench_app(tmp_path, enable_default_chat_provider=False)
    with TestClient(app) as client:
        status = client.get("/api/chat/provider").json()
        assert status["available"] is False
        assert status["status"] == "unavailable"

        submitted = client.post(
            "/api/chat/threads/default/turns",
            json={"content": "Can you inspect this?", "request_id": "no-provider"},
        )
        assert submitted.status_code == 202
        assert submitted.json()["provider_status"] == "failed"

        turn_id = submitted.json()["turn_id"]
        events = client.get("/api/chat/threads/default").json()["events"]
        failure = next(
            event
            for event in events
            if event["turn_id"] == turn_id and event["event_type"] == "assistant_failed"
        )
        assert failure["payload"]["reason"] == "provider_unavailable"
        assert failure["payload"]["retryable"] is True
