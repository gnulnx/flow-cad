from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from flow_cad.config import AgentProfile, FlowCadConfig, load_flow_config
from flow_cad.design_planner import plan_design_turn
from flow_cad.draft_geometry import DraftGeometryError
from flow_cad.sketch_intent import build_sketch_intent_recipe
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
from flow_cad.viewer.worker_jobs import CodexWorkerJobManager, WorkerJobError


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


def _planner_metadata(prepared: dict[str, Any]) -> dict[str, Any]:
    metadata = {"runtime": "flow_cad_design_planner"}
    context_snapshot = prepared.get("context_snapshot")
    if isinstance(context_snapshot, dict):
        snapshot_id = context_snapshot.get("snapshot_id")
        if isinstance(snapshot_id, str) and snapshot_id.strip():
            metadata["context_snapshot_id"] = snapshot_id.strip()
    return metadata


def _append_design_plan_for_turn(
    design_threads: DesignThreadService,
    thread_id: str,
    prepared: dict[str, Any],
) -> dict[str, Any]:
    plan_payload = plan_design_turn(
        str(prepared.get("message_text") or ""),
        prepared.get("context_snapshot") if isinstance(prepared.get("context_snapshot"), dict) else None,
    )
    return design_threads.append_design_plan(
        thread_id,
        {
            "plan": plan_payload,
            "metadata": _planner_metadata(prepared),
        },
    )


def _design_plan_type(message: dict[str, Any]) -> str:
    content = message.get("content")
    if not isinstance(content, dict):
        return ""
    return str(content.get("plan_type") or "")


def _question_plan_response_content(plan_message: dict[str, Any]) -> str:
    content = plan_message.get("content")
    plan = content if isinstance(content, dict) else {}
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    questions = [
        str(step.get("summary") or "").strip()
        for step in steps
        if isinstance(step, dict) and str(step.get("step_type") or step.get("kind") or "") == "question"
    ]
    questions = [question for question in questions if question]
    if not questions:
        questions = ["What constraints should I use before drafting?"]
    rendered = "\n".join(f"- {question}" for question in questions[:5])
    return f"Before I draft this, I need a few decisions:\n\n{rendered}"


def _normalized_context_ids(prepared: dict[str, Any], key: str) -> list[str]:
    snapshot = prepared.get("context_snapshot")
    if not isinstance(snapshot, dict):
        return []
    values = snapshot.get(key)
    if not isinstance(values, list):
        return []
    return [str(value) for value in values if str(value).strip()]


def _context_has_annotations(prepared: dict[str, Any]) -> bool:
    snapshot = prepared.get("context_snapshot")
    if not isinstance(snapshot, dict):
        return False
    annotations = snapshot.get("annotations")
    if isinstance(annotations, list) and annotations:
        return True
    viewer_state = snapshot.get("viewer_state")
    if isinstance(viewer_state, dict):
        viewer_annotations = viewer_state.get("annotations")
        return isinstance(viewer_annotations, list) and bool(viewer_annotations)
    return False


def _visual_evidence_request_payload(
    prepared: dict[str, Any],
    *,
    source: str,
    arguments: dict[str, Any] | None = None,
    purpose: str | None = None,
) -> dict[str, Any]:
    args = arguments if isinstance(arguments, dict) else {}
    selected_ids = _normalized_context_ids(prepared, "selected_part_ids")
    visible_ids = _normalized_context_ids(prepared, "visible_part_ids")
    requested_part_ids = args.get("part_ids")
    part_ids = [str(value) for value in requested_part_ids if str(value).strip()] if isinstance(requested_part_ids, list) else []
    view = str(args.get("view") or args.get("preset") or ("top" if _context_has_annotations(prepared) else "iso"))
    snapshot = prepared.get("context_snapshot") if isinstance(prepared.get("context_snapshot"), dict) else {}
    return {
        "source": source,
        "view": view,
        "selected_ids": selected_ids,
        "visible_ids": visible_ids,
        "part_ids": part_ids or visible_ids or selected_ids,
        "purpose": str(args.get("purpose") or purpose or "capture visual context for the current design request"),
        "metadata": {
            "created_by": "design_thread_chat",
            **({"context_snapshot_id": snapshot.get("snapshot_id")} if isinstance(snapshot.get("snapshot_id"), str) else {}),
        },
    }


def _design_plan_needs_visual_evidence(plan_message: dict[str, Any], prepared: dict[str, Any]) -> bool:
    if _design_plan_type(plan_message) != "draft_plan":
        return False
    if not _context_has_annotations(prepared):
        return False
    content = plan_message.get("content")
    if not isinstance(content, dict):
        return False
    steps = content.get("steps")
    if not isinstance(steps, list):
        return False
    step_ids = {
        str(step.get("step_id") or "")
        for step in steps
        if isinstance(step, dict)
    }
    return bool({"derive_footprint_from_annotations", "locate_hole_marks"} & step_ids)


def _should_request_visual_evidence_before_deterministic_draft(
    plan_message: dict[str, Any],
    prepared: dict[str, Any],
) -> bool:
    if not _design_plan_needs_visual_evidence(plan_message, prepared):
        return False
    return _draft_transaction_token_from_prepared(prepared) is None


def _append_visual_evidence_request_for_plan(
    design_threads: DesignThreadService,
    thread_id: str,
    prepared: dict[str, Any],
    plan_message: dict[str, Any],
) -> dict[str, Any]:
    request = design_threads.request_visual_evidence(
        thread_id,
        _visual_evidence_request_payload(
            prepared,
            source="agent",
            purpose="capture top-view evidence for annotated draft planning",
        ),
    )
    metadata = plan_message.get("metadata")
    plan_id = str(metadata.get("plan_id") or "") if isinstance(metadata, dict) else ""
    assistant_message = design_threads.append_message(
        thread_id,
        {
            "type": "assistant_message",
            "role": "assistant",
            "content": (
                f"I created a {request['view']} visual-evidence request for the annotated draft plan. "
                "Once the viewer captures it, I can use that evidence to continue the draft."
            ),
            "metadata": {
                **_planner_metadata(prepared),
                "status": "waiting_for_visual_evidence",
                "plan_id": plan_id,
                "visual_evidence_request_id": request["request_id"],
            },
        },
    )
    return {"request": request, "messages": [assistant_message]}


def _persist_runtime_event_and_side_effects(
    design_threads: DesignThreadService,
    thread_id: str,
    event: dict[str, Any],
    metadata_base: dict[str, Any],
    prepared: dict[str, Any],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    message = _persist_agent_runtime_event(design_threads, thread_id, event, metadata_base)
    if message is not None:
        messages.append(message)

    if str(event.get("type") or "") != "tool_call":
        return messages
    if str(event.get("tool") or "") != "request_visual_evidence":
        return messages

    arguments = event.get("arguments") if isinstance(event.get("arguments"), dict) else {}
    request = design_threads.request_visual_evidence(
        thread_id,
        _visual_evidence_request_payload(prepared, source="agent", arguments=arguments),
    )
    result_message = _persist_agent_runtime_event(
        design_threads,
        thread_id,
        {
            "type": "tool_result",
            "tool": "request_visual_evidence",
            "result": {
                "status": "pending",
                "summary": f"Created visual evidence request {request['request_id']}",
                "request_id": request["request_id"],
                "view": request["view"],
            },
        },
        metadata_base,
    )
    if result_message is not None:
        messages.append(result_message)
    return messages


def _snapshot_annotations(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    viewer_state = snapshot.get("viewer_state") if isinstance(snapshot.get("viewer_state"), dict) else {}
    annotations = viewer_state.get("annotations")
    if not isinstance(annotations, list):
        annotations = snapshot.get("annotations")
    return [annotation for annotation in annotations if isinstance(annotation, dict)] if isinstance(annotations, list) else []


def _annotation_points(annotation: dict[str, Any]) -> list[tuple[float, float]]:
    points = annotation.get("points")
    result: list[tuple[float, float]] = []
    if isinstance(points, list):
        for point in points:
            if not isinstance(point, dict):
                continue
            x = point.get("x")
            y = point.get("y")
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                result.append((min(max(float(x), 0.0), 1.0), min(max(float(y), 0.0), 1.0)))
    if not result:
        x = annotation.get("x")
        y = annotation.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            result.append((min(max(float(x), 0.0), 1.0), min(max(float(y), 0.0), 1.0)))
    return result


def _annotation_bounds(annotations: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    points = [point for annotation in annotations for point in _annotation_points(annotation)]
    if not points:
        return (0.0, 1.0, 0.0, 1.0)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    min_x = min(xs)
    max_x = max(xs)
    min_y = min(ys)
    max_y = max(ys)
    if max_x - min_x < 0.01:
        min_x, max_x = 0.0, 1.0
    if max_y - min_y < 0.01:
        min_y, max_y = 0.0, 1.0
    return (min_x, max_x, min_y, max_y)


def _small_annotation_centers(annotations: list[dict[str, Any]]) -> list[tuple[float, float]]:
    centers: list[tuple[float, float]] = []
    for annotation in annotations:
        kind = str(annotation.get("kind") or "").lower()
        points = _annotation_points(annotation)
        if kind == "circle":
            if points:
                centers.append(points[0])
            continue
        if len(points) < 3:
            continue
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        if width <= 0.18 and height <= 0.18:
            centers.append((sum(xs) / len(xs), sum(ys) / len(ys)))
    return centers[:8]


def _sketch_dimensions_from_text(text: str) -> tuple[float, float, float]:
    lowered = text.lower()
    thickness = 10.0
    thickness_match = re.search(r"(\d+(?:\.\d+)?)\s*mm\s*(?:thick|thickness)", lowered)
    if thickness_match:
        thickness = float(thickness_match.group(1))

    pair_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*[x×]\s*(\d+(?:\.\d+)?)\s*mm", lowered)
    if not pair_match:
        pair_match = re.search(r"roughly\s+(\d+(?:\.\d+)?)\s*(?:mm)?\s+(?:by|x|×)\s+(\d+(?:\.\d+)?)\s*mm", lowered)
    if pair_match:
        first = float(pair_match.group(1))
        second = float(pair_match.group(2))
        return max(first, second), min(first, second), thickness

    values = [float(match.group(1)) for match in re.finditer(r"(\d+(?:\.\d+)?)\s*mm", lowered)]
    if len(values) >= 3:
        plan_values = values[-2:]
        return max(plan_values), min(plan_values), thickness
    if len(values) >= 2:
        return max(values[-2:]), min(values[-2:]), thickness
    return 100.0, 65.0, thickness


def _hole_diameter_from_text(text: str) -> float:
    metric = re.search(r"\bm\s*(\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
    if metric:
        return float(metric.group(1))
    return 4.0


def _user_message_for_snapshot(thread: dict[str, Any], snapshot_id: str) -> str:
    for message in reversed(thread.get("messages", [])):
        if not isinstance(message, dict):
            continue
        if message.get("type") != "user_message":
            continue
        metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
        if metadata.get("context_snapshot_id") == snapshot_id:
            return str(message.get("content") or "")
    return ""


def _snapshot_for_id(thread: dict[str, Any], snapshot_id: str) -> dict[str, Any] | None:
    snapshots = thread.get("context_snapshots") if isinstance(thread.get("context_snapshots"), list) else []
    for snapshot in snapshots:
        if isinstance(snapshot, dict) and snapshot.get("snapshot_id") == snapshot_id:
            return snapshot
    return None


def _continue_annotated_draft_after_visual_evidence(
    design_threads: DesignThreadService,
    viewer_service: ViewerService,
    thread_id: str,
    completion: dict[str, Any],
) -> dict[str, Any] | None:
    evidence = completion.get("visual_evidence") if isinstance(completion.get("visual_evidence"), dict) else {}
    metadata = evidence.get("metadata") if isinstance(evidence.get("metadata"), dict) else {}
    if metadata.get("created_by") != "design_thread_chat":
        return None
    snapshot_id = metadata.get("context_snapshot_id")
    if not isinstance(snapshot_id, str) or not snapshot_id:
        return None

    thread = design_threads.get_thread(thread_id)
    snapshot = _snapshot_for_id(thread, snapshot_id)
    if snapshot is None:
        return None
    annotations = _snapshot_annotations(snapshot)
    if not annotations:
        return None

    command = _user_message_for_snapshot(thread, snapshot_id)
    length, width, thickness = _sketch_dimensions_from_text(command)
    diameter = _hole_diameter_from_text(command)
    part_id = "sketch_plate"
    sketch_recipe = build_sketch_intent_recipe(
        annotations,
        {"length": length, "width": width, "thickness": thickness},
        options={"symmetry": "y" if "sym" in command.lower() else None},
        part_id=part_id,
    )
    transaction = viewer_service.draft_begin_transaction({"part_id": part_id})
    transaction_token = str(transaction["transaction_token"])
    applied_operations: list[dict[str, Any]] = []
    outline = sketch_recipe.get("outline") if isinstance(sketch_recipe.get("outline"), dict) else {}
    profile_points = outline.get("points") if isinstance(outline, dict) else None
    create_payload = {
        "part_id": part_id,
        "length": length,
        "width": width,
        "height": thickness,
        "profile_points": profile_points,
    }
    create_result = viewer_service.draft_transaction_create_profile(transaction_token, create_payload)
    applied_operations.append(
        {
            "name": "create_sketch_profile",
            "endpoint": "profile",
            "parameters": create_payload,
            "result": create_result,
        }
    )

    wants_counterbore = "counter" in command.lower()
    holes = sketch_recipe.get("holes") if isinstance(sketch_recipe.get("holes"), list) else []
    for hole in holes:
        if not isinstance(hole, dict):
            continue
        center = hole.get("center")
        if not isinstance(center, (list, tuple)) or len(center) != 2:
            continue
        x = min(max(float(center[0]) + length / 2.0, 0.0), length)
        y = min(max(float(center[1]) + width / 2.0, 0.0), width)
        if wants_counterbore:
            payload = {
                "face": "top",
                "x": x,
                "y": y,
                "diameter": max(diameter * 1.8, diameter + 3.0),
                "depth": min(2.5, thickness / 2.0),
            }
            result = viewer_service.draft_transaction_add_counterbore(transaction_token, payload)
            applied_operations.append(
                {
                    "name": "add_counterbore",
                    "endpoint": "counterbores",
                    "parameters": payload,
                    "result": result,
                }
            )
        else:
            payload = {"face": "top", "x": x, "y": y, "diameter": diameter, "through": True}
            result = viewer_service.draft_transaction_add_hole(transaction_token, payload)
            applied_operations.append({"name": "add_hole", "endpoint": "holes", "parameters": payload, "result": result})

    preview_model = viewer_service.draft_transaction_preview_model(transaction_token)
    metadata_base = {
        "runtime": "flow_cad_visual_evidence_continuation",
        "context_snapshot_id": snapshot_id,
        "visual_evidence_request_id": metadata.get("visual_evidence_request_id"),
        "visual_evidence_artifact_id": evidence.get("artifact_id"),
        "draft_transaction_token": transaction_token,
        "part_id": part_id,
    }
    messages = [
        design_threads.append_draft_event(
            thread_id,
            {
                "content": {
                    "action": "apply",
                    "summary": "Applied approximate sketch draft operations from visual evidence",
                    "draft_transaction_token": transaction_token,
                    "part_id": part_id,
                    "operations": applied_operations,
                    "assumptions": [
                        "Interpreted the sketch outline as a cleaned draft profile; sketch geometry is not exact CAD.",
                        "Mapped small annotation marks onto the top face as hole/counterbore centers.",
                        *sketch_recipe.get("assumptions", []),
                    ],
                    "warnings": sketch_recipe.get("warnings", []),
                },
                "metadata": metadata_base,
            },
        ),
        design_threads.append_draft_event(
            thread_id,
            {
                "content": {
                    "action": "preview",
                    "summary": "Draft preview generated from visual evidence",
                    "draft_transaction_token": transaction_token,
                    "part_id": part_id,
                    "preview_model": preview_model,
                },
                "metadata": metadata_base,
            },
        ),
        design_threads.append_message(
            thread_id,
            {
                "type": "assistant_message",
                "role": "assistant",
                "content": (
                    f"Created draft `{part_id}` from the captured sketch evidence as "
                    f"an interpreted {length:g} x {width:g} x {thickness:g} mm profile with "
                    f"{max(len(applied_operations) - 1, 0)} approximate {'counterbores' if wants_counterbore else 'holes'}. "
                    "Inspect the preview, then accept or discard the draft."
                ),
                "metadata": {
                    **metadata_base,
                    "status": "draft_preview_ready",
                    "source_loop_commands": preview_model.get("source_loop_commands", []),
                },
            },
        ),
    ]
    return {
        "messages": messages,
        "draft_result": {
            "ok": True,
            "part_id": part_id,
            "transaction_token": transaction_token,
            "applied_operations": applied_operations,
        },
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
    worker_job_manager: CodexWorkerJobManager | None = None,
    config: FlowCadConfig | None = None,
) -> FastAPI:
    viewer_service = service or ViewerService(project_root or _project_root_from_env())
    design_threads = thread_service or DesignThreadService(viewer_service)
    flow_config = config or viewer_service.project.config
    agent_profile = flow_config.active_agent_profile()
    agent_runtime = agent_runtime_client or _agent_runtime_from_config(viewer_service.project_root, flow_config)
    worker_jobs = worker_job_manager or CodexWorkerJobManager(
        viewer_service,
        design_threads,
        agent_profile=agent_profile,
    )
    app = FastAPI(title="Flow CAD Viewer API")
    app.state.viewer_service = viewer_service
    app.state.design_threads = design_threads
    app.state.agent_runtime = agent_runtime
    app.state.worker_jobs = worker_jobs
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

    @app.post("/api/design-threads/{thread_id}/design-plans")
    def post_design_thread_plan(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return design_threads.append_design_plan(thread_id, payload)
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

    @app.post("/api/design-threads/{thread_id}/worker-jobs")
    def create_design_thread_worker_job(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return worker_jobs.start_job(thread_id, payload)
        except (ThreadStorageError, ThreadNotFoundError, WorkerJobError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/design-threads/{thread_id}/worker-jobs/{job_id}")
    def get_design_thread_worker_job(thread_id: str, job_id: str) -> dict[str, object]:
        try:
            return worker_jobs.get_job(thread_id, job_id)
        except (ThreadStorageError, ThreadNotFoundError, WorkerJobError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/design-threads/{thread_id}/worker-jobs/{job_id}/stream")
    def stream_design_thread_worker_job(thread_id: str, job_id: str) -> StreamingResponse:
        try:
            worker_jobs.get_job(thread_id, job_id)
        except (ThreadStorageError, ThreadNotFoundError, WorkerJobError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        return StreamingResponse(worker_jobs.stream_events(thread_id, job_id), media_type="text/event-stream")

    @app.post("/api/design-threads/{thread_id}/worker-jobs/{job_id}/cancel")
    def cancel_design_thread_worker_job(thread_id: str, job_id: str) -> dict[str, object]:
        try:
            return worker_jobs.cancel_job(thread_id, job_id)
        except (ThreadStorageError, ThreadNotFoundError, WorkerJobError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/worker-jobs/{job_id}/commit")
    def commit_design_thread_worker_job(
        thread_id: str,
        job_id: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        try:
            return worker_jobs.commit_job(thread_id, job_id, payload if isinstance(payload, dict) else {})
        except (ThreadStorageError, ThreadNotFoundError, WorkerJobError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/chat")
    def post_design_thread_chat(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            prepared = design_threads.begin_chat_turn(thread_id, payload)
            design_plan_message = _append_design_plan_for_turn(design_threads, thread_id, prepared)
            if _design_plan_type(design_plan_message) == "questions":
                assistant_message = design_threads.append_message(
                    thread_id,
                    {
                        "type": "assistant_message",
                        "role": "assistant",
                        "content": _question_plan_response_content(design_plan_message),
                        "metadata": {
                            **_planner_metadata(prepared),
                            "status": "needs_user_input",
                            "plan_id": design_plan_message["metadata"]["plan_id"],
                        },
                    },
                )
                return {
                    "thread_id": thread_id,
                    "messages": [prepared["user_message"], design_plan_message, assistant_message],
                    "events": [],
                    "context_snapshot": prepared.get("context_snapshot"),
                    "thread": design_threads.get_thread(thread_id),
                }
            if _should_request_visual_evidence_before_deterministic_draft(design_plan_message, prepared):
                evidence_request = _append_visual_evidence_request_for_plan(
                    design_threads,
                    thread_id,
                    prepared,
                    design_plan_message,
                )
                return {
                    "thread_id": thread_id,
                    "messages": [prepared["user_message"], design_plan_message, *evidence_request["messages"]],
                    "events": [],
                    "context_snapshot": prepared.get("context_snapshot"),
                    "visual_evidence_request": evidence_request["request"],
                    "thread": design_threads.get_thread(thread_id),
                }
            deterministic = _deterministic_draft_chat_turn(design_threads, viewer_service, thread_id, prepared)
            if deterministic is not None:
                messages = [prepared["user_message"], design_plan_message, *deterministic["messages"]]
                return {
                    "thread_id": thread_id,
                    "messages": messages,
                    "events": deterministic.get("events", []),
                    "context_snapshot": prepared.get("context_snapshot"),
                    "draft_result": deterministic.get("draft_result"),
                    "draft_preview_model": deterministic.get("draft_preview_model"),
                    "thread": design_threads.get_thread(thread_id),
                }
            if _design_plan_needs_visual_evidence(design_plan_message, prepared):
                evidence_request = _append_visual_evidence_request_for_plan(
                    design_threads,
                    thread_id,
                    prepared,
                    design_plan_message,
                )
                return {
                    "thread_id": thread_id,
                    "messages": [prepared["user_message"], design_plan_message, *evidence_request["messages"]],
                    "events": [],
                    "context_snapshot": prepared.get("context_snapshot"),
                    "visual_evidence_request": evidence_request["request"],
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
            persisted_messages = [prepared["user_message"], design_plan_message]
            runtime_events: list[dict[str, Any]] = []
            for event in agent_runtime.stream_chat(thread_id, messages, context_packet, safe_tools, model_profile):
                event = dict(event)
                event["thread_id"] = thread_id
                runtime_events.append(event)
                if str(event.get("type") or "") == "assistant_delta":
                    assistant_chunks.append(_assistant_delta_text(event))
                    continue
                persisted_messages.extend(
                    _persist_runtime_event_and_side_effects(
                        design_threads,
                        thread_id,
                        event,
                        metadata_base,
                        prepared,
                    )
                )

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
            yield _sse({"message": prepared["user_message"]})
            try:
                design_plan_message = _append_design_plan_for_turn(design_threads, thread_id, prepared)
                yield _sse({"message": design_plan_message})
                if _design_plan_type(design_plan_message) == "questions":
                    assistant_message = design_threads.append_message(
                        thread_id,
                        {
                            "type": "assistant_message",
                            "role": "assistant",
                            "content": _question_plan_response_content(design_plan_message),
                            "metadata": {
                                **_planner_metadata(prepared),
                                "status": "needs_user_input",
                                "plan_id": design_plan_message["metadata"]["plan_id"],
                            },
                        },
                    )
                    yield _sse({"message": assistant_message})
                    yield _sse({"done": True, "thread": design_threads.get_thread(thread_id)})
                    yield "data: [DONE]\n\n"
                    return

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

                if _design_plan_needs_visual_evidence(design_plan_message, prepared):
                    evidence_request = _append_visual_evidence_request_for_plan(
                        design_threads,
                        thread_id,
                        prepared,
                        design_plan_message,
                    )
                    for message in evidence_request["messages"]:
                        yield _sse({"message": message})
                    yield _sse(
                        {
                            "done": True,
                            "visual_evidence_request": evidence_request["request"],
                            "thread": design_threads.get_thread(thread_id),
                        }
                    )
                    yield "data: [DONE]\n\n"
                    return

                messages, context_packet, safe_tools, model_profile, metadata_base = _agent_turn_runtime_inputs(
                    design_threads,
                    thread_id,
                    payload,
                    prepared,
                    agent_runtime,
                    agent_profile,
                )
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
                        persisted_messages = _persist_runtime_event_and_side_effects(
                            design_threads,
                            thread_id,
                            event,
                            metadata_base,
                            prepared,
                        )
                        if not persisted_messages:
                            yield _sse({"event": event})
                        for message in persisted_messages:
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
            completion = design_threads.fulfill_visual_evidence_request(thread_id, request_id, payload)
            continuation = _continue_annotated_draft_after_visual_evidence(
                design_threads,
                viewer_service,
                thread_id,
                completion,
            )
            if continuation is not None:
                completion = {
                    **completion,
                    "continuation": continuation,
                    "thread": design_threads.get_thread(thread_id),
                }
            return completion
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

    @app.get("/api/draft-operation-registry")
    def draft_operation_registry() -> dict[str, object]:
        return viewer_service.draft_operation_registry()

    @app.post("/api/drafts/box")
    def draft_create_box(payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_create_box(payload)
        except (DraftGeometryError, KeyError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/drafts/profile")
    def draft_create_profile(payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_create_profile(payload)
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

    @app.post("/api/draft-transactions/{transaction_token}/profile")
    def draft_transaction_create_profile(transaction_token: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.draft_transaction_create_profile(transaction_token, payload)
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
