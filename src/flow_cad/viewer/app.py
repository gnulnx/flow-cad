from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from flow_cad.draft_geometry import DraftGeometryError
from flow_cad.viewer.agent_runtime import (
    AgentRuntimeClient,
    AgentRuntimeError,
    FakeAgentRuntimeClient,
    LlamaCppAgentRuntimeClient,
)
from flow_cad.viewer.threads import (
    DesignThreadService,
    ThreadNotFoundError,
    ThreadStorageError,
)
from flow_cad.viewer.service import ArtifactNotFoundError, ViewerError, ViewerService


def _project_root_from_env() -> Path | None:
    value = os.environ.get("FLOW_CAD_PROJECT_ROOT")
    return Path(value).resolve() if value else None


def _agent_runtime_from_env() -> AgentRuntimeClient:
    endpoint = os.environ.get("FLOW_CAD_AGENT_RUNTIME_ENDPOINT")
    if endpoint:
        return LlamaCppAgentRuntimeClient(
            endpoint=endpoint,
            model=os.environ.get("FLOW_CAD_AGENT_RUNTIME_MODEL", "llama3"),
            default_profile=os.environ.get("FLOW_CAD_AGENT_RUNTIME_PROFILE", "default"),
        )
    return FakeAgentRuntimeClient()


def _cad_safe_tools() -> list[dict[str, Any]]:
    return [
        {
            "name": "read_viewer_context",
            "description": "Read the active Flow CAD design-thread and viewport context.",
            "parameters": {"properties": {"thread_id": {"type": "string"}}},
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


def create_app(
    service: ViewerService | None = None,
    project_root: Path | None = None,
    thread_service: DesignThreadService | None = None,
    agent_runtime_client: AgentRuntimeClient | None = None,
) -> FastAPI:
    viewer_service = service or ViewerService(project_root or _project_root_from_env())
    design_threads = thread_service or DesignThreadService(viewer_service)
    agent_runtime = agent_runtime_client or _agent_runtime_from_env()
    app = FastAPI(title="Flow CAD Viewer API")
    app.state.viewer_service = viewer_service
    app.state.design_threads = design_threads
    app.state.agent_runtime = agent_runtime

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
            return design_threads.chat_turn(thread_id, payload)
        except (ThreadStorageError, ThreadNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/chat/stream")
    def post_design_thread_chat_stream(thread_id: str, payload: dict[str, object]) -> StreamingResponse:
        try:
            prepared = design_threads.begin_chat_turn(thread_id, payload)
        except (ThreadStorageError, ThreadNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

        def event_stream():
            assistant_chunks: list[str] = []
            context_packet = design_threads.assistant_context_packet(
                thread_id,
                context_snapshot=prepared.get("context_snapshot") if isinstance(prepared.get("context_snapshot"), dict) else None,
            )
            thread = prepared.get("thread") if isinstance(prepared.get("thread"), dict) else design_threads.get_thread(thread_id)
            messages = thread.get("messages", []) if isinstance(thread.get("messages"), list) else []
            model_profile = payload.get("model_profile") if isinstance(payload.get("model_profile"), (str, dict)) else None
            metadata_base = {
                "runtime": agent_runtime.__class__.__name__,
                **(
                    {"context_snapshot_id": prepared["context_snapshot"]["snapshot_id"]}
                    if isinstance(prepared.get("context_snapshot"), dict)
                    else {}
                ),
            }

            yield _sse({"message": prepared["user_message"]})
            try:
                for event in agent_runtime.stream_chat(
                    thread_id,
                    messages,
                    context_packet,
                    _cad_safe_tools(),
                    model_profile,
                ):
                    event["thread_id"] = thread_id
                    event_type = str(event.get("type") or "")
                    if event_type == "assistant_delta":
                        assistant_chunks.append(_assistant_delta_text(event))
                        yield _sse({"event": event})
                    elif event_type == "tool_call":
                        message = design_threads.append_message(
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
                        yield _sse({"event": event, "message": message})
                    elif event_type == "tool_result":
                        message = design_threads.append_validator_event(
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
                        yield _sse({"event": event, "message": message})
                    elif event_type == "error":
                        message = design_threads.append_message(
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

    @app.get("/api/parts")
    def parts() -> dict[str, object]:
        return viewer_service.list_parts()

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
