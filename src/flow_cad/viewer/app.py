from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from flow_cad.editing.service import EditServiceError
from flow_cad.viewer.service import ViewerError, ViewerService


def _project_root_from_env() -> Path | None:
    value = os.environ.get("FLOW_CAD_PROJECT_ROOT")
    return Path(value).resolve() if value else None


def create_app(service: ViewerService | None = None, project_root: Path | None = None) -> FastAPI:
    viewer_service = service or ViewerService(project_root or _project_root_from_env())
    app = FastAPI(title="Flow CAD Viewer API")
    app.state.viewer_service = viewer_service

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

    @app.get("/api/edit/status")
    def edit_status() -> dict[str, object]:
        try:
            return viewer_service.edit_status()
        except EditServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.get("/api/edit/document")
    def edit_document() -> dict[str, object]:
        try:
            return viewer_service.edit_document()
        except EditServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/edit/operations")
    def edit_operations(operation: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.append_edit_operation(operation)
        except EditServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.patch("/api/edit/entities/{entity_id}")
    def edit_entity(entity_id: str, patch: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.patch_edit_entity(entity_id, patch)
        except EditServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.delete("/api/edit/entities/{entity_id}")
    def delete_edit_entity(entity_id: str) -> dict[str, object]:
        try:
            return viewer_service.delete_edit_entity(entity_id)
        except EditServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/edit/points")
    def edit_points(point: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.create_edit_point(point)
        except EditServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.patch("/api/edit/points/{point_id}")
    def edit_point(point_id: str, patch: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.patch_edit_point(point_id, patch)
        except EditServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/edit/holes")
    def edit_holes(hole: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.create_edit_hole(hole)
        except EditServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/edit/booleans")
    def edit_booleans(operation: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.create_edit_boolean(operation)
        except EditServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/edit/splits")
    def edit_splits(operation: dict[str, object]) -> dict[str, object]:
        try:
            return viewer_service.create_edit_split(operation)
        except EditServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/edit/undo")
    def edit_undo() -> dict[str, object]:
        try:
            return viewer_service.undo_edit_operation()
        except EditServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/reload")
    def reload_viewer() -> dict[str, object]:
        return viewer_service.reload()

    return app


app = create_app()
