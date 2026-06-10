from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from flow_cad.config import AgentProfile, FlowCadConfig, load_flow_config
from flow_cad.draft_geometry import DraftGeometryError
from flow_cad.viewer.agent_runtime import (
    AgentRuntimeClient,
    AgentRuntimeError,
    CodexExecAgentRuntimeClient,
    FakeAgentRuntimeClient,
    LlamaCppAgentRuntimeClient,
)
from flow_cad.viewer.threads import (
    DesignThreadService,
    VisualEvidenceNotFoundError,
    VisualEvidenceRequestNotFoundError,
    ThreadNotFoundError,
    ThreadStorageError,
)
from flow_cad.viewer.service import ArtifactNotFoundError, ViewerError, ViewerService


def _project_root_from_env() -> Path | None:
    value = os.environ.get("FLOW_CAD_PROJECT_ROOT")
    return Path(value).resolve() if value else None


def _agent_runtime_from_config(project_root: Path, config: FlowCadConfig) -> AgentRuntimeClient:
    profile = config.active_agent_profile()
    provider = profile.normalized_provider
    if provider == "codex":
        return CodexExecAgentRuntimeClient(
            project_root=str(project_root.resolve()),
            codex_command=profile.command or "codex",
            model=profile.model,
            sandbox=profile.sandbox or "read-only",
            request_timeout=profile.timeout_seconds or 120.0,
        )

    if profile.endpoint:
        return LlamaCppAgentRuntimeClient(
            endpoint=profile.endpoint,
            model=profile.model or "llama3",
            default_profile=profile.id,
        )
    return FakeAgentRuntimeClient()


def _agent_runtime_from_env(project_root: Path | None = None) -> AgentRuntimeClient:
    resolved_root = (project_root or Path.cwd()).resolve()
    return _agent_runtime_from_config(resolved_root, load_flow_config(resolved_root))


def _cad_safe_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "read_viewer_context",
            "description": "Read the active Flow CAD design-thread and viewport context.",
            "parameters": {"properties": {"thread_id": {"type": "string"}}},
        },
        {
            "name": "request_visual_evidence",
            "description": "Ask the Flow CAD viewer to capture an offscreen visual evidence render for a thread.",
            "parameters": {
                "properties": {
                    "thread_id": {"type": "string"},
                    "view": {"type": "string", "enum": ["front", "back", "left", "right", "top", "bottom", "iso"]},
                    "purpose": {"type": "string"},
                    "part_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["thread_id"],
            },
        },
        {
            "name": "create_draft_transaction",
            "description": "Create a draft transaction for a registered CAD part.",
            "parameters": {"properties": {"part_id": {"type": "string"}}, "required": ["part_id"]},
        },
        {
            "name": "apply_draft_operations",
            "description": "Apply explicit Flow CAD draft operations to a draft transaction.",
            "parameters": {
                "properties": {
                    "transaction_token": {"type": "string"},
                    "operations": {"type": "array"},
                },
                "required": ["transaction_token", "operations"],
            },
        },
        {
            "name": "generate_preview_model",
            "description": "Generate a reviewable draft preview model.",
            "parameters": {"properties": {"transaction_token": {"type": "string"}}, "required": ["transaction_token"]},
        },
        {
            "name": "run_focused_validator",
            "description": "Run a focused Flow CAD validator against explicit draft or project context.",
            "parameters": {"properties": {"validator_id": {"type": "string"}, "transaction_token": {"type": "string"}}},
        },
        {
            "name": "read_profile_summary",
            "description": "Read an existing Flow CAD profile summary.",
            "parameters": {"properties": {"profile_id": {"type": "string"}}, "required": ["profile_id"]},
        },
        {
            "name": "summarize_acceptance_artifacts",
            "description": "Summarize review artifacts created by accepted draft transactions.",
            "parameters": {"properties": {"transaction_token": {"type": "string"}}, "required": ["transaction_token"]},
        },
    ]


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n\n"


def _assistant_delta_text(event: dict[str, Any]) -> str:
    value = event.get("text", event.get("delta", ""))
    return value if isinstance(value, str) else str(value)


def _tool_call_content(event: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(event.get("tool") or event.get("name") or "unknown")
    arguments = event.get("arguments") if isinstance(event.get("arguments"), dict) else {}
    return {
        "kind": "tool_call",
        "tool": tool_name,
        "summary": f"Calling {tool_name}",
        "inputs": arguments,
    }


def _tool_result_content(event: dict[str, Any]) -> dict[str, Any]:
    tool_name = str(event.get("tool") or event.get("name") or "unknown")
    result = event.get("result") if isinstance(event.get("result"), dict) else {"value": event.get("result")}
    status = str(result.get("status") or event.get("status") or "success") if isinstance(result, dict) else "success"
    content = {
        "kind": "tool_result",
        "tool": tool_name,
        "status": status,
        "summary": str(result.get("summary") or result.get("message") or f"{tool_name} completed"),
        "details": result,
    }
    for key in ("report_id", "profile_id"):
        if isinstance(result.get(key), str) and result[key].strip():
            content[key] = result[key].strip()
    return content


def _agent_turn_runtime_inputs(
    design_threads: DesignThreadService,
    thread_id: str,
    payload: dict[str, object],
    prepared: dict[str, Any],
    agent_runtime: AgentRuntimeClient,
    profile: AgentProfile,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]], str | dict[str, Any] | None, dict[str, Any]]:
    context_packet = design_threads.assistant_context_packet(
        thread_id,
        context_snapshot=prepared.get("context_snapshot") if isinstance(prepared.get("context_snapshot"), dict) else None,
    )
    thread = prepared.get("thread") if isinstance(prepared.get("thread"), dict) else design_threads.get_thread(thread_id)
    messages = thread.get("messages", []) if isinstance(thread.get("messages"), list) else []
    model_profile = payload.get("model_profile") if isinstance(payload.get("model_profile"), (str, dict)) else None
    if model_profile is None:
        model_profile = {
            "profile_id": profile.id,
            "provider": profile.provider,
            "model": profile.model,
            "reasoning": profile.reasoning,
        }
    metadata_base = {
        "runtime": agent_runtime.__class__.__name__,
        "agent_profile_id": profile.id,
        "agent_provider": profile.provider,
        **({"agent_model": profile.model} if profile.model else {}),
        **({"agent_reasoning": profile.reasoning} if profile.reasoning else {}),
        **(
            {"context_snapshot_id": prepared["context_snapshot"]["snapshot_id"]}
            if isinstance(prepared.get("context_snapshot"), dict)
            else {}
        ),
    }
    return messages, context_packet, _cad_safe_tools(), model_profile, metadata_base


def _persist_agent_runtime_event(
    design_threads: DesignThreadService,
    thread_id: str,
    event: dict[str, Any],
    metadata_base: dict[str, Any],
) -> dict[str, Any] | None:
    event_type = str(event.get("type") or "")
    if event_type == "tool_call":
        return design_threads.append_message(
            thread_id,
            {
                "type": "tool_call",
                "role": "assistant",
                "content": _tool_call_content(event),
                "metadata": {
                    **metadata_base,
                    "tool": event.get("tool"),
                    **({"tool_call_id": event["tool_call_id"]} if isinstance(event.get("tool_call_id"), str) else {}),
                },
            },
        )
    if event_type == "tool_result":
        return design_threads.append_validator_event(
            thread_id,
            {
                "type": "tool_result",
                "content": _tool_result_content(event),
                "metadata": {
                    **metadata_base,
                    "tool": event.get("tool"),
                },
            },
        )
    if event_type == "error":
        return design_threads.append_message(
            thread_id,
            {
                "type": "status",
                "role": "system",
                "content": {
                    "summary": str(event.get("error") or "Assistant stream error"),
                    "details": event,
                },
                "metadata": metadata_base,
            },
        )
    return None


def _selected_part_id_from_prepared(prepared: dict[str, Any]) -> str | None:
    snapshot = prepared.get("context_snapshot") if isinstance(prepared.get("context_snapshot"), dict) else {}
    candidates = snapshot.get("selected_part_ids")
    if not isinstance(candidates, list):
        viewer_state = snapshot.get("viewer_state") if isinstance(snapshot.get("viewer_state"), dict) else {}
        candidates = viewer_state.get("selected_part_ids")
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return None


def _draft_transaction_token_from_prepared(prepared: dict[str, Any]) -> str | None:
    snapshot = prepared.get("context_snapshot") if isinstance(prepared.get("context_snapshot"), dict) else {}
    draft_transaction = snapshot.get("draft_transaction") if isinstance(snapshot.get("draft_transaction"), dict) else {}
    for candidate in (
        draft_transaction.get("transaction_token"),
        draft_transaction.get("token"),
        snapshot.get("draft_transaction_token"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()

    viewer_state = snapshot.get("viewer_state") if isinstance(snapshot.get("viewer_state"), dict) else {}
    draft_transaction = viewer_state.get("draft_transaction") if isinstance(viewer_state.get("draft_transaction"), dict) else {}
    for candidate in (
        viewer_state.get("draft_transaction_token"),
        draft_transaction.get("transaction_token"),
        draft_transaction.get("token"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _annotations_from_prepared(prepared: dict[str, Any]) -> list[dict[str, Any]]:
    snapshot = prepared.get("context_snapshot") if isinstance(prepared.get("context_snapshot"), dict) else {}
    viewer_state = snapshot.get("viewer_state") if isinstance(snapshot.get("viewer_state"), dict) else {}
    annotations = viewer_state.get("annotations")
    if not isinstance(annotations, list):
        nested_viewer_state = viewer_state.get("viewer_state")
        if isinstance(nested_viewer_state, dict):
            annotations = nested_viewer_state.get("annotations")
    if not isinstance(annotations, list):
        annotations = snapshot.get("annotations")
    return [annotation for annotation in annotations if isinstance(annotation, dict)] if isinstance(annotations, list) else []


def _dimension_summary(preview_model: dict[str, Any]) -> str:
    dimensions = preview_model.get("dimensions") if isinstance(preview_model.get("dimensions"), dict) else {}
    length = dimensions.get("length_mm")
    width = dimensions.get("width_mm")
    height = dimensions.get("height_mm")
    if all(isinstance(value, (int, float)) for value in (length, width, height)):
        return f"{length:g} x {width:g} x {height:g} mm"
    draft = preview_model.get("draft") if isinstance(preview_model.get("draft"), dict) else {}
    raw_dimensions = draft.get("dimensions") if isinstance(draft.get("dimensions"), dict) else {}
    length = raw_dimensions.get("length")
    width = raw_dimensions.get("width")
    height = raw_dimensions.get("height")
    if all(isinstance(value, (int, float)) for value in (length, width, height)):
        return f"{length:g} x {width:g} x {height:g} mm"
    return "draft dimensions"


def _deterministic_draft_chat_turn(
    design_threads: DesignThreadService,
    viewer_service: ViewerService,
    thread_id: str,
    prepared: dict[str, Any],
) -> dict[str, Any] | None:
    command = str(prepared.get("message_text") or "")
    selected_part_id = _selected_part_id_from_prepared(prepared)
    draft_transaction_token = _draft_transaction_token_from_prepared(prepared)
    annotations = _annotations_from_prepared(prepared)
    metadata_base = {
        "runtime": "flow_cad_deterministic_draft",
        **(
            {"context_snapshot_id": prepared["context_snapshot"]["snapshot_id"]}
            if isinstance(prepared.get("context_snapshot"), dict)
            else {}
        ),
    }
    if draft_transaction_token and annotations:
        try:
            annotated_result = viewer_service.draft_transaction_from_annotated_walls(
                {
                    "command": command,
                    "transaction_token": draft_transaction_token,
                    "annotations": annotations,
                }
            )
        except (DraftGeometryError, ViewerError, KeyError, ValueError) as exc:
            annotated_result = {"ok": False, "error": str(exc)}
        if annotated_result.get("ok"):
            transaction_token = str(annotated_result["transaction_token"])
            part_id = str(annotated_result["part_id"])
            preview_model = (
                annotated_result.get("preview_model")
                if isinstance(annotated_result.get("preview_model"), dict)
                else {}
            )
            applied_operations = (
                annotated_result.get("applied_operations")
                if isinstance(annotated_result.get("applied_operations"), list)
                else []
            )
            source_loop_commands = (
                annotated_result.get("source_loop_commands")
                if isinstance(annotated_result.get("source_loop_commands"), list)
                else []
            )
            messages: list[dict[str, Any]] = []
            messages.append(
                design_threads.append_draft_event(
                    thread_id,
                    {
                        "content": {
                            "action": "apply",
                            "summary": "Applied annotated raised-wall draft operations",
                            "draft_transaction_token": transaction_token,
                            "part_id": part_id,
                            "operations": applied_operations,
                            "warnings": annotated_result.get("warnings", []),
                            "assumptions": annotated_result.get("assumptions", []),
                        },
                        "metadata": metadata_base,
                    },
                )
            )
            messages.append(
                design_threads.append_draft_event(
                    thread_id,
                    {
                        "content": {
                            "action": "preview",
                            "summary": "Draft preview generated from annotated chat",
                            "draft_transaction_token": transaction_token,
                            "part_id": part_id,
                            "preview_model": preview_model,
                            "source_loop_commands": source_loop_commands,
                        },
                        "metadata": metadata_base,
                    },
                )
            )
            wall_count = len(
                [operation for operation in applied_operations if operation.get("name") == "add_raised_wall"]
            )
            messages.append(
                design_threads.append_message(
                    thread_id,
                    {
                        "type": "assistant_message",
                        "role": "assistant",
                        "content": (
                            f"Updated draft `{part_id}` with {wall_count} raised wall features from the saved "
                            "annotations. The preview is ready in this thread; inspect it, then accept or discard "
                            "the draft."
                        ),
                        "metadata": {
                            **metadata_base,
                            "status": "draft_preview_ready",
                            "draft_transaction_token": transaction_token,
                            "part_id": part_id,
                            "source_loop_commands": source_loop_commands,
                        },
                    },
                )
            )
            return {
                "messages": messages,
                "events": [],
                "draft_result": annotated_result,
                "draft_preview_model": preview_model,
            }

    try:
        proposal = viewer_service.preview_command_proposal(
            {
                "command": command,
                **({"part_id": selected_part_id} if selected_part_id else {}),
                **({"transaction_token": draft_transaction_token} if draft_transaction_token else {}),
            }
        )
    except ViewerError:
        proposal = viewer_service.preview_command_proposal({"command": command})
    if not proposal.get("ok"):
        return None

    try:
        result = viewer_service.draft_transaction_from_panel_command(
            {
                "command": command,
                **({"selected_part_id": selected_part_id} if selected_part_id else {}),
                **({"transaction_token": draft_transaction_token} if draft_transaction_token else {}),
            }
        )
    except (DraftGeometryError, ViewerError, KeyError, ValueError) as exc:
        message = design_threads.append_message(
            thread_id,
            {
                "type": "assistant_message",
                "role": "assistant",
                "content": (
                    "I understood this as a supported draft request, but draft preview "
                    f"creation failed: {exc}"
                ),
                "metadata": {
                    **metadata_base,
                    "status": "failed",
                    "failed_step": "draft_preview",
                    "proposal": proposal,
                },
            },
        )
        return {
            "messages": [message],
            "events": [],
            "draft_result": {"ok": False, "error": str(exc), "proposal": proposal},
        }

    if not result.get("ok"):
        return None

    transaction_token = str(result["transaction_token"])
    part_id = str(result["part_id"])
    preview_model = result.get("preview_model") if isinstance(result.get("preview_model"), dict) else {}
    applied_operations = result.get("applied_operations") if isinstance(result.get("applied_operations"), list) else []
    source_loop_commands = result.get("source_loop_commands") if isinstance(result.get("source_loop_commands"), list) else []
    messages: list[dict[str, Any]] = []
    messages.append(
        design_threads.append_draft_event(
            thread_id,
            {
                "content": {
                    "action": "propose",
                    "summary": f"Proposed {len(applied_operations)} deterministic draft operations",
                    "draft_transaction_token": transaction_token,
                    "part_id": part_id,
                    "proposal": result.get("proposal"),
                    "warnings": result.get("warnings", []),
                    "assumptions": result.get("assumptions", []),
                },
                "metadata": metadata_base,
            },
        )
    )
    messages.append(
        design_threads.append_draft_event(
            thread_id,
            {
                "content": {
                    "action": "apply",
                    "summary": "Applied deterministic draft operations",
                    "draft_transaction_token": transaction_token,
                    "part_id": part_id,
                    "operations": applied_operations,
                },
                "metadata": metadata_base,
            },
        )
    )
    messages.append(
        design_threads.append_draft_event(
            thread_id,
            {
                "content": {
                    "action": "preview",
                    "summary": "Draft preview generated from chat",
                    "draft_transaction_token": transaction_token,
                    "part_id": part_id,
                    "preview_model": preview_model,
                    "source_loop_commands": source_loop_commands,
                },
                "metadata": metadata_base,
            },
        )
    )
    assistant_message = design_threads.append_message(
        thread_id,
        {
            "type": "assistant_message",
            "role": "assistant",
            "content": (
                f"Created draft `{part_id}` as {_dimension_summary(preview_model)}. "
                "The preview is ready in this thread; inspect it, then accept or discard the draft."
            ),
            "metadata": {
                **metadata_base,
                "status": "draft_preview_ready",
                "draft_transaction_token": transaction_token,
                "part_id": part_id,
                "source_loop_commands": source_loop_commands,
            },
        },
    )
    messages.append(assistant_message)
    return {
        "messages": messages,
        "events": [],
        "draft_result": result,
        "draft_preview_model": preview_model,
    }


def _agent_runtime_health(agent_runtime: AgentRuntimeClient, profile: AgentProfile) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "class": agent_runtime.__class__.__name__,
        "profile_id": profile.id,
        "profile_label": profile.display_name,
        "provider": profile.provider,
        "model": profile.model,
        "reasoning": profile.reasoning,
    }
    if isinstance(agent_runtime, CodexExecAgentRuntimeClient):
        payload.update(
            {
                "command": agent_runtime.codex_command,
                "sandbox": agent_runtime.sandbox,
            }
        )
    elif isinstance(agent_runtime, LlamaCppAgentRuntimeClient):
        payload.update({"endpoint": profile.endpoint})
    elif isinstance(agent_runtime, FakeAgentRuntimeClient):
        pass
    return payload


def create_app(
    service: ViewerService | None = None,
    project_root: Path | None = None,
    thread_service: DesignThreadService | None = None,
    agent_runtime_client: AgentRuntimeClient | None = None,
    config: FlowCadConfig | None = None,
) -> FastAPI:
    viewer_service = service or ViewerService(project_root or _project_root_from_env())
    design_threads = thread_service or DesignThreadService(viewer_service)
    flow_config = config or viewer_service.project.config
    agent_profile = flow_config.active_agent_profile()
    agent_runtime = agent_runtime_client or _agent_runtime_from_config(viewer_service.project_root, flow_config)
    app = FastAPI(title="Flow CAD Viewer API")
    app.state.viewer_service = viewer_service
    app.state.design_threads = design_threads
    app.state.agent_runtime = agent_runtime
    app.state.flow_config = flow_config
    app.state.agent_profile = agent_profile

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1):\d+",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, object]:
        return {
            "ok": True,
            "project_root": str(viewer_service.project_root),
            "revision": viewer_service.revision,
            "config": {
                "user_config_path": str(flow_config.user_config_path),
                "project_config_path": str(flow_config.project_config_path) if flow_config.project_config_path else None,
                "sources": [str(path) for path in flow_config.sources],
            },
            "agent_runtime": _agent_runtime_health(agent_runtime, agent_profile),
        }

    @app.get("/api/design-threads")
    def list_design_threads() -> dict[str, object]:
        return design_threads.list_threads()

    @app.post("/api/design-threads")
    def create_design_thread(payload: dict[str, object]) -> dict[str, object]:
        try:
            return design_threads.create_thread(payload)
        except ThreadStorageError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/api/design-threads/{thread_id}")
    def get_design_thread(thread_id: str) -> dict[str, object]:
        try:
            return design_threads.get_thread(thread_id)
        except ThreadNotFoundError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.patch("/api/design-threads/{thread_id}")
    def patch_design_thread(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return design_threads.patch_thread(thread_id, payload)
        except ThreadNotFoundError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/messages")
    def post_design_thread_message(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return design_threads.append_message(thread_id, payload)
        except (ThreadStorageError, ThreadNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/draft-events")
    def post_design_thread_draft_event(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return design_threads.append_draft_event(thread_id, payload)
        except (ThreadStorageError, ThreadNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/validator-events")
    def post_design_thread_validator_event(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return design_threads.append_validator_event(thread_id, payload)
        except (ThreadStorageError, ThreadNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/chat")
    def post_design_thread_chat(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            prepared = design_threads.begin_chat_turn(thread_id, payload)
            deterministic = _deterministic_draft_chat_turn(design_threads, viewer_service, thread_id, prepared)
            if deterministic is not None:
                messages = [prepared["user_message"], *deterministic["messages"]]
                return {
                    "thread_id": thread_id,
                    "messages": messages,
                    "events": deterministic.get("events", []),
                    "context_snapshot": prepared.get("context_snapshot"),
                    "draft_result": deterministic.get("draft_result"),
                    "draft_preview_model": deterministic.get("draft_preview_model"),
                    "thread": design_threads.get_thread(thread_id),
                }
            messages, context_packet, safe_tools, model_profile, metadata_base = _agent_turn_runtime_inputs(
                design_threads,
                thread_id,
                payload,
                prepared,
                agent_runtime,
                agent_profile,
            )
            assistant_chunks: list[str] = []
            persisted_messages = [prepared["user_message"]]
            runtime_events: list[dict[str, Any]] = []
            for event in agent_runtime.stream_chat(thread_id, messages, context_packet, safe_tools, model_profile):
                event = dict(event)
                event["thread_id"] = thread_id
                runtime_events.append(event)
                if str(event.get("type") or "") == "assistant_delta":
                    assistant_chunks.append(_assistant_delta_text(event))
                    continue
                message = _persist_agent_runtime_event(design_threads, thread_id, event, metadata_base)
                if message is not None:
                    persisted_messages.append(message)

            if assistant_chunks:
                persisted_messages.append(
                    design_threads.append_message(
                        thread_id,
                        {
                            "type": "assistant_message",
                            "role": "assistant",
                            "content": "".join(assistant_chunks),
                            "metadata": metadata_base,
                        },
                    )
                )

            return {
                "thread_id": thread_id,
                "messages": persisted_messages,
                "events": runtime_events,
                "context_snapshot": prepared.get("context_snapshot"),
                "thread": design_threads.get_thread(thread_id),
            }
        except (ThreadStorageError, ThreadNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        except AgentRuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/chat/stream")
    def post_design_thread_chat_stream(thread_id: str, payload: dict[str, object]) -> StreamingResponse:
        try:
            prepared = design_threads.begin_chat_turn(thread_id, payload)
        except (ThreadStorageError, ThreadNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

        def event_stream():
            assistant_chunks: list[str] = []
            messages, context_packet, safe_tools, model_profile, metadata_base = _agent_turn_runtime_inputs(
                design_threads,
                thread_id,
                payload,
                prepared,
                agent_runtime,
                agent_profile,
            )

            yield _sse({"message": prepared["user_message"]})
            try:
                deterministic = _deterministic_draft_chat_turn(design_threads, viewer_service, thread_id, prepared)
                if deterministic is not None:
                    for message in deterministic["messages"]:
                        yield _sse({"message": message})
                    yield _sse(
                        {
                            "done": True,
                            "draft_result": deterministic.get("draft_result"),
                            "draft_preview_model": deterministic.get("draft_preview_model"),
                            "thread": design_threads.get_thread(thread_id),
                        }
                    )
                    yield "data: [DONE]\n\n"
                    return

                for event in agent_runtime.stream_chat(
                    thread_id,
                    messages,
                    context_packet,
                    safe_tools,
                    model_profile,
                ):
                    event["thread_id"] = thread_id
                    event_type = str(event.get("type") or "")
                    if event_type == "assistant_delta":
                        assistant_chunks.append(_assistant_delta_text(event))
                        yield _sse({"event": event})
                    elif event_type in {"tool_call", "tool_result", "error"}:
                        message = _persist_agent_runtime_event(design_threads, thread_id, event, metadata_base)
                        yield _sse({"event": event, "message": message})
                    elif event_type == "done":
                        yield _sse({"event": event})

                if assistant_chunks:
                    assistant_message = design_threads.append_message(
                        thread_id,
                        {
                            "type": "assistant_message",
                            "role": "assistant",
                            "content": "".join(assistant_chunks),
                            "metadata": metadata_base,
                        },
                    )
                    yield _sse({"message": assistant_message})

                yield _sse({"done": True, "thread": design_threads.get_thread(thread_id)})
                yield "data: [DONE]\n\n"
            except AgentRuntimeError as exc:
                yield _sse({"event": {"type": "error", "thread_id": thread_id, "error": str(exc)}})
            except Exception as exc:  # pragma: no cover - defensive stream boundary
                yield _sse({"event": {"type": "error", "thread_id": thread_id, "error": f"Assistant stream failed: {exc}"}})

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/api/design-threads/{thread_id}/context-snapshots")
    def create_design_thread_context_snapshot(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return design_threads.create_context_snapshot(thread_id, payload)
        except (ThreadStorageError, ThreadNotFoundError, ViewerError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/attachments/viewport-screenshot")
    def create_viewport_screenshot_attachment(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return design_threads.add_viewport_screenshot_attachment(thread_id, payload)
        except (ThreadStorageError, ThreadNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/visual-evidence")
    def create_visual_evidence(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return design_threads.add_visual_evidence(thread_id, payload)
        except (ThreadStorageError, ThreadNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/visual-evidence-requests")
    def create_visual_evidence_request(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return design_threads.request_visual_evidence(thread_id, payload)
        except (ThreadStorageError, ThreadNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/design-threads/{thread_id}/visual-evidence-requests")
    def list_visual_evidence_requests(thread_id: str, status: str | None = None) -> dict[str, object]:
        try:
            return design_threads.list_visual_evidence_requests(thread_id, status=status)
        except (ThreadStorageError, ThreadNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/design-threads/{thread_id}/visual-evidence-requests/{request_id}")
    def get_visual_evidence_request(thread_id: str, request_id: str) -> dict[str, object]:
        try:
            return design_threads.get_visual_evidence_request(thread_id, request_id)
        except (ThreadNotFoundError, VisualEvidenceRequestNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/visual-evidence-requests/{request_id}/complete")
    def complete_visual_evidence_request(
        thread_id: str,
        request_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        try:
            return design_threads.fulfill_visual_evidence_request(thread_id, request_id, payload)
        except (ThreadStorageError, ThreadNotFoundError, VisualEvidenceRequestNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/visual-evidence-requests/{request_id}/fail")
    def fail_visual_evidence_request(
        thread_id: str,
        request_id: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        try:
            return design_threads.fail_visual_evidence_request(thread_id, request_id, payload)
        except (ThreadStorageError, ThreadNotFoundError, VisualEvidenceRequestNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/design-threads/{thread_id}/visual-evidence/{artifact_id}")
    def get_visual_evidence(thread_id: str, artifact_id: str) -> dict[str, object]:
        try:
            return design_threads.get_visual_evidence(thread_id, artifact_id)
        except (ThreadNotFoundError, VisualEvidenceNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/design-threads/{thread_id}/visual-evidence/{artifact_id}/image")
    def get_visual_evidence_image(thread_id: str, artifact_id: str) -> FileResponse:
        try:
            path = design_threads.get_visual_evidence_image(thread_id, artifact_id)
            return FileResponse(
                path,
                media_type="image/png",
                filename=path.name,
            )
        except (ThreadNotFoundError, VisualEvidenceNotFoundError, ThreadStorageError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/parts")
    def parts() -> dict[str, object]:
        return viewer_service.list_parts()

    @app.post("/api/imports/model")
    async def import_model(request: Request) -> dict[str, object]:
        filename = request.headers.get("X-Flow-CAD-Filename", "import.step")
        content = await request.body()
        try:
            return viewer_service.import_step_file(filename, content)
        except ViewerError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/api/imports/{import_id}/model")
    def imported_model(import_id: str) -> FileResponse:
        try:
            path = viewer_service.imported_model_path(import_id)
        except ViewerError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return FileResponse(
            path,
            media_type="model/stl",
            filename=path.name,
            headers={"X-Flow-CAD-Source-Format": "step"},
        )

    @app.get("/api/parts/{component_id}/model")
    def model(component_id: str) -> FileResponse:
        try:
            path, source_format = viewer_service.model_path(component_id)
        except ViewerError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        return FileResponse(
            path,
            media_type="model/stl",
            filename=path.name,
            headers={"X-Flow-CAD-Source-Format": source_format},
        )

    @app.get("/api/parts/{component_id}/source")
    def source(component_id: str) -> dict[str, object]:
        try:
            return viewer_service.source_context(component_id)
        except ViewerError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/api/parts/{component_id}/snap-features")
    def snap_features(component_id: str) -> dict[str, object]:
        try:
            return viewer_service.snap_features(component_id)
        except ViewerError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/api/parts/{component_id}/preview-context")
    def part_preview_context(component_id: str) -> dict[str, object]:
        try:
            return viewer_service.preview_context(component_id)
        except ViewerError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/preview-commands/panel")
    def preview_command_proposal(payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.preview_command_proposal(payload)
        except ViewerError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/drafts/box")
    def draft_create_box(payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_create_box(payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/drafts/{draft_token}/thickness")
    def draft_set_panel_thickness(draft_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_set_panel_thickness(draft_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/drafts/{draft_token}/holes")
    def draft_add_hole(draft_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_add_hole(draft_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/drafts/{draft_token}/counterbores")
    def draft_add_counterbore(draft_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_add_counterbore(draft_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/drafts/{draft_token}/slots")
    def draft_add_slot(draft_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_add_slot(draft_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/drafts/{draft_token}/raised-walls")
    def draft_add_raised_wall(draft_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_add_raised_wall(draft_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/drafts/{draft_token}/louver-patterns")
    def draft_add_louver_pattern(draft_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_add_louver_pattern(draft_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/drafts/{draft_token}/mirror-features")
    def draft_mirror_features(draft_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_mirror_features(draft_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/drafts/{draft_token}/measure")
    def draft_measure(draft_token: str) -> dict[str, object]:
        try:
            return viewer_service.draft_measure(draft_token)
        except DraftGeometryError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/drafts/{draft_token}/export-step")
    def draft_export_step(draft_token: str) -> dict[str, object]:
        try:
            return viewer_service.draft_export_step(draft_token)
        except DraftGeometryError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.delete("/api/drafts/{draft_token}")
    def draft_discard(draft_token: str) -> dict[str, object]:
        try:
            return viewer_service.draft_discard(draft_token)
        except DraftGeometryError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/draft-transactions")
    def draft_begin_transaction(payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_begin_transaction(payload)
        except DraftGeometryError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/draft-transactions/{transaction_token}/box")
    def draft_transaction_create_box(transaction_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_create_box(transaction_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/draft-transactions/{transaction_token}/thickness")
    def draft_transaction_set_panel_thickness(transaction_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_set_panel_thickness(transaction_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/draft-transactions/{transaction_token}/holes")
    def draft_transaction_add_hole(transaction_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_add_hole(transaction_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/draft-transactions/{transaction_token}/counterbores")
    def draft_transaction_add_counterbore(transaction_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_add_counterbore(transaction_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/draft-transactions/{transaction_token}/slots")
    def draft_transaction_add_slot(transaction_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_add_slot(transaction_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/draft-transactions/{transaction_token}/raised-walls")
    def draft_transaction_add_raised_wall(transaction_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_add_raised_wall(transaction_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/draft-transactions/{transaction_token}/louver-patterns")
    def draft_transaction_add_louver_pattern(transaction_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_add_louver_pattern(transaction_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/draft-transactions/{transaction_token}/mirror-features")
    def draft_transaction_mirror_features(transaction_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_mirror_features(transaction_token, payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/draft-transactions/{transaction_token}/measure")
    def draft_transaction_measure(transaction_token: str) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_measure(transaction_token)
        except DraftGeometryError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/draft-transactions/{transaction_token}/preview")
    def draft_transaction_preview(transaction_token: str) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_preview(transaction_token)
        except DraftGeometryError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/draft-transactions/{transaction_token}/preview-model")
    def draft_transaction_preview_model(transaction_token: str) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_preview_model(transaction_token)
        except (DraftGeometryError, ViewerError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/draft-transactions/{transaction_token}/model")
    def draft_transaction_model(transaction_token: str) -> FileResponse:
        try:
            path = viewer_service.draft_transaction_model(transaction_token)
        except (DraftGeometryError, ArtifactNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        return FileResponse(
            path,
            media_type="model/stl",
            filename=path.name,
            headers={"X-Flow-CAD-Source-Format": "stl"},
        )

    @app.get("/api/draft-transactions/{transaction_token}/status")
    def draft_transaction_status(transaction_token: str) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_status(transaction_token)
        except DraftGeometryError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/draft-transactions/{transaction_token}/accept")
    def draft_transaction_accept(transaction_token: str) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_accept(transaction_token)
        except DraftGeometryError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.delete("/api/draft-transactions/{transaction_token}")
    def draft_transaction_discard(transaction_token: str) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_discard(transaction_token)
        except DraftGeometryError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/reload")
    def reload_viewer() -> dict[str, object]:
        return viewer_service.reload()

    return app


app = create_app()
