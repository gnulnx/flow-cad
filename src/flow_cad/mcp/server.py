from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from flow_cad.draft_geometry import DraftGeometryStore
from flow_cad.project import load_project

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


LOGGER = logging.getLogger(__name__)
DEFAULT_LOG_FILENAME = "flow_cad_mcp.log"
PROJECT_ROOT_ENV = "FLOW_CAD_PROJECT_ROOT"
ALLOWED_PROJECT_ROOTS_ENV = "FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS"
LOG_PATH_ENV = "FLOW_CAD_MCP_LOG_PATH"

_DRAFT_STORES: dict[Path, DraftGeometryStore] = {}


def resolve_log_path() -> Path:
    env_override = os.getenv(LOG_PATH_ENV)
    if env_override:
        return Path(env_override).expanduser().resolve()
    return (Path(tempfile.gettempdir()) / DEFAULT_LOG_FILENAME).resolve()


def configure_logging() -> None:
    log_path = resolve_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        filename=str(log_path),
        filemode="a",
    )
    LOGGER.info(
        "Configured Flow CAD MCP logging. path=%s pid=%s cwd=%s executable=%s argv=%s",
        log_path,
        os.getpid(),
        Path.cwd(),
        sys.executable,
        sys.argv,
    )


def resolved_allowed_project_roots() -> list[Path]:
    env_roots = os.getenv(ALLOWED_PROJECT_ROOTS_ENV)
    if env_roots:
        roots: list[Path] = []
        for raw_root in env_roots.split(os.pathsep):
            text = raw_root.strip()
            if text:
                roots.append(Path(text).expanduser().resolve())
        if roots:
            return roots

    project_root = os.getenv(PROJECT_ROOT_ENV)
    if project_root:
        return [Path(project_root).expanduser().resolve()]

    return [Path.cwd().resolve()]


def enforce_project_root(project_root: str | None = None) -> Path:
    raw_root = project_root or os.getenv(PROJECT_ROOT_ENV) or str(Path.cwd())
    candidate = Path(raw_root).expanduser().resolve()
    allowed_roots = resolved_allowed_project_roots()
    for root in allowed_roots:
        if candidate.is_relative_to(root):
            return candidate
    raise ValueError(
        f"project_root is outside allowed Flow CAD MCP roots: {candidate}. "
        f"Allowed roots: {[str(root) for root in allowed_roots]}"
    )


def draft_store(project_root: str | None = None) -> DraftGeometryStore:
    root = enforce_project_root(project_root)
    store = _DRAFT_STORES.get(root)
    if store is None:
        project = load_project(root, fallback_to_bundled=False)
        store = DraftGeometryStore(project)
        _DRAFT_STORES[root] = store
    return store


def build_server() -> FastMCP:
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        "Flow CAD MCP",
        instructions=(
            "Flow CAD MCP server for draft-only CAD geometry operations. "
            "Draft tools write only project-local runtime draft state and preview artifacts."
        ),
    )
    LOGGER.info("Created FastMCP server instance.")

    @mcp.tool(name="draft_create_box", description="Create a draft-only rectangular box or panel.")
    def draft_create_box_tool(
        length: float,
        width: float,
        height: float,
        project_root: str | None = None,
        part_id: str | None = None,
        material: str = "draft",
        role: str = "draft",
    ) -> dict[str, object]:
        LOGGER.info(
            "draft_create_box called. project_root=%s part_id=%s length=%s width=%s height=%s",
            project_root,
            part_id,
            length,
            width,
            height,
        )
        return draft_store(project_root).create_box_part(
            part_id=part_id,
            length=length,
            width=width,
            height=height,
            material=material,
            role=role,
        )

    @mcp.tool(name="draft_set_panel_thickness", description="Adjust a draft panel thickness.")
    def draft_set_panel_thickness_tool(
        draft_token: str,
        thickness: float,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("draft_set_panel_thickness called. project_root=%s draft_token=%s", project_root, draft_token)
        return draft_store(project_root).set_panel_thickness(draft_token, thickness=thickness)

    @mcp.tool(name="draft_add_hole", description="Add a draft through-hole to a selected face.")
    def draft_add_hole_tool(
        draft_token: str,
        face: str,
        x: float,
        y: float,
        diameter: float,
        through: bool = True,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("draft_add_hole called. project_root=%s draft_token=%s face=%s", project_root, draft_token, face)
        return draft_store(project_root).add_hole(
            draft_token,
            face=face,
            x=x,
            y=y,
            diameter=diameter,
            through=through,
        )

    @mcp.tool(name="draft_add_counterbore", description="Add a basic draft counterbore pocket to a selected face.")
    def draft_add_counterbore_tool(
        draft_token: str,
        face: str,
        x: float,
        y: float,
        diameter: float,
        depth: float,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info(
            "draft_add_counterbore called. project_root=%s draft_token=%s face=%s", project_root, draft_token, face
        )
        return draft_store(project_root).add_counterbore(
            draft_token,
            face=face,
            x=x,
            y=y,
            diameter=diameter,
            depth=depth,
        )

    @mcp.tool(name="draft_add_slot", description="Add a draft rounded slot to a selected face.")
    def draft_add_slot_tool(
        draft_token: str,
        face: str,
        x: float,
        y: float,
        length: float,
        width: float,
        angle: float = 0.0,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("draft_add_slot called. project_root=%s draft_token=%s face=%s", project_root, draft_token, face)
        return draft_store(project_root).add_slot(
            draft_token,
            face=face,
            x=x,
            y=y,
            length=length,
            width=width,
            angle=angle,
        )

    @mcp.tool(name="draft_add_louver_pattern", description="Add a draft louver pattern as repeated rounded slots.")
    def draft_add_louver_pattern_tool(
        draft_token: str,
        face: str,
        count: int,
        pitch: float,
        x: float,
        y: float,
        width: float,
        height: float,
        angle: float = 0.0,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info(
            "draft_add_louver_pattern called. project_root=%s draft_token=%s face=%s count=%s",
            project_root,
            draft_token,
            face,
            count,
        )
        return draft_store(project_root).add_louver_pattern(
            draft_token,
            face=face,
            count=count,
            pitch=pitch,
            x=x,
            y=y,
            width=width,
            height=height,
            angle=angle,
        )

    @mcp.tool(name="draft_mirror_features", description="Mirror draft features to the opposing parallel face.")
    def draft_mirror_features_tool(
        draft_token: str,
        source_face: str,
        target_face: str,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info(
            "draft_mirror_features called. project_root=%s draft_token=%s source_face=%s target_face=%s",
            project_root,
            draft_token,
            source_face,
            target_face,
        )
        return draft_store(project_root).mirror_features(
            draft_token,
            source_face=source_face,
            target_face=target_face,
        )

    @mcp.tool(name="draft_measure", description="Measure a draft part and return structured geometry facts.")
    def draft_measure_tool(draft_token: str, project_root: str | None = None) -> dict[str, object]:
        LOGGER.info("draft_measure called. project_root=%s draft_token=%s", project_root, draft_token)
        return draft_store(project_root).measure_part(draft_token)

    @mcp.tool(name="draft_export_step", description="Export a draft-only STEP preview under project local state.")
    def draft_export_step_tool(draft_token: str, project_root: str | None = None) -> dict[str, object]:
        LOGGER.info("draft_export_step called. project_root=%s draft_token=%s", project_root, draft_token)
        return draft_store(project_root).export_draft_step(draft_token)

    @mcp.tool(name="draft_discard", description="Discard a draft token and remove its local runtime artifacts.")
    def draft_discard_tool(draft_token: str, project_root: str | None = None) -> dict[str, object]:
        LOGGER.info("draft_discard called. project_root=%s draft_token=%s", project_root, draft_token)
        return draft_store(project_root).discard(draft_token)

    LOGGER.info(
        "Registered MCP tools: draft_create_box, draft_set_panel_thickness, draft_add_hole, "
        "draft_add_counterbore, draft_add_slot, draft_add_louver_pattern, draft_mirror_features, "
        "draft_measure, draft_export_step, draft_discard"
    )
    return mcp


def main() -> None:
    configure_logging()
    LOGGER.info("Starting Flow CAD MCP server over stdio transport.")
    server = build_server()
    try:
        server.run(transport="stdio")
    except Exception:
        LOGGER.exception("Flow CAD MCP server terminated with an exception.")
        raise


__all__ = ["build_server", "main"]
