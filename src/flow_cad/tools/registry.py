"""Unified Tool Registry for Flow CAD.

Exposes declarative tool schemas, signatures, and execution handlers for both
the FastMCP server and the viewer's agent runtime.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

from flow_cad.draft_operations import draft_operation_payloads
from flow_cad.draft_geometry import DraftGeometryStore
from flow_cad.project import load_project
from flow_cad.profiler import format_profile_summary, load_latest_build_profile
from flow_cad.validation.runner import FocusedValidatorRunner
from flow_cad.viewer.service import ViewerService
from flow_cad.viewer.threads import DesignThreadService
from flow_cad.viewer.agent_screen import AgentScreenService

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT_ENV = "FLOW_CAD_PROJECT_ROOT"
ALLOWED_PROJECT_ROOTS_ENV = "FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS"

_DRAFT_STORES: dict[Path, DraftGeometryStore] = {}


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


class ToolRegistry:
    """Registry to keep track of unified CAD tools and their functions."""

    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}

    def register(self, name: str | None = None) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator to register a tool function in the unified registry."""
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            tool_name = name or func.__name__
            self._tools[tool_name] = {
                "func": func,
                "name": tool_name,
                "description": func.__doc__ or f"Run {tool_name}.",
            }
            return func
        return decorator

    def get_tool(self, name: str) -> dict[str, Any] | None:
        """Retrieve tool metadata by name."""
        return self._tools.get(name)

    def get_tools(self) -> dict[str, dict[str, Any]]:
        """Retrieve all registered tools."""
        return self._tools

    def execute(self, name: str, **kwargs: Any) -> Any:
        """Execute a registered tool handler by name."""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"Tool {name} is not registered in ToolRegistry.")
        return tool["func"](**kwargs)

    def get_schemas(self, names: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """Generate OpenAI/Gemini/Codex compatible tool schemas dynamically."""
        import inspect
        import typing

        schemas = []
        type_map = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object",
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }

        filter_names = set(names) if names is not None else None

        for tool_name, tool_data in self.get_tools().items():
            if filter_names is not None and tool_name not in filter_names:
                continue

            func = tool_data["func"]
            sig = inspect.signature(func)
            try:
                hints = typing.get_type_hints(func)
            except Exception:
                hints = {}
            properties = {}
            required = []

            for param_name, param in sig.parameters.items():
                if param_name in ("project_root", "context"):
                    continue

                annotation = hints.get(param_name, param.annotation)
                param_type = "string"  # fallback

                annotation_str = str(annotation)
                if "Union" in annotation_str or "|" in annotation_str:
                    if "float" in annotation_str:
                        param_type = "number"
                    elif "int" in annotation_str:
                        param_type = "integer"
                    elif "bool" in annotation_str:
                        param_type = "boolean"
                    elif "list" in annotation_str:
                        param_type = "array"
                    elif "dict" in annotation_str:
                        param_type = "object"
                    elif "str" in annotation_str:
                        param_type = "string"
                elif annotation in type_map:
                    param_type = type_map[annotation]
                elif annotation_str in type_map:
                    param_type = type_map[annotation_str]
                elif hasattr(annotation, "__origin__") and annotation.__origin__ in (list, dict):
                    param_type = "array" if annotation.__origin__ is list else "object"

                properties[param_name] = {"type": param_type}
                if param.default is inspect.Parameter.empty:
                    required.append(param_name)

            schemas.append({
                "name": tool_name,
                "description": tool_data["description"],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                }
            })
        return schemas


registry = ToolRegistry()


@registry.register(name="draft_create_box")
def draft_create_box_tool(
    length: float,
    width: float,
    height: float,
    project_root: str | None = None,
    part_id: str | None = None,
    material: str = "draft",
    role: str = "draft",
) -> dict[str, object]:
    """Create a draft-only rectangular box or panel."""
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


@registry.register(name="draft_create_profile")
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
    """Create a draft-only interpreted sketch profile."""
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


@registry.register(name="draft_set_panel_thickness")
def draft_set_panel_thickness_tool(
    draft_token: str,
    thickness: float,
    project_root: str | None = None,
) -> dict[str, object]:
    """Adjust a draft panel thickness."""
    LOGGER.info("draft_set_panel_thickness called. project_root=%s draft_token=%s", project_root, draft_token)
    return draft_store(project_root).set_panel_thickness(draft_token, thickness=thickness)


@registry.register(name="draft_add_hole")
def draft_add_hole_tool(
    draft_token: str,
    face: str,
    x: float,
    y: float,
    diameter: float,
    through: bool = True,
    project_root: str | None = None,
) -> dict[str, object]:
    """Add a draft through-hole to a selected face."""
    LOGGER.info("draft_add_hole called. project_root=%s draft_token=%s face=%s", project_root, draft_token, face)
    return draft_store(project_root).add_hole(
        draft_token,
        face=face,
        x=x,
        y=y,
        diameter=diameter,
        through=through,
    )


@registry.register(name="draft_add_counterbore")
def draft_add_counterbore_tool(
    draft_token: str,
    face: str,
    x: float,
    y: float,
    diameter: float,
    depth: float,
    project_root: str | None = None,
) -> dict[str, object]:
    """Add a basic draft counterbore pocket to a selected face."""
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


@registry.register(name="draft_add_slot")
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
    """Add a draft rounded slot to a selected face."""
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


@registry.register(name="draft_add_raised_wall")
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
    """Add a raised wall feature to a selected draft face."""
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


@registry.register(name="draft_add_louver_pattern")
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
    """Add a draft louver pattern as repeated rounded slots."""
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


@registry.register(name="draft_mirror_features")
def draft_mirror_features_tool(
    draft_token: str,
    source_face: str,
    target_face: str,
    project_root: str | None = None,
) -> dict[str, object]:
    """Mirror draft features to the opposing parallel face."""
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


@registry.register(name="draft_measure")
def draft_measure_tool(draft_token: str, project_root: str | None = None) -> dict[str, object]:
    """Measure a draft part and return structured geometry facts."""
    LOGGER.info("draft_measure called. project_root=%s draft_token=%s", project_root, draft_token)
    return draft_store(project_root).measure_part(draft_token)


@registry.register(name="draft_export_step")
def draft_export_step_tool(draft_token: str, project_root: str | None = None) -> dict[str, object]:
    """Export a draft-only STEP preview under project local state."""
    LOGGER.info("draft_export_step called. project_root=%s draft_token=%s", project_root, draft_token)
    return draft_store(project_root).export_draft_step(draft_token)


@registry.register(name="draft_discard")
def draft_discard_tool(draft_token: str, project_root: str | None = None) -> dict[str, object]:
    """Discard a draft token and remove its local runtime artifacts."""
    LOGGER.info("draft_discard called. project_root=%s draft_token=%s", project_root, draft_token)
    return draft_store(project_root).discard(draft_token)


@registry.register(name="draft_operation_registry")
def draft_operation_registry_tool() -> dict[str, object]:
    """Return registered draft operations for tool discovery."""
    operations = draft_operation_payloads()
    return {
        "ok": True,
        "operations": operations,
        "count": len(operations),
        "source": "flow_cad.draft_operations",
    }


@registry.register(name="draft_begin_transaction")
def draft_begin_transaction_tool(
    project_root: str | None = None,
    part_id: str | None = None,
) -> dict[str, object]:
    """Begin a draft geometry transaction."""
    LOGGER.info("draft_begin_transaction called. project_root=%s part_id=%s", project_root, part_id)
    return draft_store(project_root).begin_transaction(part_id=part_id)


@registry.register(name="draft_transaction_create_box")
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
    """Create the box or panel inside a draft transaction."""
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


@registry.register(name="draft_transaction_create_profile")
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
    """Create an interpreted sketch profile inside a draft transaction."""
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


@registry.register(name="draft_transaction_set_panel_thickness")
def draft_transaction_set_panel_thickness_tool(
    transaction_token: str,
    thickness: float,
    project_root: str | None = None,
) -> dict[str, object]:
    """Set panel thickness inside a draft transaction."""
    LOGGER.info("draft_transaction_set_panel_thickness called. project_root=%s transaction=%s", project_root, transaction_token)
    return draft_store(project_root).transaction_set_panel_thickness(transaction_token, thickness=thickness)


@registry.register(name="draft_transaction_add_hole")
def draft_transaction_add_hole_tool(
    transaction_token: str,
    face: str,
    x: float,
    y: float,
    diameter: float,
    through: bool = True,
    project_root: str | None = None,
) -> dict[str, object]:
    """Add a through-hole inside a draft transaction."""
    LOGGER.info("draft_transaction_add_hole called. project_root=%s transaction=%s face=%s", project_root, transaction_token, face)
    return draft_store(project_root).transaction_add_hole(
        transaction_token,
        face=face,
        x=x,
        y=y,
        diameter=diameter,
        through=through,
    )


@registry.register(name="draft_transaction_add_counterbore")
def draft_transaction_add_counterbore_tool(
    transaction_token: str,
    face: str,
    x: float,
    y: float,
    diameter: float,
    depth: float,
    project_root: str | None = None,
) -> dict[str, object]:
    """Add a counterbore inside a draft transaction."""
    LOGGER.info("draft_transaction_add_counterbore called. project_root=%s transaction=%s face=%s", project_root, transaction_token, face)
    return draft_store(project_root).transaction_add_counterbore(
        transaction_token,
        face=face,
        x=x,
        y=y,
        diameter=diameter,
        depth=depth,
    )


@registry.register(name="draft_transaction_add_slot")
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
    """Add a rounded slot inside a draft transaction."""
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


@registry.register(name="draft_transaction_add_raised_wall")
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
    """Add a raised wall feature inside a draft transaction."""
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


@registry.register(name="draft_transaction_add_louver_pattern")
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
    """Add a louver pattern inside a draft transaction."""
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


@registry.register(name="draft_transaction_mirror_features")
def draft_transaction_mirror_features_tool(
    transaction_token: str,
    source_face: str,
    target_face: str,
    project_root: str | None = None,
) -> dict[str, object]:
    """Mirror features inside a draft transaction."""
    LOGGER.info("draft_transaction_mirror_features called. project_root=%s transaction=%s", project_root, transaction_token)
    return draft_store(project_root).transaction_mirror_features(
        transaction_token,
        source_face=source_face,
        target_face=target_face,
    )


@registry.register(name="draft_transaction_measure")
def draft_transaction_measure_tool(transaction_token: str, project_root: str | None = None) -> dict[str, object]:
    """Measure the draft part inside a transaction."""
    LOGGER.info("draft_transaction_measure called. project_root=%s transaction=%s", project_root, transaction_token)
    return draft_store(project_root).transaction_measure(transaction_token)


@registry.register(name="draft_transaction_preview")
def draft_transaction_preview_tool(transaction_token: str, project_root: str | None = None) -> dict[str, object]:
    """Export a transaction STEP preview under project local state."""
    LOGGER.info("draft_transaction_preview called. project_root=%s transaction=%s", project_root, transaction_token)
    return draft_store(project_root).transaction_preview(transaction_token)


@registry.register(name="draft_transaction_accept")
def draft_transaction_accept_tool(transaction_token: str, project_root: str | None = None) -> dict[str, object]:
    """Accept a transaction into reviewable source patch artifacts."""
    LOGGER.info("draft_transaction_accept called. project_root=%s transaction=%s", project_root, transaction_token)
    return draft_store(project_root).accept_transaction(transaction_token)


@registry.register(name="draft_transaction_discard")
def draft_transaction_discard_tool(transaction_token: str, project_root: str | None = None) -> dict[str, object]:
    """Discard a draft transaction and local runtime artifacts."""
    LOGGER.info("draft_transaction_discard called. project_root=%s transaction=%s", project_root, transaction_token)
    return draft_store(project_root).discard_transaction(transaction_token)


@registry.register(name="validator_list")
def validator_list_tool(
    project_root: str | None = None,
    family: str | None = None,
    tag: str | None = None,
) -> dict[str, object]:
    """List focused validators for a Flow CAD project."""
    LOGGER.info("validator_list called. project_root=%s family=%s tag=%s", project_root, family, tag)
    validators = validation_runner(project_root).list_validators(family=family, tag=tag)
    return {"ok": True, "validators": validators}


@registry.register(name="validator_run")
def validator_run_tool(
    validator_id: str | None = None,
    project_root: str | None = None,
    part_id: str | None = None,
    family: str | None = None,
    tag: str | None = None,
    draft_token: str | None = None,
    draft_transaction: str | None = None,
) -> dict[str, object]:
    """Run focused validators and return structured reports."""
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


@registry.register(name="profile_last")
def profile_last_tool(
    project_root: str | None = None,
    limit: int = 5,
) -> dict[str, object]:
    """Return the latest build or validator profile summary."""
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


@registry.register(name="visual_evidence_list")
def visual_evidence_list_tool(
    thread_id: str,
    project_root: str | None = None,
) -> dict[str, object]:
    """List visual evidence artifacts for a design thread."""
    LOGGER.info("visual_evidence_list called. project_root=%s thread_id=%s", project_root, thread_id)
    thread = design_thread_service(project_root).get_thread(thread_id)
    visual_evidence = thread.get("visual_evidence", [])
    return {
        "ok": True,
        "thread_id": thread["thread_id"],
        "count": len(visual_evidence) if isinstance(visual_evidence, list) else 0,
        "visual_evidence": visual_evidence if isinstance(visual_evidence, list) else [],
    }


@registry.register(name="visual_evidence_get")
def visual_evidence_get_tool(
    thread_id: str,
    artifact_id: str,
    project_root: str | None = None,
) -> dict[str, object]:
    """Read visual evidence metadata for a design thread artifact."""
    LOGGER.info(
        "visual_evidence_get called. project_root=%s thread_id=%s artifact_id=%s",
        project_root,
        thread_id,
        artifact_id,
    )
    return design_thread_service(project_root).get_visual_evidence(thread_id, artifact_id)


@registry.register(name="request_visual_evidence")
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
    """Request an offscreen browser render for a design thread; the viewer fulfills it asynchronously."""
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


@registry.register(name="visual_evidence_requests_list")
def visual_evidence_requests_list_tool(
    thread_id: str,
    project_root: str | None = None,
    status: str | None = None,
) -> dict[str, object]:
    """List render requests for a design thread."""
    LOGGER.info(
        "visual_evidence_requests_list called. project_root=%s thread_id=%s status=%s",
        project_root,
        thread_id,
        status,
    )
    return design_thread_service(project_root).list_visual_evidence_requests(thread_id, status=status)


@registry.register(name="visual_evidence_create")
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
    """Store a PNG visual evidence artifact for a design thread."""
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


@registry.register(name="agent_screen_request")
def agent_screen_request_tool(
    project_root: str | None = None,
    purpose: str | None = None,
    width: int | None = None,
    height: int | None = None,
    metadata: dict[str, object] | None = None,
    request_id: str | None = None,
) -> dict[str, object]:
    """Request the active Flow CAD browser workbench to capture its current viewport for agent review."""
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


@registry.register(name="agent_screen_latest")
def agent_screen_latest_tool(project_root: str | None = None) -> dict[str, object]:
    """Read metadata for the latest captured Flow CAD agent screen."""
    LOGGER.info("agent_screen_latest called. project_root=%s", project_root)
    return {"ok": True, "screen": agent_screen_service(project_root).latest()}


@registry.register(name="agent_screen_requests_list")
def agent_screen_requests_list_tool(
    project_root: str | None = None,
    status: str | None = None,
) -> dict[str, object]:
    """List pending or completed Flow CAD agent screen requests."""
    LOGGER.info("agent_screen_requests_list called. project_root=%s status=%s", project_root, status)
    return agent_screen_service(project_root).list_requests(status=status)


# --- Legacy Tool Wrappers for Compatibility ---

@registry.register(name="read_viewer_context")
def read_viewer_context_tool(
    thread_id: str,
    project_root: str | None = None,
) -> dict[str, object]:
    """Read the active Flow CAD design-thread and viewport context."""
    LOGGER.info("read_viewer_context called. thread_id=%s", thread_id)
    service = design_thread_service(project_root)
    thread = service.get_thread(thread_id)
    return {
        "ok": True,
        "thread_id": thread_id,
        "thread": thread,
    }


@registry.register(name="create_draft_transaction")
def create_draft_transaction_tool(
    part_id: str | None = None,
    project_root: str | None = None,
) -> dict[str, object]:
    """Create a draft transaction for a registered CAD part."""
    LOGGER.info("create_draft_transaction called. part_id=%s", part_id)
    return draft_begin_transaction_tool(project_root=project_root, part_id=part_id)


@registry.register(name="apply_draft_operations")
def apply_draft_operations_tool(
    transaction_token: str,
    operations: list[dict[str, Any]],
    project_root: str | None = None,
) -> dict[str, object]:
    """Apply explicit Flow CAD draft operations to a draft transaction."""
    LOGGER.info("apply_draft_operations called. transaction=%s ops=%s", transaction_token, len(operations))
    applied = []
    for op in operations:
        op_name = op.get("name")
        op_params = op.get("parameters", {})
        reg_op_name = f"draft_transaction_{op_name}"
        op_kwargs = dict(op_params)
        op_kwargs["transaction_token"] = transaction_token
        op_kwargs["project_root"] = project_root
        res = registry.execute(reg_op_name, **op_kwargs)
        applied.append({
            "name": op_name,
            "parameters": op_params,
            "result": res,
        })
    return {
        "ok": True,
        "transaction_token": transaction_token,
        "applied_operations": applied,
    }


@registry.register(name="generate_preview_model")
def generate_preview_model_tool(
    transaction_token: str,
    project_root: str | None = None,
) -> dict[str, object]:
    """Generate a reviewable draft preview model."""
    LOGGER.info("generate_preview_model called. transaction=%s", transaction_token)
    return draft_transaction_preview_tool(transaction_token=transaction_token, project_root=project_root)


@registry.register(name="run_focused_validator")
def run_focused_validator_tool(
    validator_id: str,
    transaction_token: str,
    project_root: str | None = None,
) -> dict[str, object]:
    """Run a focused Flow CAD validator against explicit draft or project context."""
    LOGGER.info("run_focused_validator called. validator=%s transaction=%s", validator_id, transaction_token)
    return validator_run_tool(
        validator_id=validator_id,
        draft_transaction=transaction_token,
        project_root=project_root,
    )


@registry.register(name="read_profile_summary")
def read_profile_summary_tool(
    profile_id: str | None = None,
    project_root: str | None = None,
) -> dict[str, object]:
    """Read an existing Flow CAD profile summary."""
    LOGGER.info("read_profile_summary called. profile_id=%s", profile_id)
    return profile_last_tool(project_root=project_root)


@registry.register(name="summarize_acceptance_artifacts")
def summarize_acceptance_artifacts_tool(
    transaction_token: str,
    project_root: str | None = None,
) -> dict[str, object]:
    """Summarize review artifacts created by accepted draft transactions."""
    LOGGER.info("summarize_acceptance_artifacts called. transaction=%s", transaction_token)
    import json
    root = enforce_project_root(project_root)
    manifest_path = root / ".flow" / "drafts" / transaction_token / "acceptance.json"
    if not manifest_path.exists():
        return {
            "ok": False,
            "error": f"Acceptance manifest not found for token {transaction_token}",
        }
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return {
            "ok": True,
            "transaction_token": transaction_token,
            "manifest": data,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": f"Failed to read acceptance manifest: {exc}",
        }
