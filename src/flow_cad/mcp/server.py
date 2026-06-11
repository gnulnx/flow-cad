from __future__ import annotations

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from flow_cad.draft_operations import draft_operation_payloads
from flow_cad.draft_geometry import DraftGeometryStore
from flow_cad.project import load_project
from flow_cad.profiler import format_profile_summary, load_latest_build_profile
from flow_cad.validation.runner import FocusedValidatorRunner
from flow_cad.viewer.agent_screen import AgentScreenService
from flow_cad.viewer.service import ViewerService
from flow_cad.viewer.threads import DesignThreadService

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


LOGGER = logging.getLogger(__name__)
DEFAULT_LOG_FILENAME = "flow_cad_mcp.log"
PROJECT_ROOT_ENV = "FLOW_CAD_PROJECT_ROOT"
ALLOWED_PROJECT_ROOTS_ENV = "FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS"
LOG_PATH_ENV = "FLOW_CAD_MCP_LOG_PATH"
TOOLSET_ENV = "FLOW_CAD_MCP_TOOLSET"

_DRAFT_STORES: dict[Path, DraftGeometryStore] = {}

DRAFT_OPERATION_REGISTRY_TOOL_NAME = "draft_operation_registry"
DRAFT_OPERATION_REGISTRY_TOOL_NAMES = {DRAFT_OPERATION_REGISTRY_TOOL_NAME}

DIRECT_DRAFT_TOOL_NAMES = {
    "draft_create_box",
    "draft_create_profile",
    "draft_set_panel_thickness",
    "draft_add_hole",
    "draft_add_counterbore",
    "draft_add_slot",
    "draft_add_raised_wall",
    "draft_add_louver_pattern",
    "draft_mirror_features",
    "draft_measure",
    "draft_export_step",
    "draft_discard",
}
TRANSACTION_TOOL_NAMES = {
    "draft_begin_transaction",
    "draft_transaction_create_box",
    "draft_transaction_create_profile",
    "draft_transaction_set_panel_thickness",
    "draft_transaction_add_hole",
    "draft_transaction_add_counterbore",
    "draft_transaction_add_slot",
    "draft_transaction_add_raised_wall",
    "draft_transaction_add_louver_pattern",
    "draft_transaction_mirror_features",
    "draft_transaction_measure",
    "draft_transaction_preview",
    "draft_transaction_accept",
    "draft_transaction_discard",
}
VALIDATOR_PROFILE_TOOL_NAMES = {
    "validator_list",
    "validator_run",
    "profile_last",
}
DEFAULT_VISUAL_TOOL_NAMES = {
    "visual_evidence_list",
    "visual_evidence_get",
    "request_visual_evidence",
    "visual_evidence_requests_list",
    "agent_screen_request",
    "agent_screen_latest",
    "agent_screen_requests_list",
}
ADVANCED_VISUAL_TOOL_NAMES = DEFAULT_VISUAL_TOOL_NAMES | {"visual_evidence_create"}
DEFAULT_TOOL_NAMES = (
    TRANSACTION_TOOL_NAMES | VALIDATOR_PROFILE_TOOL_NAMES | DEFAULT_VISUAL_TOOL_NAMES | DRAFT_OPERATION_REGISTRY_TOOL_NAMES
)
TOOLSET_TOOL_NAMES = {
    "default": DEFAULT_TOOL_NAMES,
    "advanced": DIRECT_DRAFT_TOOL_NAMES
    | TRANSACTION_TOOL_NAMES
    | VALIDATOR_PROFILE_TOOL_NAMES
    | ADVANCED_VISUAL_TOOL_NAMES
    | DRAFT_OPERATION_REGISTRY_TOOL_NAMES,
    "visual": ADVANCED_VISUAL_TOOL_NAMES,
    "transactions": TRANSACTION_TOOL_NAMES | VALIDATOR_PROFILE_TOOL_NAMES | DRAFT_OPERATION_REGISTRY_TOOL_NAMES,
}


def active_toolset() -> str:
    requested = os.getenv(TOOLSET_ENV, "default").strip().lower() or "default"
    if requested not in TOOLSET_TOOL_NAMES:
        LOGGER.warning("Unknown Flow CAD MCP toolset %r; using default", requested)
        return "default"
    return requested


def active_tool_names() -> set[str]:
    return set(TOOLSET_TOOL_NAMES[active_toolset()])


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


def validation_runner(project_root: str | None = None) -> FocusedValidatorRunner:
    root = enforce_project_root(project_root)
    project = load_project(root, fallback_to_bundled=False)
    return FocusedValidatorRunner(project)


def design_thread_service(project_root: str | None = None) -> DesignThreadService:
    root = enforce_project_root(project_root)
    return DesignThreadService(ViewerService(root))


def agent_screen_service(project_root: str | None = None) -> AgentScreenService:
    root = enforce_project_root(project_root)
    return AgentScreenService(ViewerService(root))


def build_server() -> FastMCP:
    from mcp.server.fastmcp import FastMCP

    tool_names = active_tool_names()
    mcp = FastMCP(
        "Flow CAD MCP",
        instructions=(
            "Flow CAD MCP server for draft-only CAD geometry operations and transactions. "
            "Draft tools write only project-local runtime state, preview artifacts, and review artifacts."
        ),
    )
    LOGGER.info("Created FastMCP server instance. toolset=%s tools=%s", active_toolset(), sorted(tool_names))

    def tool(*, name: str, description: str):
        if name in tool_names:
            return mcp.tool(name=name, description=description)

        def decorator(func):
            LOGGER.debug("Skipping MCP tool %s for toolset %s", name, active_toolset())
            return func

        return decorator

    @tool(name="draft_create_box", description="Create a draft-only rectangular box or panel.")
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

    @tool(name="draft_create_profile", description="Create a draft-only interpreted sketch profile.")
    def draft_create_profile_tool(
        length: float,
        width: float,
        height: float,
        profile_points: list[list[float]],
        project_root: str | None = None,
        part_id: str | None = None,
        material: str = "draft",
        role: str = "draft",
    ) -> dict[str, object]:
        LOGGER.info(
            "draft_create_profile called. project_root=%s part_id=%s length=%s width=%s height=%s points=%s",
            project_root,
            part_id,
            length,
            width,
            height,
            len(profile_points),
        )
        return draft_store(project_root).create_profile_part(
            part_id=part_id,
            length=length,
            width=width,
            height=height,
            profile_points=profile_points,
            material=material,
            role=role,
        )

    @tool(name="draft_set_panel_thickness", description="Adjust a draft panel thickness.")
    def draft_set_panel_thickness_tool(
        draft_token: str,
        thickness: float,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("draft_set_panel_thickness called. project_root=%s draft_token=%s", project_root, draft_token)
        return draft_store(project_root).set_panel_thickness(draft_token, thickness=thickness)

    @tool(name="draft_add_hole", description="Add a draft through-hole to a selected face.")
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

    @tool(name="draft_add_counterbore", description="Add a basic draft counterbore pocket to a selected face.")
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

    @tool(name="draft_add_slot", description="Add a draft rounded slot to a selected face.")
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

    @tool(name="draft_add_raised_wall", description="Add a raised wall feature to a selected draft face.")
    def draft_add_raised_wall_tool(
        draft_token: str,
        face: str,
        x: float,
        y: float,
        length: float,
        width: float,
        height: float,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info(
            "draft_add_raised_wall called. project_root=%s draft_token=%s face=%s",
            project_root,
            draft_token,
            face,
        )
        return draft_store(project_root).add_raised_wall(
            draft_token,
            face=face,
            x=x,
            y=y,
            length=length,
            width=width,
            height=height,
        )

    @tool(name="draft_add_louver_pattern", description="Add a draft louver pattern as repeated rounded slots.")
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

    @tool(name="draft_mirror_features", description="Mirror draft features to the opposing parallel face.")
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

    @tool(name="draft_measure", description="Measure a draft part and return structured geometry facts.")
    def draft_measure_tool(draft_token: str, project_root: str | None = None) -> dict[str, object]:
        LOGGER.info("draft_measure called. project_root=%s draft_token=%s", project_root, draft_token)
        return draft_store(project_root).measure_part(draft_token)

    @tool(name="draft_export_step", description="Export a draft-only STEP preview under project local state.")
    def draft_export_step_tool(draft_token: str, project_root: str | None = None) -> dict[str, object]:
        LOGGER.info("draft_export_step called. project_root=%s draft_token=%s", project_root, draft_token)
        return draft_store(project_root).export_draft_step(draft_token)

    @tool(name="draft_discard", description="Discard a draft token and remove its local runtime artifacts.")
    def draft_discard_tool(draft_token: str, project_root: str | None = None) -> dict[str, object]:
        LOGGER.info("draft_discard called. project_root=%s draft_token=%s", project_root, draft_token)
        return draft_store(project_root).discard(draft_token)

    @tool(name=DRAFT_OPERATION_REGISTRY_TOOL_NAME, description="Return registered draft operations for tool discovery.")
    def draft_operation_registry_tool() -> dict[str, object]:
        operations = draft_operation_payloads()
        return {
            "ok": True,
            "operations": operations,
            "count": len(operations),
            "source": "flow_cad.draft_operations",
        }

    @tool(name="draft_begin_transaction", description="Begin a draft geometry transaction.")
    def draft_begin_transaction_tool(
        project_root: str | None = None,
        part_id: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("draft_begin_transaction called. project_root=%s part_id=%s", project_root, part_id)
        return draft_store(project_root).begin_transaction(part_id=part_id)

    @tool(name="draft_transaction_create_box", description="Create the box or panel inside a draft transaction.")
    def draft_transaction_create_box_tool(
        transaction_token: str,
        length: float,
        width: float,
        height: float,
        project_root: str | None = None,
        part_id: str | None = None,
        material: str = "draft",
        role: str = "draft",
    ) -> dict[str, object]:
        LOGGER.info("draft_transaction_create_box called. project_root=%s transaction=%s", project_root, transaction_token)
        return draft_store(project_root).transaction_create_box(
            transaction_token,
            part_id=part_id,
            length=length,
            width=width,
            height=height,
            material=material,
            role=role,
        )

    @tool(
        name="draft_transaction_create_profile",
        description="Create an interpreted sketch profile inside a draft transaction.",
    )
    def draft_transaction_create_profile_tool(
        transaction_token: str,
        length: float,
        width: float,
        height: float,
        profile_points: list[list[float]],
        project_root: str | None = None,
        part_id: str | None = None,
        material: str = "draft",
        role: str = "draft",
    ) -> dict[str, object]:
        LOGGER.info(
            "draft_transaction_create_profile called. project_root=%s transaction=%s",
            project_root,
            transaction_token,
        )
        return draft_store(project_root).transaction_create_profile(
            transaction_token,
            part_id=part_id,
            length=length,
            width=width,
            height=height,
            profile_points=profile_points,
            material=material,
            role=role,
        )

    @tool(name="draft_transaction_set_panel_thickness", description="Set panel thickness inside a draft transaction.")
    def draft_transaction_set_panel_thickness_tool(
        transaction_token: str,
        thickness: float,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("draft_transaction_set_panel_thickness called. project_root=%s transaction=%s", project_root, transaction_token)
        return draft_store(project_root).transaction_set_panel_thickness(transaction_token, thickness=thickness)

    @tool(name="draft_transaction_add_hole", description="Add a through-hole inside a draft transaction.")
    def draft_transaction_add_hole_tool(
        transaction_token: str,
        face: str,
        x: float,
        y: float,
        diameter: float,
        through: bool = True,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("draft_transaction_add_hole called. project_root=%s transaction=%s face=%s", project_root, transaction_token, face)
        return draft_store(project_root).transaction_add_hole(
            transaction_token,
            face=face,
            x=x,
            y=y,
            diameter=diameter,
            through=through,
        )

    @tool(name="draft_transaction_add_counterbore", description="Add a counterbore inside a draft transaction.")
    def draft_transaction_add_counterbore_tool(
        transaction_token: str,
        face: str,
        x: float,
        y: float,
        diameter: float,
        depth: float,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("draft_transaction_add_counterbore called. project_root=%s transaction=%s face=%s", project_root, transaction_token, face)
        return draft_store(project_root).transaction_add_counterbore(
            transaction_token,
            face=face,
            x=x,
            y=y,
            diameter=diameter,
            depth=depth,
        )

    @tool(name="draft_transaction_add_slot", description="Add a rounded slot inside a draft transaction.")
    def draft_transaction_add_slot_tool(
        transaction_token: str,
        face: str,
        x: float,
        y: float,
        length: float,
        width: float,
        angle: float = 0.0,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("draft_transaction_add_slot called. project_root=%s transaction=%s face=%s", project_root, transaction_token, face)
        return draft_store(project_root).transaction_add_slot(
            transaction_token,
            face=face,
            x=x,
            y=y,
            length=length,
            width=width,
            angle=angle,
        )

    @tool(name="draft_transaction_add_raised_wall", description="Add a raised wall feature inside a draft transaction.")
    def draft_transaction_add_raised_wall_tool(
        transaction_token: str,
        face: str,
        x: float,
        y: float,
        length: float,
        width: float,
        height: float,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info(
            "draft_transaction_add_raised_wall called. project_root=%s transaction=%s face=%s",
            project_root,
            transaction_token,
            face,
        )
        return draft_store(project_root).transaction_add_raised_wall(
            transaction_token,
            face=face,
            x=x,
            y=y,
            length=length,
            width=width,
            height=height,
        )

    @tool(name="draft_transaction_add_louver_pattern", description="Add a louver pattern inside a draft transaction.")
    def draft_transaction_add_louver_pattern_tool(
        transaction_token: str,
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
        LOGGER.info("draft_transaction_add_louver_pattern called. project_root=%s transaction=%s face=%s", project_root, transaction_token, face)
        return draft_store(project_root).transaction_add_louver_pattern(
            transaction_token,
            face=face,
            count=count,
            pitch=pitch,
            x=x,
            y=y,
            width=width,
            height=height,
            angle=angle,
        )

    @tool(name="draft_transaction_mirror_features", description="Mirror features inside a draft transaction.")
    def draft_transaction_mirror_features_tool(
        transaction_token: str,
        source_face: str,
        target_face: str,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("draft_transaction_mirror_features called. project_root=%s transaction=%s", project_root, transaction_token)
        return draft_store(project_root).transaction_mirror_features(
            transaction_token,
            source_face=source_face,
            target_face=target_face,
        )

    @tool(name="draft_transaction_measure", description="Measure the draft part inside a transaction.")
    def draft_transaction_measure_tool(transaction_token: str, project_root: str | None = None) -> dict[str, object]:
        LOGGER.info("draft_transaction_measure called. project_root=%s transaction=%s", project_root, transaction_token)
        return draft_store(project_root).transaction_measure(transaction_token)

    @tool(name="draft_transaction_preview", description="Export a transaction STEP preview under project local state.")
    def draft_transaction_preview_tool(transaction_token: str, project_root: str | None = None) -> dict[str, object]:
        LOGGER.info("draft_transaction_preview called. project_root=%s transaction=%s", project_root, transaction_token)
        return draft_store(project_root).transaction_preview(transaction_token)

    @tool(name="draft_transaction_accept", description="Accept a transaction into reviewable source patch artifacts.")
    def draft_transaction_accept_tool(transaction_token: str, project_root: str | None = None) -> dict[str, object]:
        LOGGER.info("draft_transaction_accept called. project_root=%s transaction=%s", project_root, transaction_token)
        return draft_store(project_root).accept_transaction(transaction_token)

    @tool(name="draft_transaction_discard", description="Discard a draft transaction and local runtime artifacts.")
    def draft_transaction_discard_tool(transaction_token: str, project_root: str | None = None) -> dict[str, object]:
        LOGGER.info("draft_transaction_discard called. project_root=%s transaction=%s", project_root, transaction_token)
        return draft_store(project_root).discard_transaction(transaction_token)

    @tool(name="validator_list", description="List focused validators for a Flow CAD project.")
    def validator_list_tool(
        project_root: str | None = None,
        family: str | None = None,
        tag: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("validator_list called. project_root=%s family=%s tag=%s", project_root, family, tag)
        validators = validation_runner(project_root).list_validators(family=family, tag=tag)
        return {"ok": True, "validators": validators}

    @tool(name="validator_run", description="Run focused validators and return structured reports.")
    def validator_run_tool(
        validator_id: str | None = None,
        project_root: str | None = None,
        part_id: str | None = None,
        family: str | None = None,
        tag: str | None = None,
        draft_token: str | None = None,
        draft_transaction: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info(
            "validator_run called. project_root=%s validator_id=%s part_id=%s family=%s tag=%s",
            project_root,
            validator_id,
            part_id,
            family,
            tag,
        )
        reports, profile_payload = validation_runner(project_root).run(
            validator_id,
            part_id=part_id,
            family=family,
            tag=tag,
            draft_token=draft_token,
            draft_transaction=draft_transaction,
            command="mcp validator_run",
            profile=True,
        )
        return {
            "ok": all(report.ok for report in reports),
            "reports": [report.to_dict() for report in reports],
            "profile": profile_payload,
        }

    @tool(name="profile_last", description="Return the latest build or validator profile summary.")
    def profile_last_tool(
        project_root: str | None = None,
        limit: int = 5,
    ) -> dict[str, object]:
        LOGGER.info("profile_last called. project_root=%s", project_root)
        root = enforce_project_root(project_root)
        project = load_project(root, fallback_to_bundled=False)
        profile = load_latest_build_profile(project.paths.local_state)
        if profile is None:
            return {"ok": False, "profile": None, "summary": "No Flow CAD profile found."}
        return {
            "ok": True,
            "profile": profile,
            "summary": format_profile_summary(profile, limit=limit),
        }

    @tool(name="visual_evidence_list", description="List visual evidence artifacts for a design thread.")
    def visual_evidence_list_tool(
        thread_id: str,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("visual_evidence_list called. project_root=%s thread_id=%s", project_root, thread_id)
        thread = design_thread_service(project_root).get_thread(thread_id)
        visual_evidence = thread.get("visual_evidence", [])
        return {
            "ok": True,
            "thread_id": thread["thread_id"],
            "count": len(visual_evidence) if isinstance(visual_evidence, list) else 0,
            "visual_evidence": visual_evidence if isinstance(visual_evidence, list) else [],
        }

    @tool(name="visual_evidence_get", description="Read visual evidence metadata for a design thread artifact.")
    def visual_evidence_get_tool(
        thread_id: str,
        artifact_id: str,
        project_root: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info(
            "visual_evidence_get called. project_root=%s thread_id=%s artifact_id=%s",
            project_root,
            thread_id,
            artifact_id,
        )
        return design_thread_service(project_root).get_visual_evidence(thread_id, artifact_id)

    @tool(
        name="request_visual_evidence",
        description="Request an offscreen browser render for a design thread; the viewer fulfills it asynchronously.",
    )
    def request_visual_evidence_tool(
        thread_id: str,
        project_root: str | None = None,
        view: str = "iso",
        source: str = "agent",
        width: int | None = None,
        height: int | None = None,
        purpose: str | None = None,
        selected_ids: list[str] | None = None,
        visible_ids: list[str] | None = None,
        part_ids: list[str] | None = None,
        metadata: dict[str, object] | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info(
            "request_visual_evidence called. project_root=%s thread_id=%s source=%s view=%s",
            project_root,
            thread_id,
            source,
            view,
        )
        payload = {
            "request_id": request_id,
            "source": source,
            "view": view,
            "width": width,
            "height": height,
            "purpose": purpose,
            "selected_ids": selected_ids or [],
            "visible_ids": visible_ids or [],
            "part_ids": part_ids or [],
            "metadata": metadata or {},
        }
        return design_thread_service(project_root).request_visual_evidence(thread_id, payload)

    @tool(name="visual_evidence_requests_list", description="List render requests for a design thread.")
    def visual_evidence_requests_list_tool(
        thread_id: str,
        project_root: str | None = None,
        status: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info(
            "visual_evidence_requests_list called. project_root=%s thread_id=%s status=%s",
            project_root,
            thread_id,
            status,
        )
        return design_thread_service(project_root).list_visual_evidence_requests(thread_id, status=status)

    @tool(
        name="agent_screen_request",
        description="Request the active Flow CAD browser workbench to capture its current viewport for agent review.",
    )
    def agent_screen_request_tool(
        project_root: str | None = None,
        purpose: str | None = None,
        width: int | None = None,
        height: int | None = None,
        metadata: dict[str, object] | None = None,
        request_id: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("agent_screen_request called. project_root=%s purpose=%s", project_root, purpose)
        return agent_screen_service(project_root).request_capture(
            {
                "request_id": request_id,
                "purpose": purpose,
                "width": width,
                "height": height,
                "metadata": metadata or {},
            }
        )

    @tool(name="agent_screen_latest", description="Read metadata for the latest captured Flow CAD agent screen.")
    def agent_screen_latest_tool(project_root: str | None = None) -> dict[str, object]:
        LOGGER.info("agent_screen_latest called. project_root=%s", project_root)
        return {"ok": True, "screen": agent_screen_service(project_root).latest()}

    @tool(name="agent_screen_requests_list", description="List pending or completed Flow CAD agent screen requests.")
    def agent_screen_requests_list_tool(
        project_root: str | None = None,
        status: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info("agent_screen_requests_list called. project_root=%s status=%s", project_root, status)
        return agent_screen_service(project_root).list_requests(status=status)

    @tool(name="visual_evidence_create", description="Store a PNG visual evidence artifact for a design thread.")
    def visual_evidence_create_tool(
        thread_id: str,
        project_root: str | None = None,
        data_url: str | None = None,
        image_data: str | None = None,
        source: str = "agent",
        view: str = "iso",
        width: int | None = None,
        height: int | None = None,
        purpose: str | None = None,
        selected_ids: list[str] | None = None,
        visible_ids: list[str] | None = None,
        part_ids: list[str] | None = None,
        metadata: dict[str, object] | None = None,
        artifact_id: str | None = None,
    ) -> dict[str, object]:
        LOGGER.info(
            "visual_evidence_create called. project_root=%s thread_id=%s source=%s view=%s",
            project_root,
            thread_id,
            source,
            view,
        )
        payload = {
            "artifact_id": artifact_id,
            "source": source,
            "view": view,
            "content_type": "image/png",
            "data_url": data_url,
            "image_data": image_data,
            "width": width,
            "height": height,
            "purpose": purpose,
            "selected_ids": selected_ids or [],
            "visible_ids": visible_ids or [],
            "part_ids": part_ids or [],
            "metadata": metadata or {},
        }
        return design_thread_service(project_root).add_visual_evidence(thread_id, payload)

    LOGGER.info("Registered MCP tools: %s", ", ".join(sorted(tool_names)))
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
