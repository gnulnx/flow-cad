"""Metadata-first replacement workbench API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from flow_cad.annotations import AnnotationStore
from flow_cad.build import PartBuildService, ProjectBuildService
from flow_cad.chat import ChatDispatchService, ChatStore, CodexAppServerProvider
from flow_cad.chat.api import create_chat_command_router, create_chat_query_router
from flow_cad.chat.providers import ChatProvider
from flow_cad.jobs import JobService
from flow_cad.measurement import MeasurementSnapshotStore
from flow_cad.release import ReleaseGateService
from flow_cad.release.api import create_release_gate_router

from .agent_screen_routes import create_agent_screen_router
from .annotation_routes import create_annotation_router
from .build_routes import create_part_build_router, create_project_build_router
from .command_routes import create_workbench_command_router
from .job_routes import create_job_router
from .measurement_routes import create_measurement_router
from .measurement_snapshot_routes import create_measurement_snapshot_router
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
    chat_provider: ChatProvider | None = None,
    enable_default_chat_provider: bool = True,
    max_concurrent_chat_turns: int = 1,
    max_queued_chat_turns: int = 8,
) -> FastAPI:
    """Create the replacement query API without loading project or CAD code."""

    job_service = JobService(project_root, max_concurrency=max_concurrent_jobs)
    part_build_service = PartBuildService(project_root, job_service)
    project_build_service = ProjectBuildService(project_root, job_service)
    release_gate_service = ReleaseGateService(project_root, job_service)
    chat_store = ChatStore(project_root)
    resolved_chat_provider = chat_provider
    if resolved_chat_provider is None and enable_default_chat_provider:
        resolved_chat_provider = CodexAppServerProvider(project_root)
    chat_dispatch = ChatDispatchService(
        chat_store,
        resolved_chat_provider,
        max_concurrency=max_concurrent_chat_turns,
        max_queued_turns=max_queued_chat_turns,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            chat_dispatch.shutdown(wait=False, cancel_pending=True)
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
    annotation_store = AnnotationStore(project_root)
    measurement_snapshot_store = MeasurementSnapshotStore(project_root)
    app.include_router(create_chat_query_router(chat_store, chat_dispatch))
    app.include_router(create_chat_command_router(chat_store, chat_dispatch))
    app.include_router(create_annotation_router(annotation_store))
    app.include_router(create_agent_screen_router(project_root))
    app.include_router(create_workbench_command_router(project_root))
    app.include_router(create_part_build_router(part_build_service))
    app.include_router(create_project_build_router(project_build_service))
    app.include_router(create_release_gate_router(release_gate_service))
    app.include_router(create_measurement_router(project_root, job_service=job_service))
    app.include_router(create_measurement_snapshot_router(measurement_snapshot_store))
    app.include_router(create_job_router(job_service))
    app.state.project_root = project_root.resolve()
    app.state.job_service = job_service
    app.state.part_build_service = part_build_service
    app.state.project_build_service = project_build_service
    app.state.release_gate_service = release_gate_service
    app.state.chat_store = chat_store
    app.state.chat_dispatch = chat_dispatch
    app.state.annotation_store = annotation_store
    app.state.measurement_snapshot_store = measurement_snapshot_store
    return app
