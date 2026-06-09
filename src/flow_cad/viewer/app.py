from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from flow_cad.draft_geometry import DraftGeometryError
from flow_cad.viewer.threads import (
    DesignThreadService,
    ThreadNotFoundError,
    ThreadStorageError,
)
from flow_cad.viewer.service import ArtifactNotFoundError, ViewerError, ViewerService


def _project_root_from_env() -> Path | None:
    value = os.environ.get("FLOW_CAD_PROJECT_ROOT")
    return Path(value).resolve() if value else None


def create_app(
    service: ViewerService | None = None,
    project_root: Path | None = None,
    thread_service: DesignThreadService | None = None,
) -> FastAPI:
    viewer_service = service or ViewerService(project_root or _project_root_from_env())
    design_threads = thread_service or DesignThreadService(viewer_service)
    app = FastAPI(title="Flow CAD Viewer API")
    app.state.viewer_service = viewer_service
    app.state.design_threads = design_threads

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

    @app.post("/api/design-threads/{thread_id}/chat")
    def post_design_thread_chat(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return design_threads.chat_turn(thread_id, payload)
        except (ThreadStorageError, ThreadNotFoundError) as exc:
            status_code = getattr(exc, "status_code", 400)
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.post("/api/design-threads/{thread_id}/context-snapshots")
    def create_design_thread_context_snapshot(thread_id: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            return design_threads.create_context_snapshot(thread_id, payload)
        except (ThreadStorageError, ThreadNotFoundError, ViewerError) as exc:
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
