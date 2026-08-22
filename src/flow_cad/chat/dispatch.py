"""Bounded provider dispatch over the durable chat event journal."""

from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from .models import ChatEvent, PendingChatTurn
from .providers import ChatProvider, ProviderCancellation, ProviderEvent
from .store import ChatStore, TERMINAL_TURN_EVENT_TYPES


class ChatDispatchError(RuntimeError):
    pass


@dataclass(slots=True)
class _ActiveTurn:
    submission: PendingChatTurn
    cancellation: ProviderCancellation
    state: str = "queued"
    future: Future[None] | None = None


class ChatDispatchService:
    """Start durable turns with fixed concurrency and bounded queue capacity."""

    def __init__(
        self,
        store: ChatStore,
        provider: ChatProvider | None,
        *,
        max_concurrency: int = 1,
        max_queued_turns: int = 8,
        recover_pending: bool = True,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        if max_queued_turns < 0:
            raise ValueError("max_queued_turns must not be negative")
        self.store = store
        self.provider = provider
        self.max_concurrency = max_concurrency
        self.max_queued_turns = max_queued_turns
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrency,
            thread_name_prefix="flow-cad-chat",
        )
        self._capacity = threading.BoundedSemaphore(max_concurrency + max_queued_turns)
        self._active: dict[tuple[str, str], _ActiveTurn] = {}
        self._provider_thread_locks: dict[str, threading.Lock] = {}
        self._lock = threading.RLock()
        self._closed = False

        if recover_pending:
            for submission in self.store.pending_turns():
                self._schedule(submission)

    @property
    def provider_name(self) -> str | None:
        if self.provider is None:
            return None
        name = getattr(self.provider, "name", None)
        return name if isinstance(name, str) and name else type(self.provider).__name__

    @property
    def provider_available(self) -> bool:
        if self.provider is None:
            return False
        available = getattr(self.provider, "available", True)
        try:
            return bool(available() if callable(available) else available)
        except Exception:
            return False

    def status(self) -> dict[str, object]:
        with self._lock:
            queued = sum(turn.state == "queued" for turn in self._active.values())
            running = sum(turn.state == "running" for turn in self._active.values())
            if self._closed:
                status = "stopping"
            elif not self.provider_available:
                status = "unavailable"
            elif running or queued:
                status = "busy"
            else:
                status = "ready"
            return {
                "provider": self.provider_name,
                "available": self.provider_available and not self._closed,
                "status": status,
                "running_turns": running,
                "queued_turns": queued,
                "max_concurrent_turns": self.max_concurrency,
                "max_queued_turns": self.max_queued_turns,
                "execution_policy": {
                    "sandbox": "read-only",
                    "approval_policy": "never",
                },
            }

    def start_turn(self, thread_id: str, turn_id: str) -> dict[str, object]:
        submission = self.store.turn_submission(thread_id, turn_id)
        terminal = self._terminal_event(thread_id, turn_id)
        if terminal is not None:
            return {
                "provider": self.provider_name,
                "status": _terminal_status(terminal),
                "created": False,
            }
        with self._lock:
            existing = self._active.get((thread_id, turn_id))
            if existing is not None:
                return {
                    "provider": self.provider_name,
                    "status": existing.state,
                    "created": False,
                }
        return self._schedule(submission)

    def cancel_turn(self, thread_id: str, turn_id: str) -> tuple[ChatEvent, bool]:
        with self._lock:
            terminal = self._terminal_event(thread_id, turn_id)
            if terminal is not None:
                return terminal, False
            # Validate the turn even if it was written by another process and
            # has not been recovered into this dispatcher's active map.
            self.store.turn_submission(thread_id, turn_id)
            active = self._active.get((thread_id, turn_id))
            if active is not None:
                active.cancellation.cancel()
                active.state = "cancelled"
                if active.future is not None:
                    active.future.cancel()
            event = self.store.append_turn_event(
                thread_id,
                turn_id,
                "turn_cancelled",
                {
                    "status": "cancelled",
                    "provider": self.provider_name,
                },
            )
            return event, True

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = False) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            active_turns = tuple(self._active.values()) if cancel_pending else ()
            for active in active_turns:
                active.cancellation.cancel()
                if active.future is not None:
                    active.future.cancel()
        self._executor.shutdown(wait=wait, cancel_futures=cancel_pending)

    def _schedule(self, submission: PendingChatTurn) -> dict[str, object]:
        with self._lock:
            if self._closed:
                raise ChatDispatchError("chat dispatch service is closed")
            if not self.provider_available:
                self._append_failure(
                    submission,
                    error="Chat provider is unavailable.",
                    reason="provider_unavailable",
                )
                return {
                    "provider": self.provider_name,
                    "status": "failed",
                    "created": False,
                }
            key = (submission.thread_id, submission.turn_id)
            existing = self._active.get(key)
            if existing is not None:
                return {
                    "provider": self.provider_name,
                    "status": existing.state,
                    "created": False,
                }
            if not self._capacity.acquire(blocking=False):
                self._append_failure(
                    submission,
                    error="Chat dispatch capacity is full.",
                    reason="dispatch_capacity",
                )
                return {
                    "provider": self.provider_name,
                    "status": "failed",
                    "created": False,
                }

            active = _ActiveTurn(
                submission=submission,
                cancellation=ProviderCancellation(),
            )
            self._active[key] = active
            try:
                active.future = self._executor.submit(self._run, active)
                active.future.add_done_callback(
                    lambda _future, turn_key=key: self._finish(turn_key)
                )
            except BaseException:
                self._active.pop(key, None)
                self._capacity.release()
                self._append_failure(
                    submission,
                    error="Chat turn could not be dispatched.",
                    reason="dispatch_error",
                )
                raise
            return {
                "provider": self.provider_name,
                "status": "queued",
                "created": True,
            }

    def _run(self, active: _ActiveTurn) -> None:
        submission = active.submission
        with self._lock:
            provider_thread_lock = self._provider_thread_locks.setdefault(
                submission.thread_id,
                threading.Lock(),
            )
        with provider_thread_lock:
            self._run_serialized(active)

    def _run_serialized(self, active: _ActiveTurn) -> None:
        submission = active.submission
        with self._lock:
            if (
                self._terminal_event(submission.thread_id, submission.turn_id)
                is not None
            ):
                return
            active.state = "running"
            self.store.append_turn_event(
                submission.thread_id,
                submission.turn_id,
                "assistant_progress",
                {
                    "provider": self.provider_name,
                    "kind": "progress",
                    "phase": "dispatching",
                    "content": "Chat provider started.",
                },
            )

        terminal = False
        try:
            assert self.provider is not None
            for provider_event in self.provider.stream_turn(
                thread_id=submission.thread_id,
                turn_id=submission.turn_id,
                prompt=submission.prompt,
                context=submission.context,
                cancellation=active.cancellation,
            ):
                terminal = self._persist_provider_event(active, provider_event)
                if terminal:
                    break
        except BaseException:
            with self._lock:
                if active.state not in {"completed", "failed", "cancelled"}:
                    self._append_failure(
                        submission,
                        error="Chat provider stopped unexpectedly.",
                        reason="provider_exception",
                    )
                    active.state = "failed"
            return

        with self._lock:
            if not terminal and active.state not in {
                "completed",
                "failed",
                "cancelled",
            }:
                self._append_failure(
                    submission,
                    error="Chat provider ended without a result.",
                    reason="provider_incomplete",
                )
                active.state = "failed"

    def _persist_provider_event(
        self,
        active: _ActiveTurn,
        provider_event: ProviderEvent,
    ) -> bool:
        submission = active.submission
        event_type, terminal = _stored_event_type(provider_event.kind)
        payload = _provider_payload(self.provider_name, provider_event)
        with self._lock:
            if active.state in {"completed", "failed", "cancelled"}:
                return True
            self.store.append_turn_event(
                submission.thread_id,
                submission.turn_id,
                event_type,
                payload,
            )
            if terminal:
                active.state = _event_type_status(event_type)
        return terminal

    def _append_failure(
        self,
        submission: PendingChatTurn,
        *,
        error: str,
        reason: str,
    ) -> ChatEvent:
        return self.store.append_turn_event(
            submission.thread_id,
            submission.turn_id,
            "assistant_failed",
            {
                "provider": self.provider_name,
                "error": error,
                "retryable": True,
                "reason": reason,
            },
        )

    def _terminal_event(self, thread_id: str, turn_id: str) -> ChatEvent | None:
        events = self.store.turn_events(thread_id, turn_id)
        return next(
            (
                event
                for event in reversed(events)
                if event.event_type in TERMINAL_TURN_EVENT_TYPES
            ),
            None,
        )

    def _finish(self, key: tuple[str, str]) -> None:
        with self._lock:
            if self._active.pop(key, None) is not None:
                self._capacity.release()


def _stored_event_type(kind: str) -> tuple[str, bool]:
    if kind == "content":
        return "assistant_delta", False
    if kind in {"reasoning", "progress", "tool"}:
        return "assistant_progress", False
    if kind == "completed":
        return "assistant_completed", True
    if kind == "failed":
        return "assistant_failed", True
    if kind == "cancelled":
        return "turn_cancelled", True
    return "assistant_progress", False


def _provider_payload(
    provider_name: str | None, event: ProviderEvent
) -> dict[str, Any]:
    payload: dict[str, Any] = dict(event.details or {})
    payload["provider"] = provider_name
    payload["kind"] = event.kind
    if event.content:
        if event.kind == "failed":
            payload["error"] = event.content
        else:
            payload["content"] = event.content
    if event.kind == "completed":
        payload.setdefault("status", "completed")
    elif event.kind == "cancelled":
        payload.setdefault("status", "cancelled")
    elif event.kind == "failed":
        payload.setdefault("retryable", True)
        payload.setdefault("error", "Chat provider failed.")
    return payload


def _terminal_status(event: ChatEvent) -> str:
    return _event_type_status(event.event_type)


def _event_type_status(event_type: str) -> str:
    return {
        "assistant_completed": "completed",
        "assistant_failed": "failed",
        "turn_cancelled": "cancelled",
    }.get(event_type, "terminal")
