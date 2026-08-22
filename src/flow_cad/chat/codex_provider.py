"""Bounded Codex app-server provider for Flow CAD chat.

The adapter speaks the newline-delimited JSON-RPC protocol emitted by the
installed ``codex app-server``.  It intentionally presents a much smaller
surface to the rest of Flow CAD: compact assistant, reasoning, tool, progress,
and terminal events.  Command output, patches, tool arguments, and other raw
transcripts never cross the provider boundary.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Protocol, TextIO, cast

from .providers import ProviderCancellation, ProviderEvent
from .tools import ChatToolRegistry, default_chat_tools


APP_SERVER_PROTOCOL = "v2"
_BINDINGS_SCHEMA_VERSION = 1
_MAX_CONTEXT_BYTES = 1_000_000
_MAX_MESSAGE_CHARS = 8_000_000
_RECEIVE_POLL_SECONDS = 0.05
_REQUEST_TIMEOUT_SECONDS = 15.0


class CodexProviderError(RuntimeError):
    """Base class for errors that may be shown as a bounded provider failure."""


class CodexTransportError(CodexProviderError):
    """The app-server transport could not provide another protocol message."""


class CodexProtocolError(CodexProviderError):
    """The app server returned malformed or unsupported protocol data."""


class CodexRpcError(CodexProviderError):
    """A JSON-RPC request failed without exposing the server's raw payload."""

    def __init__(self, method: str, code: int | None, message: str) -> None:
        super().__init__(f"Codex request failed: {method}")
        self.method = method
        self.code = code
        self.server_message = message


class JsonRpcTransport(Protocol):
    """Minimal transport contract used by the provider and fake tests."""

    def send(self, message: Mapping[str, object]) -> None:
        ...

    def receive(self, timeout: float | None = None) -> Mapping[str, object] | None:
        ...

    def close(self) -> None:
        ...


class SubprocessJsonRpcTransport:
    """Newline-delimited JSON transport over one ``codex app-server`` process."""

    def __init__(
        self,
        *,
        project_root: Path,
        executable: str = "codex",
    ) -> None:
        self._process = subprocess.Popen(
            [executable, "app-server", "--stdio"],
            cwd=project_root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="strict",
            bufsize=1,
        )
        if self._process.stdin is None or self._process.stdout is None:
            self._process.kill()
            raise CodexTransportError("Codex app-server stdio is unavailable")
        self._stdin: TextIO = self._process.stdin
        self._stdout: TextIO = self._process.stdout
        self._messages: queue.Queue[object] = queue.Queue()
        self._send_lock = threading.Lock()
        self._closed = False
        self._reader = threading.Thread(
            target=self._read_stdout,
            name="flow-cad-codex-reader",
            daemon=True,
        )
        self._reader.start()

    def send(self, message: Mapping[str, object]) -> None:
        if self._closed:
            raise CodexTransportError("Codex app-server transport is closed")
        encoded = json.dumps(dict(message), separators=(",", ":"), ensure_ascii=False)
        with self._send_lock:
            try:
                self._stdin.write(encoded + "\n")
                self._stdin.flush()
            except (BrokenPipeError, OSError, UnicodeError) as error:
                raise CodexTransportError("Codex app-server input closed") from error

    def receive(self, timeout: float | None = None) -> Mapping[str, object] | None:
        try:
            value = self._messages.get(timeout=timeout)
        except queue.Empty:
            return None
        if value is _END_OF_STREAM:
            raise CodexTransportError("Codex app-server output closed")
        if isinstance(value, BaseException):
            raise CodexTransportError("Codex app-server returned invalid protocol data") from value
        if not isinstance(value, Mapping):
            raise CodexProtocolError("Codex app-server message must be an object")
        return cast(Mapping[str, object], value)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            self._stdin.close()
        except OSError:
            pass
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=1.0)
        try:
            self._stdout.close()
        except OSError:
            pass

    def _read_stdout(self) -> None:
        try:
            for line in self._stdout:
                if len(line) > _MAX_MESSAGE_CHARS:
                    raise CodexProtocolError("Codex app-server message exceeds the size limit")
                stripped = line.strip()
                if not stripped:
                    continue
                parsed = json.loads(stripped)
                if not isinstance(parsed, dict):
                    raise CodexProtocolError("Codex app-server message must be an object")
                self._messages.put(parsed)
        except BaseException as error:
            self._messages.put(error)
        finally:
            self._messages.put(_END_OF_STREAM)


_END_OF_STREAM = object()


class CodexThreadBindings:
    """Atomically persist local-chat to durable Codex thread IDs."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()

    def get(self, local_thread_id: str) -> str | None:
        with self._lock:
            return self._load().get(local_thread_id)

    def set(self, local_thread_id: str, provider_thread_id: str) -> None:
        _validate_binding_id(local_thread_id, "local thread")
        _validate_binding_id(provider_thread_id, "provider thread")
        with self._lock:
            bindings = self._load()
            bindings[local_thread_id] = provider_thread_id
            self._write(bindings)

    def remove(self, local_thread_id: str) -> None:
        with self._lock:
            bindings = self._load()
            if bindings.pop(local_thread_id, None) is not None:
                self._write(bindings)

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise CodexProviderError("Codex thread bindings are unreadable") from error
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != _BINDINGS_SCHEMA_VERSION
        ):
            raise CodexProviderError("Codex thread bindings use an unsupported schema")
        raw_bindings = payload.get("bindings")
        if not isinstance(raw_bindings, dict):
            raise CodexProviderError("Codex thread bindings are malformed")
        bindings: dict[str, str] = {}
        for local_id, provider_id in raw_bindings.items():
            if not isinstance(local_id, str) or not isinstance(provider_id, str):
                raise CodexProviderError("Codex thread bindings are malformed")
            _validate_binding_id(local_id, "local thread")
            _validate_binding_id(provider_id, "provider thread")
            bindings[local_id] = provider_id
        return bindings

    def _write(self, bindings: Mapping[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.{uuid.uuid4().hex}.tmp")
        payload = {
            "schema_version": _BINDINGS_SCHEMA_VERSION,
            "bindings": dict(sorted(bindings.items())),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            _fsync_directory(self.path.parent)
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass


class CodexAppServerProvider:
    """Read-only, never-approve Codex provider implementing ``ChatProvider``."""

    name = "codex-app-server"

    def __init__(
        self,
        project_root: Path,
        *,
        transport_factory: Callable[[], JsonRpcTransport] | None = None,
        executable: str = "codex",
        bindings_path: Path | None = None,
        request_timeout: float = _REQUEST_TIMEOUT_SECONDS,
        tool_registry: ChatToolRegistry | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self._executable = executable
        self._custom_transport = transport_factory is not None
        self._transport_factory = transport_factory or (
            lambda: SubprocessJsonRpcTransport(
                project_root=self.project_root,
                executable=self._executable,
            )
        )
        self._bindings = CodexThreadBindings(
            bindings_path or self.project_root / ".flow" / "codex-thread-bindings.json"
        )
        self._request_timeout = request_timeout
        self._tool_registry = tool_registry or default_chat_tools(self.project_root)
        self._diagnostic_lock = threading.Lock()
        self._last_failure_reason: str | None = None
        self._last_rpc_method: str | None = None

    @property
    def available(self) -> bool:
        """Report whether the app server exists and has usable authentication."""

        diagnostics = self.diagnostics()
        return bool(
            diagnostics["executable_available"] and diagnostics["authenticated"]
        )

    def diagnostics(self) -> dict[str, object]:
        """Return bounded connection facts without exposing credentials or CLI output."""

        executable_available = self._custom_transport or shutil.which(self._executable) is not None
        authenticated = self._custom_transport
        auth_method: str | None = "test-transport" if self._custom_transport else None
        if executable_available and not self._custom_transport:
            try:
                completed = subprocess.run(
                    [self._executable, "login", "status"],
                    cwd=self.project_root,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=3.0,
                    check=False,
                )
                authenticated = completed.returncode == 0
                normalized = completed.stdout.casefold()
                if authenticated:
                    if "chatgpt" in normalized:
                        auth_method = "chatgpt"
                    elif "api key" in normalized or "api-key" in normalized:
                        auth_method = "api-key"
                    elif "access token" in normalized:
                        auth_method = "access-token"
                    else:
                        auth_method = "authenticated"
            except (OSError, subprocess.TimeoutExpired):
                authenticated = False
        with self._diagnostic_lock:
            last_failure_reason = self._last_failure_reason
            last_rpc_method = self._last_rpc_method
        return {
            "executable_available": executable_available,
            "authenticated": authenticated,
            "auth_method": auth_method,
            "last_failure_reason": last_failure_reason,
            "last_rpc_method": last_rpc_method,
        }

    def stream_turn(
        self,
        *,
        thread_id: str,
        turn_id: str,
        prompt: str,
        context: Mapping[str, object],
        cancellation: ProviderCancellation,
    ) -> Iterator[ProviderEvent]:
        """Start or resume a durable Codex thread and stream compact events."""

        if cancellation.cancelled:
            yield ProviderEvent("cancelled", "Turn cancelled before provider dispatch.")
            return
        try:
            normalized_context = _json_object(context)
            context_size = len(
                json.dumps(normalized_context, separators=(",", ":"), ensure_ascii=False).encode(
                    "utf-8"
                )
            )
            if context_size > _MAX_CONTEXT_BYTES:
                raise CodexProviderError("Flow CAD context exceeds the provider size limit")
        except (TypeError, ValueError, UnicodeError):
            yield ProviderEvent(
                "failed",
                "Flow CAD context could not be sent to Codex.",
                {"retryable": False, "reason": "invalid_context"},
            )
            return

        transport: JsonRpcTransport | None = None
        client: _CodexRpcClient | None = None
        provider_thread_id: str | None = None
        provider_turn_id: str | None = None
        terminal = False
        interrupt_sent = False
        try:
            yield ProviderEvent(
                "progress",
                "Connecting to Codex.",
                {"phase": "connecting", "protocol": APP_SERVER_PROTOCOL},
            )
            transport = self._transport_factory()
            client = _CodexRpcClient(
                transport,
                request_timeout=self._request_timeout,
                tool_handler=lambda name, arguments: self._tool_registry.execute(
                    name,
                    arguments,
                    normalized_context,
                ),
            )
            client.initialize()

            provider_thread_id, resumed = self._start_or_resume_thread(client, thread_id)
            yield ProviderEvent(
                "progress",
                "Resumed Codex conversation." if resumed else "Started Codex conversation.",
                {
                    "phase": "thread_ready",
                    "resumed": resumed,
                    "provider_thread_id": provider_thread_id,
                },
            )
            if cancellation.cancelled:
                yield ProviderEvent("cancelled", "Turn cancelled before model dispatch.")
                terminal = True
                return

            context_value = json.dumps(
                normalized_context,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )
            result = client.request(
                "turn/start",
                {
                    "threadId": provider_thread_id,
                    "input": [{"type": "text", "text": prompt, "text_elements": []}],
                    "additionalContext": {
                        "flow_cad": {"kind": "application", "value": context_value}
                    },
                    "clientUserMessageId": turn_id,
                    "cwd": str(self.project_root),
                    "approvalPolicy": "never",
                },
            )
            provider_turn_id = _nested_string(result, "turn", "id")
            yield ProviderEvent(
                "progress",
                "Codex is working.",
                {
                    "phase": "running",
                    "provider_thread_id": provider_thread_id,
                    "provider_turn_id": provider_turn_id,
                },
            )

            mapper = _CodexEventMapper(provider_thread_id, provider_turn_id)
            while not terminal:
                if cancellation.cancelled and not interrupt_sent:
                    interrupt_sent = True
                    client.request(
                        "turn/interrupt",
                        {"threadId": provider_thread_id, "turnId": provider_turn_id},
                    )
                    yield ProviderEvent(
                        "progress",
                        "Cancellation requested.",
                        {"phase": "cancelling"},
                    )

                while client.provider_events:
                    yield client.provider_events.popleft()

                message = client.next_message(timeout=_RECEIVE_POLL_SECONDS)
                if message is None:
                    continue
                if client.is_server_request(message):
                    client.handle_server_request(message)
                    continue
                for event, is_terminal in mapper.map(message):
                    yield event
                    terminal = terminal or is_terminal
            if terminal:
                with self._diagnostic_lock:
                    self._last_failure_reason = None
                    self._last_rpc_method = None
        except CodexProviderError as error:
            failure_reason = _failure_reason(error)
            with self._diagnostic_lock:
                self._last_failure_reason = failure_reason
                self._last_rpc_method = error.method if isinstance(error, CodexRpcError) else None
            yield ProviderEvent(
                "failed",
                "Codex provider is unavailable.",
                {
                    "retryable": True,
                    "reason": failure_reason,
                    **(
                        {"rpc_method": error.method}
                        if isinstance(error, CodexRpcError)
                        else {}
                    ),
                },
            )
        finally:
            if (
                client is not None
                and provider_thread_id is not None
                and provider_turn_id is not None
                and not terminal
            ):
                client.interrupt_best_effort(provider_thread_id, provider_turn_id)
            if transport is not None:
                transport.close()

    def _start_or_resume_thread(
        self, client: "_CodexRpcClient", local_thread_id: str
    ) -> tuple[str, bool]:
        provider_thread_id = self._bindings.get(local_thread_id)
        if provider_thread_id is not None:
            try:
                result = client.request(
                    "thread/resume",
                    {
                        "threadId": provider_thread_id,
                        "cwd": str(self.project_root),
                        "approvalPolicy": "never",
                        "approvalsReviewer": "user",
                        "sandbox": "read-only",
                        "excludeTurns": True,
                    },
                )
                resumed_id = _nested_string(result, "thread", "id")
                if resumed_id != provider_thread_id:
                    raise CodexProtocolError("Codex resumed an unexpected thread")
                return resumed_id, True
            except CodexRpcError as error:
                if not _is_missing_thread(error):
                    raise
                self._bindings.remove(local_thread_id)

        result = client.request(
            "thread/start",
            {
                "cwd": str(self.project_root),
                "ephemeral": False,
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": "read-only",
                "experimentalRawEvents": False,
                "dynamicTools": self._tool_registry.provider_specs,
                "developerInstructions": (
                    "You are assisting inside Flow CAD. Treat the flow_cad additionalContext as "
                    "authoritative CAD review context. Do not mutate files or request elevated "
                    "permissions. Give concise user-facing progress and results."
                ),
            },
        )
        provider_thread_id = _nested_string(result, "thread", "id")
        self._bindings.set(local_thread_id, provider_thread_id)
        return provider_thread_id, False


class _CodexRpcClient:
    def __init__(
        self,
        transport: JsonRpcTransport,
        *,
        request_timeout: float,
        tool_handler: Callable[[str, object], Mapping[str, object]] | None = None,
    ) -> None:
        self.transport = transport
        self.request_timeout = request_timeout
        self._next_request_id = 1
        self._pending_messages: deque[Mapping[str, object]] = deque()
        self.provider_events: deque[ProviderEvent] = deque()
        self._tool_handler = tool_handler

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "flow-cad",
                    "title": "Flow CAD",
                    "version": "1",
                },
                "capabilities": {"experimentalApi": True},
            },
        )
        self.transport.send({"method": "initialized"})

    def request(self, method: str, params: Mapping[str, object]) -> Mapping[str, object]:
        request_id = self._next_request_id
        self._next_request_id += 1
        self.transport.send({"id": request_id, "method": method, "params": dict(params)})
        deadline = time.monotonic() + self.request_timeout
        deferred: list[Mapping[str, object]] = []
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise CodexTransportError(f"Codex app-server did not answer {method}")
                # Do not feed a deferred notification straight back into this
                # same response wait; it must remain available to the event
                # loop after the matching response arrives.
                message = self.transport.receive(min(_RECEIVE_POLL_SECONDS, remaining))
                if message is None:
                    continue
                if self.is_server_request(message):
                    self.handle_server_request(message)
                    continue
                if message.get("id") != request_id:
                    deferred.append(message)
                    continue
                error = message.get("error")
                if isinstance(error, Mapping):
                    code = error.get("code")
                    error_code = code if isinstance(code, int) else None
                    server_message = error.get("message")
                    raise CodexRpcError(
                        method,
                        error_code,
                        server_message if isinstance(server_message, str) else "",
                    )
                result = message.get("result")
                if not isinstance(result, Mapping):
                    raise CodexProtocolError(f"Codex response for {method} has no object result")
                return cast(Mapping[str, object], result)
        finally:
            self._pending_messages.extend(deferred)

    def next_message(self, *, timeout: float) -> Mapping[str, object] | None:
        if self._pending_messages:
            return self._pending_messages.popleft()
        return self.transport.receive(timeout)

    @staticmethod
    def is_server_request(message: Mapping[str, object]) -> bool:
        return (
            "id" in message
            and isinstance(message.get("method"), str)
            and "result" not in message
            and "error" not in message
        )

    def handle_server_request(self, message: Mapping[str, object]) -> None:
        request_id = message.get("id")
        method = message.get("method")
        if not isinstance(method, str):
            raise CodexProtocolError("Codex server request has no method")

        new_approvals = {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
        }
        legacy_approvals = {"execCommandApproval", "applyPatchApproval"}
        if method in new_approvals:
            self._respond(request_id, {"decision": "decline"})
            self.provider_events.append(
                ProviderEvent(
                    "progress",
                    "Codex requested an operation that Flow CAD did not approve.",
                    {"phase": "approval_declined", "request_kind": method},
                )
            )
            return
        if method in legacy_approvals:
            self._respond(
                request_id,
                {
                    "decision": {
                        "denied": {
                            "rejection": "Flow CAD chat does not expose interactive approvals."
                        }
                    }
                },
            )
            self.provider_events.append(
                ProviderEvent(
                    "progress",
                    "Codex requested an operation that Flow CAD did not approve.",
                    {"phase": "approval_declined", "request_kind": method},
                )
            )
            return
        if method == "item/permissions/requestApproval":
            # This callback has no explicit decline variant. An empty granted
            # profile is the schema-valid equivalent of granting no additional
            # filesystem or network authority.
            self._respond(
                request_id,
                {"permissions": {}, "scope": "turn", "strictAutoReview": False},
            )
            self.provider_events.append(
                ProviderEvent(
                    "progress",
                    "Codex requested permissions that Flow CAD did not grant.",
                    {"phase": "approval_declined", "request_kind": method},
                )
            )
            return
        if method == "item/tool/call":
            params = message.get("params")
            tool_name = params.get("tool") if isinstance(params, Mapping) else None
            arguments = params.get("arguments") if isinstance(params, Mapping) else None
            if self._tool_handler is None or not isinstance(tool_name, str):
                result = {"error": "The requested Flow CAD operation is not registered."}
                success = False
                phase = "tool_rejected"
            else:
                try:
                    result = dict(self._tool_handler(tool_name, arguments))
                    success = True
                    phase = "tool_completed"
                except (KeyError, ValueError, RuntimeError):
                    result = {"error": "The Flow CAD operation could not be completed."}
                    success = False
                    phase = "tool_failed"
            self._respond(
                request_id,
                {
                    "success": success,
                    "contentItems": [
                        {
                            "type": "inputText",
                            "text": json.dumps(
                                result,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        }
                    ],
                },
            )
            self.provider_events.append(
                ProviderEvent(
                    "tool",
                    (
                        "Flow CAD operation completed."
                        if success
                        else "Flow CAD operation failed."
                    ),
                    {
                        "phase": phase,
                        "tool": tool_name if isinstance(tool_name, str) else None,
                    },
                )
            )
            return

        self._respond_error(request_id, -32601, "Request is unavailable in Flow CAD chat")
        if "Approval" in method or "approval" in method or "elicitation" in method:
            self.provider_events.append(
                ProviderEvent(
                    "progress",
                    "Codex requested input or approval that is unavailable here.",
                    {"phase": "approval_unavailable", "request_kind": method},
                )
            )

    def interrupt_best_effort(self, thread_id: str, turn_id: str) -> None:
        try:
            request_id = self._next_request_id
            self._next_request_id += 1
            self.transport.send(
                {
                    "id": request_id,
                    "method": "turn/interrupt",
                    "params": {"threadId": thread_id, "turnId": turn_id},
                }
            )
        except CodexProviderError:
            pass

    def _respond(self, request_id: object, result: Mapping[str, object]) -> None:
        if not isinstance(request_id, (str, int)):
            raise CodexProtocolError("Codex server request has an invalid id")
        self.transport.send({"id": request_id, "result": dict(result)})

    def _respond_error(self, request_id: object, code: int, message: str) -> None:
        if not isinstance(request_id, (str, int)):
            raise CodexProtocolError("Codex server request has an invalid id")
        self.transport.send({"id": request_id, "error": {"code": code, "message": message}})


class _CodexEventMapper:
    def __init__(self, thread_id: str, turn_id: str) -> None:
        self.thread_id = thread_id
        self.turn_id = turn_id
        self._agent_delta_items: set[str] = set()
        self._reasoning_delta_items: set[str] = set()

    def map(self, message: Mapping[str, object]) -> tuple[tuple[ProviderEvent, bool], ...]:
        method = message.get("method")
        params = message.get("params")
        if not isinstance(method, str) or not isinstance(params, Mapping):
            return ()
        if not self._belongs_to_turn(params):
            return ()

        if method == "item/agentMessage/delta":
            delta = params.get("delta")
            item_id = params.get("itemId")
            if isinstance(delta, str) and delta:
                if isinstance(item_id, str):
                    self._agent_delta_items.add(item_id)
                return ((ProviderEvent("content", delta), False),)
            return ()

        if method == "item/reasoning/summaryTextDelta":
            delta = params.get("delta")
            item_id = params.get("itemId")
            if isinstance(delta, str) and delta:
                if isinstance(item_id, str):
                    self._reasoning_delta_items.add(item_id)
                return ((ProviderEvent("reasoning", delta), False),)
            return ()

        if method == "item/plan/delta":
            delta = params.get("delta")
            if isinstance(delta, str) and delta:
                return (
                    (
                        ProviderEvent("progress", _safe_text(delta), {"phase": "planning"}),
                        False,
                    ),
                )
            return ()

        if method == "item/started":
            item = params.get("item")
            event = _tool_event(item, phase="started")
            return ((event, False),) if event is not None else ()

        if method == "item/completed":
            item = params.get("item")
            if not isinstance(item, Mapping):
                return ()
            item_type = item.get("type")
            item_id = item.get("id")
            if item_type == "agentMessage" and item_id not in self._agent_delta_items:
                text = item.get("text")
                if isinstance(text, str) and text:
                    return ((ProviderEvent("content", text), False),)
            if item_type == "reasoning" and item_id not in self._reasoning_delta_items:
                summary = item.get("summary")
                if isinstance(summary, list):
                    text = "\n".join(part for part in summary if isinstance(part, str)).strip()
                    if text:
                        return ((ProviderEvent("reasoning", text), False),)
            event = _tool_event(item, phase="completed")
            return ((event, False),) if event is not None else ()

        if method == "item/reasoning/summaryPartAdded":
            return (
                (ProviderEvent("progress", "Codex is reasoning.", {"phase": "reasoning"}), False),
            )

        if method == "item/mcpToolCall/progress":
            return (
                (
                    ProviderEvent("tool", "A Codex tool is still running.", {"phase": "running"}),
                    False,
                ),
            )

        if method == "turn/started":
            return (
                (ProviderEvent("progress", "Codex turn started.", {"phase": "running"}), False),
            )

        if method == "error":
            retrying = params.get("willRetry") is True
            return (
                (
                    ProviderEvent(
                        "progress",
                        (
                            "Codex encountered an error and is retrying."
                            if retrying
                            else "Codex encountered an error."
                        ),
                        {"phase": "retrying" if retrying else "error"},
                    ),
                    False,
                ),
            )

        if method == "warning":
            return (
                (ProviderEvent("progress", "Codex reported a warning.", {"phase": "warning"}), False),
            )

        if method == "turn/completed":
            turn = params.get("turn")
            if not isinstance(turn, Mapping):
                raise CodexProtocolError("Codex turn completion is malformed")
            status = turn.get("status")
            details = {
                "provider_thread_id": self.thread_id,
                "provider_turn_id": self.turn_id,
                "status": status if isinstance(status, str) else "unknown",
            }
            if status == "completed":
                return ((ProviderEvent("completed", "", details), True),)
            if status == "interrupted":
                return ((ProviderEvent("cancelled", "Codex turn cancelled.", details), True),)
            return (
                (
                    ProviderEvent(
                        "failed", "Codex turn failed.", {**details, "retryable": True}
                    ),
                    True,
                ),
            )

        # Raw command/file output, patches, diffs, and raw reasoning are
        # intentionally ignored even though the protocol can emit them.
        return ()

    def _belongs_to_turn(self, params: Mapping[str, object]) -> bool:
        notification_thread = params.get("threadId")
        if isinstance(notification_thread, str) and notification_thread != self.thread_id:
            return False
        notification_turn = params.get("turnId")
        if isinstance(notification_turn, str) and notification_turn != self.turn_id:
            return False
        turn = params.get("turn")
        if isinstance(turn, Mapping):
            nested_turn_id = turn.get("id")
            if isinstance(nested_turn_id, str) and nested_turn_id != self.turn_id:
                return False
        return True


def _tool_event(item: object, *, phase: str) -> ProviderEvent | None:
    if not isinstance(item, Mapping):
        return None
    item_type = item.get("type")
    labels = {
        "commandExecution": "Command",
        "fileChange": "File change",
        "mcpToolCall": "Tool call",
        "dynamicToolCall": "Tool call",
        "collabAgentToolCall": "Agent task",
        "webSearch": "Web search",
        "imageView": "Image review",
        "imageGeneration": "Image generation",
    }
    if not isinstance(item_type, str) or item_type not in labels:
        return None
    details: dict[str, object] = {"tool_type": item_type, "phase": phase}
    item_id = item.get("id")
    if isinstance(item_id, str):
        details["item_id"] = item_id
    status = item.get("status")
    if isinstance(status, str):
        details["status"] = status
    return ProviderEvent("tool", f"{labels[item_type]} {phase}.", details)


def _json_object(value: Mapping[str, object]) -> dict[str, object]:
    encoded = json.dumps(dict(value), ensure_ascii=False, allow_nan=False)
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise ValueError("context must be an object")
    return cast(dict[str, object], decoded)


def _nested_string(value: Mapping[str, object], parent: str, key: str) -> str:
    nested = value.get(parent)
    if not isinstance(nested, Mapping):
        raise CodexProtocolError(f"Codex response has no {parent}")
    result = nested.get(key)
    if not isinstance(result, str) or not result:
        raise CodexProtocolError(f"Codex response has no {parent}.{key}")
    return result


def _validate_binding_id(value: str, label: str) -> None:
    if not value or len(value) > 300 or any(character in value for character in "\r\n\0"):
        raise CodexProviderError(f"Invalid {label} id")


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _is_missing_thread(error: CodexRpcError) -> bool:
    message = error.server_message.casefold()
    return error.code == -32600 and (
        "no rollout found" in message or ("thread" in message and "not found" in message)
    )


def _safe_text(value: str, *, limit: int = 500) -> str:
    return " ".join(value.split())[:limit]


def _failure_reason(error: CodexProviderError) -> str:
    if isinstance(error, CodexRpcError):
        return "rpc_error"
    if isinstance(error, CodexTransportError):
        return "transport_error"
    if isinstance(error, CodexProtocolError):
        return "protocol_error"
    return "provider_error"
