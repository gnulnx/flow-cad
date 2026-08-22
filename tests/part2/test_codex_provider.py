from __future__ import annotations

import json
from collections import deque
from collections.abc import Mapping
from pathlib import Path

from flow_cad.chat.codex_provider import (
    CodexAppServerProvider,
    CodexThreadBindings,
    CodexTransportError,
)
from flow_cad.chat.providers import ChatProvider, ProviderCancellation
from flow_cad.chat.tools import ChatTool, ChatToolRegistry


class FakeAppServerTransport:
    """Protocol-level fake: no Codex model request leaves the test process."""

    def __init__(
        self,
        *,
        provider_thread_id: str = "provider-thread-1",
        resume: str = "ok",
        turn_notifications: list[dict[str, object]] | None = None,
        complete_on_interrupt: bool = False,
    ) -> None:
        self.provider_thread_id = provider_thread_id
        self.resume = resume
        self.turn_notifications = turn_notifications or []
        self.complete_on_interrupt = complete_on_interrupt
        self.sent: list[dict[str, object]] = []
        self.incoming: deque[object] = deque()
        self.closed = False

    def send(self, message: Mapping[str, object]) -> None:
        request = dict(message)
        self.sent.append(request)
        method = request.get("method")
        request_id = request.get("id")
        if method == "initialize":
            self.incoming.extend(
                [
                    {
                        "method": "remoteControl/status/changed",
                        "params": {"status": "disabled"},
                    },
                    {
                        "id": request_id,
                        "result": {
                            "userAgent": "fake/0.149.0",
                            "codexHome": "/tmp/fake-codex",
                            "platformFamily": "unix",
                            "platformOs": "linux",
                        },
                    },
                ]
            )
        elif method == "thread/start":
            self.incoming.append(
                {"id": request_id, "result": {"thread": {"id": self.provider_thread_id}}}
            )
        elif method == "thread/resume":
            if self.resume == "missing":
                self.incoming.append(
                    {
                        "id": request_id,
                        "error": {
                            "code": -32600,
                            "message": f"no rollout found for thread id {self.provider_thread_id}",
                        },
                    }
                )
            else:
                self.incoming.append(
                    {"id": request_id, "result": {"thread": {"id": self.provider_thread_id}}}
                )
        elif method == "turn/start":
            self.incoming.append(
                {"id": request_id, "result": {"turn": {"id": "provider-turn-1"}}}
            )
            self.incoming.extend(self.turn_notifications)
        elif method == "turn/interrupt":
            self.incoming.append({"id": request_id, "result": {}})
            if self.complete_on_interrupt:
                self.incoming.append(
                    _turn_completed(self.provider_thread_id, "provider-turn-1", "interrupted")
                )

    def receive(self, timeout: float | None = None) -> Mapping[str, object] | None:
        if not self.incoming:
            return None
        value = self.incoming.popleft()
        if isinstance(value, BaseException):
            raise value
        assert isinstance(value, Mapping)
        return value

    def close(self) -> None:
        self.closed = True


def _turn_completed(thread_id: str, turn_id: str, status: str) -> dict[str, object]:
    return {
        "method": "turn/completed",
        "params": {
            "threadId": thread_id,
            "turn": {"id": turn_id, "items": [], "status": status},
        },
    }


def _provider(
    root: Path, fake: FakeAppServerTransport, *, request_timeout: float = 0.1
) -> CodexAppServerProvider:
    provider = CodexAppServerProvider(
        root,
        transport_factory=lambda: fake,
        request_timeout=request_timeout,
    )
    _accepts_chat_provider(provider)
    return provider


def _accepts_chat_provider(provider: ChatProvider) -> None:
    del provider


def test_starts_durable_thread_sends_cad_context_and_maps_bounded_events(
    tmp_path: Path,
) -> None:
    secret_transcript = "RAW-TRANSCRIPT-MUST-NOT-LEAK"
    fake = FakeAppServerTransport(
        turn_notifications=[
            {
                "method": "item/agentMessage/delta",
                "params": {
                    "threadId": "provider-thread-1",
                    "turnId": "provider-turn-1",
                    "itemId": "message-1",
                    "delta": "The guard has two mounting centers.",
                },
            },
            {
                "method": "item/reasoning/summaryTextDelta",
                "params": {
                    "threadId": "provider-thread-1",
                    "turnId": "provider-turn-1",
                    "itemId": "reasoning-1",
                    "summaryIndex": 0,
                    "delta": "Checking the exact STEP context.",
                },
            },
            {
                "method": "item/reasoning/textDelta",
                "params": {
                    "threadId": "provider-thread-1",
                    "turnId": "provider-turn-1",
                    "itemId": "reasoning-1",
                    "delta": secret_transcript,
                },
            },
            {
                "method": "item/started",
                "params": {
                    "threadId": "provider-thread-1",
                    "turnId": "provider-turn-1",
                    "startedAtMs": 1,
                    "item": {
                        "id": "command-1",
                        "type": "commandExecution",
                        "command": f"printf {secret_transcript}",
                        "commandActions": [],
                        "cwd": str(tmp_path),
                        "status": "inProgress",
                    },
                },
            },
            {
                "method": "item/commandExecution/outputDelta",
                "params": {
                    "threadId": "provider-thread-1",
                    "turnId": "provider-turn-1",
                    "itemId": "command-1",
                    "delta": secret_transcript,
                },
            },
            {
                "method": "item/completed",
                "params": {
                    "threadId": "provider-thread-1",
                    "turnId": "provider-turn-1",
                    "completedAtMs": 2,
                    "item": {
                        "id": "command-1",
                        "type": "commandExecution",
                        "command": f"printf {secret_transcript}",
                        "commandActions": [],
                        "cwd": str(tmp_path),
                        "status": "completed",
                        "aggregatedOutput": secret_transcript,
                        "exitCode": 0,
                    },
                },
            },
            _turn_completed("provider-thread-1", "provider-turn-1", "completed"),
        ]
    )
    context = {
        "selected_part_uuid": "part-1",
        "visible_occurrence_ids": ["guard-primary"],
        "artifact_hashes": {"part-1": "a" * 64},
        "camera": {"position": [1, 2, 3]},
        "measurements": [{"distance_mm": 42.0}],
        "annotations": [{"kind": "arrow"}],
        "viewer_revision": "7",
    }

    events = list(
        _provider(tmp_path, fake).stream_turn(
            thread_id="default",
            turn_id="local-turn-1",
            prompt="Inspect the selected guard",
            context=context,
            cancellation=ProviderCancellation(),
        )
    )

    methods = [message.get("method") for message in fake.sent if "method" in message]
    assert methods[:4] == ["initialize", "initialized", "thread/start", "turn/start"]
    start_params = next(
        message["params"] for message in fake.sent if message.get("method") == "thread/start"
    )
    assert isinstance(start_params, dict)
    assert start_params["ephemeral"] is False
    assert start_params["sandbox"] == "read-only"
    assert start_params["approvalPolicy"] == "never"
    assert {tool["name"] for tool in start_params["dynamicTools"]} == {
        "flow_current_view",
        "flow_inspect_part",
        "flow_inspect_placement",
        "flow_request_build",
    }

    turn_params = next(
        message["params"] for message in fake.sent if message.get("method") == "turn/start"
    )
    assert isinstance(turn_params, dict)
    assert turn_params["input"] == [
        {"type": "text", "text": "Inspect the selected guard", "text_elements": []}
    ]
    assert turn_params["additionalContext"] == {"flow_cad": context}
    assert turn_params["clientUserMessageId"] == "local-turn-1"

    assert "content" in [event.kind for event in events]
    assert "reasoning" in [event.kind for event in events]
    assert [event.kind for event in events].count("tool") == 2
    assert events[-1].kind == "completed"
    assert secret_transcript not in repr(events)
    assert fake.closed

    bindings = json.loads((tmp_path / ".flow" / "codex-thread-bindings.json").read_text())
    assert bindings == {
        "bindings": {"default": "provider-thread-1"},
        "schema_version": 1,
    }


def test_provider_resumes_binding_after_restart(tmp_path: Path) -> None:
    bindings = CodexThreadBindings(tmp_path / ".flow" / "codex-thread-bindings.json")
    bindings.set("default", "provider-thread-1")
    fake = FakeAppServerTransport(
        turn_notifications=[
            _turn_completed("provider-thread-1", "provider-turn-1", "completed")
        ]
    )

    events = list(
        _provider(tmp_path, fake).stream_turn(
            thread_id="default",
            turn_id="local-turn-2",
            prompt="Continue the review",
            context={},
            cancellation=ProviderCancellation(),
        )
    )

    methods = [message.get("method") for message in fake.sent if "method" in message]
    assert "thread/resume" in methods
    assert "thread/start" not in methods
    assert any(event.details and event.details.get("resumed") is True for event in events)
    assert events[-1].kind == "completed"


def test_missing_durable_provider_thread_is_replaced(tmp_path: Path) -> None:
    bindings = CodexThreadBindings(tmp_path / ".flow" / "codex-thread-bindings.json")
    bindings.set("default", "provider-thread-1")
    fake = FakeAppServerTransport(
        resume="missing",
        turn_notifications=[
            _turn_completed("provider-thread-1", "provider-turn-1", "completed")
        ],
    )

    events = list(
        _provider(tmp_path, fake).stream_turn(
            thread_id="default",
            turn_id="local-turn-3",
            prompt="Continue",
            context={},
            cancellation=ProviderCancellation(),
        )
    )

    methods = [message.get("method") for message in fake.sent if "method" in message]
    assert methods.index("thread/resume") < methods.index("thread/start")
    assert events[-1].kind == "completed"


def test_cancellation_interrupts_the_active_codex_turn(tmp_path: Path) -> None:
    fake = FakeAppServerTransport(complete_on_interrupt=True)
    cancellation = ProviderCancellation()
    stream = _provider(tmp_path, fake).stream_turn(
        thread_id="default",
        turn_id="local-turn-4",
        prompt="Inspect",
        context={},
        cancellation=cancellation,
    )

    assert next(stream).details == {"phase": "connecting", "protocol": "v2"}
    thread_ready = next(stream)
    assert thread_ready.details and thread_ready.details.get("phase") == "thread_ready"
    assert any(message.get("method") == "thread/start" for message in fake.sent)
    running = next(stream)
    assert running.details and running.details.get("phase") == "running"
    cancellation.cancel()
    cancelling = next(stream)
    assert cancelling.details == {"phase": "cancelling"}
    terminal = next(stream)
    assert terminal.kind == "cancelled"
    assert list(stream) == []

    interrupt = next(message for message in fake.sent if message.get("method") == "turn/interrupt")
    assert interrupt["params"] == {
        "threadId": "provider-thread-1",
        "turnId": "provider-turn-1",
    }


def test_approval_requests_are_denied_without_exposing_request_payload(tmp_path: Path) -> None:
    secret_command = "rm -rf SHOULD-NEVER-BE-DISPLAYED"
    fake = FakeAppServerTransport(
        turn_notifications=[
            {
                "id": "approval-1",
                "method": "item/commandExecution/requestApproval",
                "params": {
                    "threadId": "provider-thread-1",
                    "turnId": "provider-turn-1",
                    "itemId": "command-1",
                    "command": secret_command,
                },
            },
            {
                "id": "approval-2",
                "method": "applyPatchApproval",
                "params": {
                    "conversationId": "provider-thread-1",
                    "callId": "patch-1",
                    "fileChanges": {"secret.py": secret_command},
                },
            },
            {
                "id": "approval-3",
                "method": "item/permissions/requestApproval",
                "params": {
                    "threadId": "provider-thread-1",
                    "turnId": "provider-turn-1",
                    "permissions": {"network": {"enabled": True}},
                },
            },
            _turn_completed("provider-thread-1", "provider-turn-1", "completed"),
        ]
    )

    events = list(
        _provider(tmp_path, fake).stream_turn(
            thread_id="default",
            turn_id="local-turn-5",
            prompt="Inspect only",
            context={},
            cancellation=ProviderCancellation(),
        )
    )

    response = next(message for message in fake.sent if message.get("id") == "approval-1")
    assert response == {"id": "approval-1", "result": {"decision": "decline"}}
    legacy_response = next(message for message in fake.sent if message.get("id") == "approval-2")
    assert legacy_response == {
        "id": "approval-2",
        "result": {
            "decision": {
                "denied": {
                    "rejection": "Flow CAD chat does not expose interactive approvals."
                }
            }
        },
    }
    permission_response = next(
        message for message in fake.sent if message.get("id") == "approval-3"
    )
    assert permission_response == {
        "id": "approval-3",
        "result": {
            "permissions": {},
            "scope": "turn",
            "strictAutoReview": False,
        },
    }
    assert any(
        event.details and event.details.get("phase") == "approval_declined" for event in events
    )
    assert secret_command not in repr(events)
    assert events[-1].kind == "completed"


def test_transport_failure_becomes_retryable_provider_event(tmp_path: Path) -> None:
    fake = FakeAppServerTransport()
    fake.incoming.appendleft(CodexTransportError("raw process details"))

    events = list(
        _provider(tmp_path, fake).stream_turn(
            thread_id="default",
            turn_id="local-turn-6",
            prompt="Inspect",
            context={},
            cancellation=ProviderCancellation(),
        )
    )

    assert events[-1].kind == "failed"
    assert events[-1].details == {"retryable": True, "reason": "transport_error"}
    assert "raw process details" not in repr(events)


def test_registered_dynamic_tool_call_returns_bounded_application_result(
    tmp_path: Path,
) -> None:
    fake = FakeAppServerTransport(
        turn_notifications=[
            {
                "id": "tool-request-1",
                "method": "item/tool/call",
                "params": {
                    "threadId": "provider-thread-1",
                    "turnId": "provider-turn-1",
                    "callId": "call-1",
                    "namespace": None,
                    "tool": "flow_probe",
                    "arguments": {"identity": "guard"},
                },
            },
            _turn_completed("provider-thread-1", "provider-turn-1", "completed"),
        ]
    )
    registry = ChatToolRegistry(
        (
            ChatTool(
                "flow_probe",
                "Inspect a bounded fixture.",
                {"type": "object"},
                lambda arguments, context: {
                    "identity": arguments["identity"],
                    "selected": context["selected_part_uuid"],
                },
            ),
        )
    )
    provider = CodexAppServerProvider(
        tmp_path,
        transport_factory=lambda: fake,
        request_timeout=0.1,
        tool_registry=registry,
    )

    events = list(
        provider.stream_turn(
            thread_id="default",
            turn_id="local-tool-turn",
            prompt="Inspect",
            context={"selected_part_uuid": "guard-uuid"},
            cancellation=ProviderCancellation(),
        )
    )

    response = next(message for message in fake.sent if message.get("id") == "tool-request-1")
    assert response == {
        "id": "tool-request-1",
        "result": {
            "success": True,
            "contentItems": [
                {
                    "type": "inputText",
                    "text": '{"identity":"guard","selected":"guard-uuid"}',
                }
            ],
        },
    }
    assert any(
        event.kind == "tool"
        and event.details == {"phase": "tool_completed", "tool": "flow_probe"}
        for event in events
    )
