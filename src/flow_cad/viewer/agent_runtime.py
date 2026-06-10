"""Runtime-neutral agent streaming adapters for the Flow CAD viewer."""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, Protocol, cast


NormalizedEvent = dict[str, Any]
Messages = Sequence[dict[str, Any]]


SAFE_TOOL_NAMES = (
    "read_viewer_context",
    "request_visual_evidence",
    "create_draft_transaction",
    "apply_draft_operations",
    "generate_preview_model",
    "run_focused_validator",
    "read_profile_summary",
    "summarize_acceptance_artifacts",
)

DISALLOWED_TOOL_NAMES = {
    "write_file",
    "run_command",
    "shell",
    "run_shell",
    "execute_command",
}



class AgentRuntimeError(RuntimeError):
    """Base class for runtime adapter failures."""


class AgentRuntimeClient(Protocol):
    """Runtime-neutral interface for streamed assistant adapters."""

    def stream_chat(
        self,
        thread_id: str,
        messages: Messages,
        context_packet: dict[str, Any],
        tools: Iterable[dict[str, Any]],
        model_profile: str | dict[str, Any] | None,
    ) -> Iterable[NormalizedEvent]:
        """Yield normalized stream events for a chat request."""


def _ensure_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _delta_text(value: Any) -> str:
    return value if isinstance(value, str) else str(value or "")


def _as_list_of_str(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text:
            result.append(text)
    return result


def _compact_message_payload(messages: Messages) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = _ensure_str(message.get("role")) or "user"
        content = message.get("content")
        if isinstance(content, str):
            content_text = content
        elif content is None:
            content_text = ""
        else:
            content_text = json.dumps(content, ensure_ascii=False)
        if content_text:
            payload.append({"role": role, "content": content_text})
    return payload


def compact_context_packet(context_packet: dict[str, Any]) -> dict[str, Any]:
    """Return a compact context packet containing only chat-relevant fields."""

    project = context_packet.get("project", {}) if isinstance(context_packet.get("project"), dict) else {}
    viewer = context_packet.get("viewer", {}) if isinstance(context_packet.get("viewer"), dict) else {}
    selected = _as_list_of_str(viewer.get("selected_part_ids", context_packet.get("selected_part_ids")))
    visible = _as_list_of_str(viewer.get("visible_part_ids", context_packet.get("visible_part_ids")))
    measurements = viewer.get("measurements", context_packet.get("measurements"))

    compact = {
        "thread_id": _ensure_str(context_packet.get("thread_id")) or "thread",
        "project": {
            "project_id": _ensure_str(project.get("project_id") or project.get("id")),
            "project_name": _ensure_str(project.get("project_name") or project.get("name")),
            "active_assembly_id": _ensure_str(project.get("active_assembly_id")),
            "backend_revision": project.get("revision") if isinstance(project.get("revision"), int) else None,
        },
        "draft": {
            "draft_transaction_token": _ensure_str(context_packet.get("draft_transaction_token")),
            "preview_model_token": _ensure_str(context_packet.get("preview_model_token")),
        },
        "viewer": {
            "selected_part_ids": selected,
            "visible_part_ids": visible,
            "viewport_size": viewer.get("viewport_size"),
            "viewport_screenshot": _ensure_str(viewer.get("viewport_screenshot"))
            or _ensure_str(context_packet.get("viewport_screenshot")),
            "measurement_count": len(measurements) if isinstance(measurements, list) else 0,
        },
        "artifacts": {
            "validator_reports": _as_list_of_str(context_packet.get("validator_report_ids")),
            "profile_ids": _as_list_of_str(context_packet.get("profile_ids")),
        },
    }

    compacted: dict[str, Any] = {}
    for key, value in compact.items():
        if isinstance(value, dict):
            filtered = {k: v for k, v in value.items() if v not in (None, "", [], {}, 0)}
            if filtered:
                compacted[key] = filtered
            continue
        if value not in (None, "", 0):
            compacted[key] = value
    return compacted


def _normalize_tool_parameters(
    tool: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(tool, dict):
        return {}
    parameters = tool.get("parameters")
    if not isinstance(parameters, dict):
        return {"type": "object", "properties": {}, "additionalProperties": False}
    props = parameters.get("properties")
    required = parameters.get("required", [])
    if not isinstance(props, dict):
        props = {}
    if not isinstance(required, list):
        required = []
    return {
        "type": "object",
        "properties": {name: desc for name, desc in props.items() if isinstance(name, str)},
        "required": [name for name in required if isinstance(name, str)],
        "additionalProperties": False,
    }


def build_compact_tool_schemas(tools: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build compact tool schemas with Flow CAD-safe tool names only."""

    result: list[dict[str, Any]] = []
    seen = set[str]()
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = _ensure_str(tool.get("name"))
        if not name or name in DISALLOWED_TOOL_NAMES:
            continue
        if name not in SAFE_TOOL_NAMES:
            continue
        if name in seen:
            continue
        seen.add(name)

        result.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": _ensure_str(tool.get("description")) or f"Run {name}.",
                    "parameters": _normalize_tool_parameters(tool),
                },
            }
        )
    return result


def _tool_result_event(tool_name: str | None, payload: Any, thread_id: str) -> NormalizedEvent:
    return {
        "type": "tool_result",
        "thread_id": thread_id,
        "tool": tool_name or "unknown",
        "result": payload if isinstance(payload, dict) else {"value": payload},
    }


def _assistant_delta_event(text: str, thread_id: str) -> NormalizedEvent:
    return {"type": "assistant_delta", "thread_id": thread_id, "text": text}


def _tool_call_event(tool_name: str, arguments: dict[str, Any], thread_id: str, tool_call_id: str | None = None) -> NormalizedEvent:
    event: NormalizedEvent = {
        "type": "tool_call",
        "thread_id": thread_id,
        "tool": tool_name,
        "arguments": arguments,
    }
    if tool_call_id:
        event["tool_call_id"] = tool_call_id
    return event


def _error_event(error: str, thread_id: str, details: Any | None = None) -> NormalizedEvent:
    return {
        "type": "error",
        "thread_id": thread_id,
        "error": error,
        **({"details": details} if details is not None else {}),
    }


def _normalize_tool_call_delta(tool_call: Mapping[str, Any], thread_id: str) -> list[NormalizedEvent]:
    events: list[NormalizedEvent] = []
    function_call = tool_call.get("function")
    name = None
    arguments: dict[str, Any] = {}
    if isinstance(function_call, dict):
        name = _ensure_str(function_call.get("name"))
        raw_args = function_call.get("arguments")
        if isinstance(raw_args, str):
            try:
                parsed_args = json.loads(raw_args)
                if isinstance(parsed_args, dict):
                    arguments = parsed_args
            except json.JSONDecodeError:
                arguments = {"_raw": raw_args}
        elif isinstance(raw_args, dict):
            arguments = raw_args
    elif isinstance(tool_call.get("name"), str):
        name = _ensure_str(tool_call.get("name"))
        raw_args = tool_call.get("arguments")
        if isinstance(raw_args, dict):
            arguments = raw_args
    if name is not None:
        events.append(
            _tool_call_event(
                name,
                arguments,
                thread_id=thread_id,
                tool_call_id=_ensure_str(tool_call.get("id")),
            )
        )
    return events


def normalize_llama_chunk(payload: Mapping[str, Any], thread_id: str) -> list[NormalizedEvent]:
    """Normalize one decoded SSE JSON payload."""

    if not isinstance(payload, dict):
        return [_error_event("Non-object SSE payload", thread_id, details=payload)]

    explicit_type = _ensure_str(payload.get("type"))
    if explicit_type == "error":
        return [_error_event(_ensure_str(payload.get("error")) or "model error", thread_id, details=payload.get("details"))]
    if explicit_type in {"assistant_delta", "tool_call", "tool_result", "done"}:
        if explicit_type == "assistant_delta":
            return [_assistant_delta_event(_delta_text(payload.get("text")), thread_id)]
        if explicit_type == "tool_call":
            arguments = payload.get("arguments", {})
            if not isinstance(arguments, dict):
                arguments = {"_raw": arguments}
            return [_tool_call_event(_ensure_str(payload.get("tool")) or "unknown", cast("dict[str, Any]", arguments), thread_id)]
        if explicit_type == "tool_result":
            return [_tool_result_event(_ensure_str(payload.get("tool")), payload.get("result", {}), thread_id)]
        return [{"type": "done", "thread_id": thread_id}]

    if "error" in payload:
        return [_error_event(_ensure_str(payload.get("error", "unknown")) or "model error", thread_id,)]

    events: list[NormalizedEvent] = []
    if "choices" in payload:
        for choice in cast("list[dict[str, Any]]", payload.get("choices", [])):
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            message = choice.get("message")
            tool_calls = []
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str) and content:
                    events.append(_assistant_delta_event(content, thread_id))
                tool_calls = delta.get("tool_calls")
            elif isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str) and content:
                    events.append(_assistant_delta_event(content, thread_id))
                tool_calls = message.get("tool_calls")
                if choice.get("role") and choice.get("role") != "assistant":
                    continue
                tool_result = message.get("tool_result")
                if isinstance(tool_result, dict):
                    events.append(
                        _tool_result_event(
                            _ensure_str(message.get("name")),
                            tool_result,
                            thread_id=thread_id,
                        )
                    )
            if isinstance(tool_calls, list):
                for tool_call in tool_calls:
                    events.extend(_normalize_tool_call_delta(tool_call, thread_id))
            finish_reason = choice.get("finish_reason")
            if finish_reason in ("stop", "tool_calls", "length", "stop_sequence"):
                events.append({"type": "done", "thread_id": thread_id, "finish_reason": finish_reason})
            if choice.get("error"):
                events.append(_error_event(_ensure_str(choice.get("error")) or "model error", thread_id))
    return events


def normalize_sse_response_lines(lines: Iterable[Any], thread_id: str) -> list[NormalizedEvent]:
    """Convert raw SSE lines into normalized assistant events."""

    normalized: list[NormalizedEvent] = []
    for raw_line in lines:
        if isinstance(raw_line, bytes):
            decoded = raw_line.decode("utf-8", errors="replace")
        else:
            decoded = str(raw_line)
        for chunk in decoded.splitlines():
            line = chunk.strip()
            if not line or line == "":  # keep explicit blank-line separators from SSE syntax
                continue
            if not line.startswith("data:"):
                continue
            payload_text = line[len("data:") :].strip()
            if not payload_text:
                continue
            if payload_text == "[DONE]":
                normalized.append({"type": "done", "thread_id": thread_id})
                continue
            try:
                payload = json.loads(payload_text)
            except json.JSONDecodeError:
                normalized.append(_error_event("Invalid SSE JSON", thread_id, details=payload_text))
                continue
            normalized.extend(normalize_llama_chunk(payload, thread_id))
    return normalized


class FakeAgentRuntimeClient:
    """Deterministic test/runtime stub for unit tests."""

    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self._events = events

    def stream_chat(
        self,
        thread_id: str,
        messages: Messages,
        context_packet: dict[str, Any],
        tools: Iterable[dict[str, Any]],
        model_profile: str | dict[str, Any] | None,
    ) -> Iterable[NormalizedEvent]:
        if self._events is None:
            compact_context = compact_context_packet(context_packet)
            safe_tools = build_compact_tool_schemas(tools)
            safe_tool_name = safe_tools[0]["function"]["name"] if safe_tools else "read_viewer_context"
            events = [
                {"type": "assistant_delta", "text": f"Processing thread {thread_id}"},
                {
                    "type": "tool_call",
                    "tool": safe_tool_name,
                    "arguments": {
                        "thread_id": thread_id,
                        "model_profile": model_profile,
                        "selected_part_count": len(compact_context.get("viewer", {}).get("selected_part_ids", [])),
                    },
                },
                {
                    "type": "tool_result",
                    "tool": safe_tool_name,
                    "result": {
                        "status": "ok",
                        "message_count": len(messages),
                    },
                },
                {"type": "done"},
            ]
        else:
            events = self._events

        for event in events:
            yield from normalize_llama_chunk(cast("dict[str, Any]", event), thread_id)


class LlamaStudioAdapterError(AgentRuntimeError):
    """Adapter-specific runtime error."""


class CodexRuntimeError(AgentRuntimeError):
    """Raised when the Codex CLI runtime bridge fails."""


class CodexExecAgentRuntimeClient:
    """Narrow Codex CLI bridge for the PS-0 provider proof spike."""

    def __init__(
        self,
        project_root: str,
        *,
        codex_command: str = "codex",
        model: str | None = None,
        sandbox: str = "read-only",
        request_timeout: float = 120.0,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self.project_root = project_root
        self.codex_command = codex_command
        self.model = model
        self.sandbox = sandbox
        self.request_timeout = request_timeout
        self._runner = runner or subprocess.run

    def _command(self, prompt: str) -> list[str]:
        executable = shutil.which(self.codex_command) or self.codex_command
        command = [
            executable,
            "exec",
            "--json",
            "--ephemeral",
            "--sandbox",
            self.sandbox,
            "--skip-git-repo-check",
            "-C",
            self.project_root,
        ]
        if self.model:
            command.extend(["--model", self.model])
        command.append(prompt)
        return command

    def _build_prompt(
        self,
        thread_id: str,
        messages: Messages,
        context_packet: dict[str, Any],
        tools: Iterable[dict[str, Any]],
        model_profile: str | dict[str, Any] | None,
    ) -> str:
        payload = {
            "thread_id": thread_id,
            "messages": _compact_message_payload(messages),
            "context_packet": compact_context_packet(context_packet),
            "safe_tools": build_compact_tool_schemas(tools),
            "model_profile": model_profile,
        }
        return (
            "You are the Codex runtime bridge for Flow CAD design-thread chat.\n"
            "Do not mutate CAD source, generated exports, reports, or project files.\n"
            "Do not call generic shell or filesystem mutation tools.\n"
            "If CAD changes are needed, propose Flow CAD draft operations only. "
            "All CAD mutations must go through draft transaction, preview, "
            "focused validation, and explicit user acceptance.\n"
            "Respond with concise text suitable for a Flow CAD chat message. "
            "If you suggest an action, name the next Flow CAD safe tool/action.\n\n"
            f"FLOW_CAD_CONTEXT={json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
        )

    def _final_agent_text(self, stdout: str) -> str:
        last_text = ""
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            if item.get("type") != "agent_message":
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                last_text = text.strip()
        return last_text

    def stream_chat(
        self,
        thread_id: str,
        messages: Messages,
        context_packet: dict[str, Any],
        tools: Iterable[dict[str, Any]],
        model_profile: str | dict[str, Any] | None,
    ) -> Iterable[NormalizedEvent]:
        prompt = self._build_prompt(thread_id, messages, context_packet, tools, model_profile)
        command = self._command(prompt)
        try:
            completed = self._runner(
                command,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                text=True,
                timeout=self.request_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CodexRuntimeError(f"Codex runtime request timed out after {self.request_timeout:g}s") from exc
        except OSError as exc:
            raise CodexRuntimeError(f"Unable to launch Codex runtime: {exc}") from exc

        if completed.returncode != 0:
            details = (completed.stderr or completed.stdout or "").strip()
            raise CodexRuntimeError(f"Codex runtime exited with status {completed.returncode}: {details}")

        text = self._final_agent_text(completed.stdout)
        if not text:
            raise CodexRuntimeError("Codex runtime completed without an assistant message")

        yield _assistant_delta_event(text, thread_id)
        yield {"type": "done", "thread_id": thread_id, "runtime": "codex_exec"}


class LlamaCppAgentRuntimeClient:
    """LlamaStudio / llama.cpp compatible streaming HTTP client."""

    def __init__(
        self,
        endpoint: str,
        model: str = "llama3",
        api_path: str = "/v1/chat/completions",
        request_timeout: float = 20.0,
        default_profile: str | dict[str, Any] | None = None,
        opener: Callable[[urllib.request.Request, float], Any] | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.api_path = api_path
        self.request_timeout = request_timeout
        self.default_profile = default_profile
        self._opener = opener or urllib.request.urlopen

    def _request_url(self) -> str:
        parsed = urllib.parse.urlsplit(self.endpoint)
        if parsed.path and parsed.path != "/":
            path = parsed.path.rstrip("/") + self.api_path
        else:
            path = self.api_path
        return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


    def _build_payload(
        self,
        thread_id: str,
        messages: Messages,
        context_packet: dict[str, Any],
        tools: Iterable[dict[str, Any]],
        model_profile: str | dict[str, Any] | None,
    ) -> dict[str, Any]:
        del thread_id
        return {
            "model": self.model,
            "stream": True,
            "messages": _compact_message_payload(messages),
            "context_packet": compact_context_packet(context_packet),
            "tools": build_compact_tool_schemas(tools),
            "profile": model_profile or self.default_profile or "default",
        }

    def stream_chat(
        self,
        thread_id: str,
        messages: Messages,
        context_packet: dict[str, Any],
        tools: Iterable[dict[str, Any]],
        model_profile: str | dict[str, Any] | None,
    ) -> Iterable[NormalizedEvent]:
        payload = self._build_payload(thread_id, messages, context_packet, tools, model_profile)
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._request_url(),
            data=data,
            headers={
                "content-type": "application/json",
                "accept": "text/event-stream",
            },
            method="POST",
        )
        try:
            with self._opener(request, timeout=self.request_timeout) as response:
                for raw_line in response:
                    for event in normalize_sse_response_lines([raw_line], thread_id):
                        yield event
        except Exception as err:
            if isinstance(err, urllib.error.HTTPError):
                raise LlamaStudioAdapterError(f"HTTP error calling model runtime: {err.code}") from err
            if isinstance(err, urllib.error.URLError):
                raise LlamaStudioAdapterError(f"Unable to connect to model runtime: {err.reason}") from err
            if isinstance(err, TimeoutError):
                raise LlamaStudioAdapterError(f"Runtime request timed out: {err}") from err
            raise LlamaStudioAdapterError(f"Runtime request failed: {err}") from err


class LlamaStudioAgentRuntimeClient(LlamaCppAgentRuntimeClient):
    """Compatibility alias for LlamaStudio-native naming."""
