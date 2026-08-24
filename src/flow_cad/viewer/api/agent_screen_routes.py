"""Protected live-browser screen capture routes for the replacement workbench."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from flow_cad.viewer.agent_screen import AgentScreenError, AgentScreenService


def create_agent_screen_router(project_root: Path) -> APIRouter:
    screens = AgentScreenService(project_root.resolve())
    router = APIRouter(prefix="/api/agent-screen", tags=["agent screen"])

    @router.post("/capture")
    def capture(payload: dict[str, object]) -> dict[str, object]:
        try:
            return screens.capture(payload)
        except AgentScreenError as error:
            raise _http_error(error) from error

    @router.get("/latest")
    def latest() -> dict[str, object]:
        try:
            return screens.latest()
        except AgentScreenError as error:
            raise _http_error(error) from error

    @router.get("/captures/{capture_id}/image")
    def image(capture_id: str) -> FileResponse:
        try:
            image_path = screens.image_path(capture_id)
        except AgentScreenError as error:
            raise _http_error(error) from error
        return FileResponse(image_path, media_type="image/png")

    @router.post("/requests")
    def request_capture(payload: dict[str, object] | None = None) -> dict[str, object]:
        try:
            return screens.request_capture(payload)
        except AgentScreenError as error:
            raise _http_error(error) from error

    @router.get("/requests")
    def list_requests(status: str | None = None) -> dict[str, object]:
        try:
            return screens.list_requests(status=status)
        except AgentScreenError as error:
            raise _http_error(error) from error

    @router.get("/requests/latest")
    def latest_request(status: str | None = "pending") -> dict[str, object]:
        try:
            return screens.latest_request(status=status)
        except AgentScreenError as error:
            raise _http_error(error) from error

    @router.post("/requests/{request_id}/fail")
    def fail_request(
        request_id: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        try:
            return screens.fail_request(request_id, payload)
        except AgentScreenError as error:
            raise _http_error(error) from error

    return router


def _http_error(error: AgentScreenError) -> HTTPException:
    return HTTPException(status_code=int(getattr(error, "status_code", 400)), detail=str(error))
