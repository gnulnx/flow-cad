from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Any

from flow_cad.viewer.agent_runtime import (
    CodexExecAgentRuntimeClient,
    CodexRuntimeError,
    FakeAgentRuntimeClient,
    LlamaCppAgentRuntimeClient,
    build_compact_tool_schemas,
    compact_context_packet,
    normalize_sse_response_lines,
)


def test_fake_runtime_streaming_order_is_deterministic() -> None:
    client = FakeAgentRuntimeClient()

    events = list(
        client.stream_chat(
            thread_id="thread_1",
            messages=[{"role": "user", "content": "Run a quick plan"}],
            context_packet={
                "thread_id": "thread_1",
                "project": {"project_id": "flow_example"},
                "selected_part_ids": ["example_block"],
            },
            tools=[
                {"name": "read_viewer_context", "description": "Read", "parameters": {"properties": {}}},
                {"name": "write_file", "description": "Nope"},
            ],
            model_profile="default",
        )
    )

    assert [event["type"] for event in events] == [
        "assistant_delta",
        "tool_call",
        "tool_result",
        "done",
    ]
    assert events[1]["tool"] == "read_viewer_context"
    assert events[1]["arguments"]["selected_part_count"] == 1
    assert events[2]["result"]["message_count"] == 1


def test_compact_context_packet_shape_is_trimmed() -> None:
    compact = compact_context_packet(
        {
            "thread_id": "thread_42",
            "project": {
                "project_id": "flow_example",
                "name": "Flow Example",
                "active_assembly_id": "assembly_main",
                "revision": 17,
            },
            "viewer": {
                "selected_part_ids": ["part_a", "part_b"],
                "visible_part_ids": ["part_a"],
                "viewport_size": {"width": 1280, "height": 720},
                "viewport_screenshot": "att_001",
            },
            "draft_transaction_token": "txn_001",
            "preview_model_token": "preview_001",
            "validator_report_ids": ["val_a", "val_b"],
            "profile_ids": ["profile_main"],
            "measurements": [{"id": "m1"}, {"id": "m2"}],
            "noisy_field": "ignore me",
        }
    )

    assert compact["thread_id"] == "thread_42"
    assert compact["project"]["project_id"] == "flow_example"
    assert compact["project"]["project_name"] == "Flow Example"
    assert compact["project"]["active_assembly_id"] == "assembly_main"
    assert compact["draft"]["draft_transaction_token"] == "txn_001"
    assert compact["draft"]["preview_model_token"] == "preview_001"
    assert compact["viewer"]["selected_part_ids"] == ["part_a", "part_b"]
    assert compact["viewer"]["visible_part_ids"] == ["part_a"]
    assert compact["viewer"]["viewport_size"] == {"width": 1280, "height": 720}
    assert compact["viewer"]["measurement_count"] == 2
    assert compact["artifacts"]["validator_reports"] == ["val_a", "val_b"]
    assert compact["artifacts"]["profile_ids"] == ["profile_main"]
    assert "noisy_field" not in compact


def test_build_compact_tool_schemas_filters_unsafe_tools() -> None:
    schemas = build_compact_tool_schemas(
        [
            {"name": "read_viewer_context", "description": "Read context", "parameters": {"properties": {"part_id": {"type": "string"}}}},
            {"name": "request_visual_evidence", "description": "Request render", "parameters": {"properties": {"thread_id": {"type": "string"}}}},
            {"name": "run_command", "description": "Shell hook"},
            {"name": "create_draft_transaction", "parameters": {"properties": {"part_id": {"type": "string"}, "op": {"type": "string"}}}},
            {"name": "write_file", "description": "Filesystem"},
            {"name": "generate_preview_model", "description": "Build preview"},
            {"name": "run_shell", "description": "Bash"},
            {"name": "read_profile_summary", "description": "Profile"},
        ]
    )

    schema_names = [schema["function"]["name"] for schema in schemas]
    assert schema_names == [
        "read_viewer_context",
        "request_visual_evidence",
        "create_draft_transaction",
        "generate_preview_model",
        "read_profile_summary",
    ]
    assert all("write_file" not in schema["function"]["name"] for schema in schemas)
    assert all("run_command" not in schema["function"]["name"] for schema in schemas)
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["parameters"]["additionalProperties"] is False
    assert schemas[0]["function"]["parameters"]["required"] == []


def _fake_http_lines() -> list[bytes]:
    return [
        b'data: {"type":"assistant_delta","text":"ready..."}\n',
        b'data: {"type":"assistant_delta","text":" next"}\n',
        b'data: {"choices":[{"delta":{"content":"part "} } ]}\n',
        b'data: {"type":"tool_call","tool":"run_focused_validator","arguments":{"name":"wall-clearance"}}\n',
        b'data: {"type":"tool_result","tool":"run_focused_validator","result":{"status":"pass","score":0.98}}\n',
        b'data: [DONE]\n',
    ]


def test_http_sse_line_normalization_produces_normalized_events() -> None:
    events = normalize_sse_response_lines(_fake_http_lines(), thread_id="thread_http")

    assert [event["type"] for event in events] == [
        "assistant_delta",
        "assistant_delta",
        "assistant_delta",
        "tool_call",
        "tool_result",
        "done",
    ]
    assert events[0]["text"] == "ready..."
    assert events[1]["text"] == " next"
    assert events[2]["text"] == "part "
    assert events[3]["tool"] == "run_focused_validator"
    assert events[3]["arguments"] == {"name": "wall-clearance"}
    assert events[4]["result"]["status"] == "pass"
    assert events[4]["result"]["score"] == 0.98
    assert events[5]["type"] == "done"


@dataclass
class _FakeResponse:
    lines: list[bytes]

    def readlines(self) -> list[bytes]:
        return self.lines


def test_http_adapter_supports_fake_response_in_helper_path() -> None:
    response = _FakeResponse(
        [
            b'data: {"type":"assistant_delta","text":"streamed"}\n',
            b'data: [DONE]\n',
        ]
    )
    events = normalize_sse_response_lines(response.readlines(), thread_id="thread_fake")
    assert events == [
        {"type": "assistant_delta", "thread_id": "thread_fake", "text": "streamed"},
        {"type": "done", "thread_id": "thread_fake"},
    ]


@dataclass
class _FakeStreamingResponse:
    lines: list[bytes]

    def __enter__(self) -> "_FakeStreamingResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def __iter__(self):
        return iter(self.lines)


def test_http_adapter_stream_chat_yields_incrementally_from_response_lines() -> None:
    requests: list[Any] = []

    def opener(request: Any, timeout: float) -> _FakeStreamingResponse:
        requests.append((request, timeout))
        return _FakeStreamingResponse(
            [
                b'data: {"type":"assistant_delta","text":"streamed"}\n',
                b'data: [DONE]\n',
            ]
        )

    client = LlamaCppAgentRuntimeClient(
        endpoint="http://127.0.0.1:8080",
        model="local-model",
        opener=opener,
    )
    events = list(
        client.stream_chat(
            thread_id="thread_http_client",
            messages=[{"role": "user", "content": "hello"}],
            context_packet={"thread_id": "thread_http_client"},
            tools=[{"name": "read_viewer_context"}],
            model_profile="default",
        )
    )

    assert events == [
        {"type": "assistant_delta", "thread_id": "thread_http_client", "text": "streamed"},
        {"type": "done", "thread_id": "thread_http_client"},
    ]
    assert requests


def test_codex_exec_runtime_builds_read_only_ephemeral_command_and_parses_final_message() -> None:
    calls: list[dict[str, Any]] = []

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"command": command, "kwargs": kwargs})
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"type":"thread.started","thread_id":"codex-thread"}\n'
                '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"status\\":\\"ready\\",\\"next_flow_cad_action\\":\\"read_viewer_context\\"}"}}\n'
                '{"type":"turn.completed"}\n'
            ),
            stderr="",
        )

    client = CodexExecAgentRuntimeClient(
        project_root="/tmp/flow-project",
        codex_command="codex-test",
        model="gpt-test",
        runner=runner,
    )

    events = list(
        client.stream_chat(
            thread_id="thread_codex",
            messages=[{"role": "user", "content": "Check the wheel box clearance"}],
            context_packet={
                "thread_id": "thread_codex",
                "project": {"project_id": "b3_robot", "active_assembly_id": "b3_v2_robot"},
                "viewer": {
                    "selected_part_ids": ["wheel_box_test_body"],
                    "visible_part_ids": ["wheel_box_test_body"],
                },
            },
            tools=[
                {"name": "read_viewer_context", "description": "Read context"},
                {"name": "write_file", "description": "Unsafe"},
            ],
            model_profile={"provider": "codex"},
        )
    )

    assert events == [
        {
            "type": "assistant_delta",
            "thread_id": "thread_codex",
            "text": '{"status":"ready","next_flow_cad_action":"read_viewer_context"}',
        },
        {"type": "done", "thread_id": "thread_codex", "runtime": "codex_exec"},
    ]
    assert calls
    command = calls[0]["command"]
    assert command[:5] == ["codex-test", "exec", "--json", "--ephemeral", "--sandbox"]
    assert "read-only" in command
    assert "--skip-git-repo-check" in command
    assert "-C" in command
    assert "/tmp/flow-project" in command
    assert "--model" in command
    prompt = command[-1]
    assert "FLOW_CAD_CONTEXT=" in prompt
    assert "wheel_box_test_body" in prompt
    assert "read_viewer_context" in prompt
    assert "write_file" not in prompt
    assert "draft transaction, preview, focused validation, and explicit user acceptance" in prompt
    assert calls[0]["kwargs"]["capture_output"] is True
    assert calls[0]["kwargs"]["stdin"] is subprocess.DEVNULL
    assert calls[0]["kwargs"]["text"] is True
    assert calls[0]["kwargs"]["check"] is False


def test_codex_exec_runtime_reports_nonzero_exit() -> None:
    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 12, stdout="", stderr="codex auth failed")

    client = CodexExecAgentRuntimeClient(
        project_root="/tmp/flow-project",
        codex_command="codex-test",
        runner=runner,
    )

    try:
        list(
            client.stream_chat(
                thread_id="thread_codex",
                messages=[],
                context_packet={"thread_id": "thread_codex"},
                tools=[],
                model_profile=None,
            )
        )
    except CodexRuntimeError as exc:
        assert "Codex runtime exited with status 12" in str(exc)
        assert "codex auth failed" in str(exc)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("Expected CodexRuntimeError")
