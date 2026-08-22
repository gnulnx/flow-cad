"""Metadata-first replacement workbench API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from flow_cad.chat import ChatStore
from flow_cad.chat.api import create_chat_command_router, create_chat_query_router
from flow_cad.jobs import JobService

from .agent_screen_routes import create_agent_screen_router
from .command_routes import create_workbench_command_router
from .job_routes import create_job_router
from .measurement_routes import create_measurement_router
from .query_routes import create_query_router


def create_app_from_environment() -> FastAPI:
    """Uvicorn factory bound to the explicit project-root environment."""

    project_root = os.environ.get("FLOW_CAD_PROJECT_ROOT")
    if not project_root:
        raise RuntimeError("FLOW_CAD_PROJECT_ROOT is required to start the workbench API")
    return create_workbench_app(Path(project_root))


def create_workbench_app(
    project_root: Path,
    *,
    max_concurrent_model_verifications: int = 2,
    max_concurrent_jobs: int = 2,
) -> FastAPI:
    """Create the replacement query API without loading project or CAD code."""

    job_service = JobService(project_root, max_concurrency=max_concurrent_jobs)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            job_service.shutdown(wait=False, cancel_pending=True)

    app = FastAPI(title="Flow CAD Workbench API", version="2", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(
        create_query_router(
            project_root,
            max_concurrent_model_verifications=max_concurrent_model_verifications,
        )
    )
    chat_store = ChatStore(project_root)
    app.include_router(create_chat_query_router(chat_store))
    app.include_router(create_chat_command_router(chat_store))
    app.include_router(create_agent_screen_router(project_root))
    app.include_router(create_workbench_command_router(project_root))
    app.include_router(create_measurement_router(project_root, job_service=job_service))
    app.include_router(create_job_router(job_service))
    app.state.project_root = project_root.resolve()
    app.state.job_service = job_service
    return app
