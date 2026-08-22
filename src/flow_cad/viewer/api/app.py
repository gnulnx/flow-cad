"""Metadata-first replacement workbench API."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .query_routes import create_query_router


def create_workbench_app(
    project_root: Path,
    *,
    max_concurrent_model_verifications: int = 2,
) -> FastAPI:
    """Create the replacement query API without loading project or CAD code."""

    app = FastAPI(title="Flow CAD Workbench API", version="2")
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(
        create_query_router(
            project_root,
            max_concurrent_model_verifications=max_concurrent_model_verifications,
        )
    )
    return app
