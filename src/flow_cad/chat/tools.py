"""Small read-only application operations exposed to chat providers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from flow_cad.viewer.services import InventoryService


ToolHandler = Callable[[Mapping[str, object], Mapping[str, object]], Mapping[str, object]]


@dataclass(frozen=True, slots=True)
class ChatTool:
    name: str
    description: str
    input_schema: Mapping[str, object]
    handler: ToolHandler

    def provider_spec(self) -> dict[str, object]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "inputSchema": dict(self.input_schema),
        }


class ChatToolRegistry:
    """Execute only explicitly registered, bounded application operations."""

    def __init__(self, tools: tuple[ChatTool, ...]) -> None:
        by_name = {tool.name: tool for tool in tools}
        if len(by_name) != len(tools):
            raise ValueError("chat tool names must be unique")
        self._tools = by_name

    @property
    def provider_specs(self) -> list[dict[str, object]]:
        return [self._tools[name].provider_spec() for name in sorted(self._tools)]

    def execute(
        self,
        name: str,
        arguments: object,
        context: Mapping[str, object],
    ) -> Mapping[str, object]:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"unregistered Flow CAD operation: {name}")
        if not isinstance(arguments, Mapping):
            raise ValueError("tool arguments must be an object")
        return tool.handler(arguments, context)


def default_chat_tools(project_root: Path) -> ChatToolRegistry:
    """Create the first-release read-only CAD review tool surface."""

    inventory = InventoryService(project_root.resolve())

    def inspect_part(
        arguments: Mapping[str, object],
        context: Mapping[str, object],
    ) -> Mapping[str, object]:
        part = _part_by_identity(inventory, _identity(arguments, context))
        return {
            "operation": "inspect_part",
            "part": {
                key: part.get(key)
                for key in (
                    "uuid",
                    "key",
                    "aliases",
                    "family",
                    "version",
                    "role",
                    "status",
                    "material",
                    "generator",
                    "geometry_authority",
                    "quality_label",
                    "artifact_revision",
                    "display_revision",
                    "warnings",
                )
            },
        }

    def inspect_placement(
        arguments: Mapping[str, object],
        context: Mapping[str, object],
    ) -> Mapping[str, object]:
        part = _part_by_identity(inventory, _identity(arguments, context))
        return {
            "operation": "inspect_placement",
            "part_uuid": part.get("uuid"),
            "part_key": part.get("key"),
            "occurrences": part.get("occurrences", []),
        }

    def current_view(
        _arguments: Mapping[str, object],
        context: Mapping[str, object],
    ) -> Mapping[str, object]:
        return {
            "operation": "current_view",
            "selected_part_uuid": context.get("selected_part_uuid"),
            "visible_occurrence_ids": context.get("visible_occurrence_ids", []),
            "artifact_hashes": context.get("artifact_hashes", {}),
            "camera": context.get("camera", {}),
            "measurements": context.get("measurements", []),
            "annotations": context.get("annotations", []),
            "viewport_attachment": context.get("viewport_attachment"),
            "viewer_revision": context.get("viewer_revision"),
        }

    def request_build(
        arguments: Mapping[str, object],
        context: Mapping[str, object],
    ) -> Mapping[str, object]:
        part = _part_by_identity(inventory, _identity(arguments, context))
        return {
            "operation": "request_build",
            "status": "authorization_required",
            "part_uuid": part.get("uuid"),
            "part_key": part.get("key"),
            "message": (
                "The user must explicitly submit the scoped Build operation in the "
                "workbench before files or artifacts change."
            ),
        }

    identity_schema = {
        "type": "object",
        "properties": {
            "identity": {
                "type": "string",
                "description": "Part UUID, key, or alias; defaults to the selected part.",
            }
        },
        "additionalProperties": False,
    }
    empty_schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    return ChatToolRegistry(
        (
            ChatTool(
                "flow_inspect_part",
                "Inspect indexed identity, lifecycle, source, and exact/display artifact facts.",
                identity_schema,
                inspect_part,
            ),
            ChatTool(
                "flow_inspect_placement",
                "Inspect declarative assembly occurrences and transforms for one part.",
                identity_schema,
                inspect_placement,
            ),
            ChatTool(
                "flow_current_view",
                "Inspect the attached live viewport, camera, measurements, and annotations.",
                empty_schema,
                current_view,
            ),
            ChatTool(
                "flow_request_build",
                "Resolve a scoped build request without changing project or artifact state.",
                identity_schema,
                request_build,
            ),
        )
    )


def _identity(
    arguments: Mapping[str, object],
    context: Mapping[str, object],
) -> str:
    requested = arguments.get("identity")
    if isinstance(requested, str) and requested.strip():
        return requested.strip()
    selected = context.get("selected_part_uuid")
    if isinstance(selected, str) and selected.strip():
        return selected.strip()
    raise ValueError("a part identity or selected part is required")


def _part_by_identity(inventory: InventoryService, identity: str) -> Mapping[str, Any]:
    parts = inventory.inventory(include_retired=True)["parts"]
    for part in parts:
        aliases = part.get("aliases", [])
        if identity in {part.get("uuid"), part.get("key"), *aliases}:
            return part
    raise KeyError(f"part not found: {identity}")
