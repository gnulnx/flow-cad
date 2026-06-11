from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


OperationScope = Literal["direct", "transaction", "mcp", "planner", "preview_command"]
AuthorityLevel = Literal["draft_read", "draft_write", "review_artifact"]
HumanReviewPosture = Literal["not_required", "required"]


def _schema(properties: dict[str, Any], *, required: list[str], additional_properties: bool = True) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": additional_properties,
    }


@dataclass(frozen=True)
class DraftOperationDescriptor:
    operation_id: str
    title: str
    summary: str
    category: str
    parameter_schema: dict[str, Any]
    execution_scopes: tuple[OperationScope, ...]
    feature_kind: str | None
    endpoint_slug: str
    mcp_tool_names: dict[str, str | None]
    supports_preview: bool
    supports_source_emission: bool
    authority_level: AuthorityLevel
    human_review_posture: HumanReviewPosture

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.operation_id,
            "operation_id": self.operation_id,
            "title": self.title,
            "summary": self.summary,
            "category": self.category,
            "parameter_schema": self.parameter_schema,
            "execution_scopes": list(self.execution_scopes),
            "feature_kind": self.feature_kind,
            "endpoint_slug": self.endpoint_slug,
            "direct_tool_name": self.mcp_tool_names.get("direct"),
            "transaction_tool_name": self.mcp_tool_names.get("transaction"),
            "mcp_tool_names": dict(self.mcp_tool_names),
            "supports_preview": self.supports_preview,
            "supports_source_emission": self.supports_source_emission,
            "authority_level": self.authority_level,
            "human_review_posture": self.human_review_posture,
        }


def draft_operation_registry() -> tuple[DraftOperationDescriptor, ...]:
    return tuple(_DRAFT_OPERATIONS)


def draft_operation_payloads() -> list[dict[str, Any]]:
    return [operation.to_payload() for operation in draft_operation_registry()]


def get_draft_operation(operation_id: str) -> DraftOperationDescriptor | None:
    for operation in draft_operation_registry():
        if operation.operation_id == operation_id:
            return operation
    return None


_DRAFT_OPERATIONS: tuple[DraftOperationDescriptor, ...] = (
    DraftOperationDescriptor(
        operation_id="create_box",
        title="Create draft base box",
        summary="Create a fresh draft box (panel) as the base geometry for subsequent draft edits.",
        category="draft_mutation",
        parameter_schema=_schema(
            {
                "length": {"type": "number", "minimum": 0.0},
                "width": {"type": "number", "minimum": 0.0},
                "height": {"type": "number", "minimum": 0.0},
                "part_id": {"type": "string"},
                "material": {"type": "string"},
                "role": {"type": "string"},
            },
            required=["length", "width", "height"],
        ),
        execution_scopes=("direct", "transaction", "mcp", "planner", "preview_command"),
        feature_kind=None,
        endpoint_slug="box",
        mcp_tool_names={
            "direct": "draft_create_box",
            "transaction": "draft_transaction_create_box",
        },
        supports_preview=True,
        supports_source_emission=True,
        authority_level="draft_write",
        human_review_posture="not_required",
    ),
    DraftOperationDescriptor(
        operation_id="create_sketch_profile",
        title="Create interpreted sketch profile",
        summary="Create a fresh draft base by extruding a cleaned sketch-intent footprint profile.",
        category="draft_mutation",
        parameter_schema=_schema(
            {
                "length": {"type": "number", "minimum": 0.0},
                "width": {"type": "number", "minimum": 0.0},
                "height": {"type": "number", "minimum": 0.0},
                "profile_points": {
                    "type": "array",
                    "items": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                    },
                    "minItems": 3,
                },
                "part_id": {"type": "string"},
                "material": {"type": "string"},
                "role": {"type": "string"},
            },
            required=["length", "width", "height", "profile_points"],
        ),
        execution_scopes=("direct", "transaction", "mcp", "planner"),
        feature_kind=None,
        endpoint_slug="profile",
        mcp_tool_names={
            "direct": "draft_create_profile",
            "transaction": "draft_transaction_create_profile",
        },
        supports_preview=True,
        supports_source_emission=True,
        authority_level="draft_write",
        human_review_posture="not_required",
    ),
    DraftOperationDescriptor(
        operation_id="set_panel_thickness",
        title="Set draft panel thickness",
        summary="Update the panel height/thickness of an active draft part.",
        category="draft_mutation",
        parameter_schema=_schema(
            {
                "thickness": {"type": "number", "minimum": 0.0},
            },
            required=["thickness"],
        ),
        execution_scopes=("direct", "transaction", "mcp", "planner", "preview_command"),
        feature_kind=None,
        endpoint_slug="thickness",
        mcp_tool_names={
            "direct": "draft_set_panel_thickness",
            "transaction": "draft_transaction_set_panel_thickness",
        },
        supports_preview=True,
        supports_source_emission=True,
        authority_level="draft_write",
        human_review_posture="not_required",
    ),
    DraftOperationDescriptor(
        operation_id="add_hole",
        title="Add draft hole",
        summary="Add a round through-hole on a draft face.",
        category="draft_feature",
        parameter_schema=_schema(
            {
                "face": {"type": "string"},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "diameter": {"type": "number", "minimum": 0.0},
                "through": {"type": "boolean"},
            },
            required=["face", "x", "y", "diameter"],
        ),
        execution_scopes=("direct", "transaction", "mcp", "planner", "preview_command"),
        feature_kind="hole",
        endpoint_slug="holes",
        mcp_tool_names={
            "direct": "draft_add_hole",
            "transaction": "draft_transaction_add_hole",
        },
        supports_preview=True,
        supports_source_emission=True,
        authority_level="draft_write",
        human_review_posture="not_required",
    ),
    DraftOperationDescriptor(
        operation_id="add_counterbore",
        title="Add draft counterbore",
        summary="Add a draft counterbore pocket on a target face.",
        category="draft_feature",
        parameter_schema=_schema(
            {
                "face": {"type": "string"},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "diameter": {"type": "number", "minimum": 0.0},
                "depth": {"type": "number", "minimum": 0.0},
            },
            required=["face", "x", "y", "diameter", "depth"],
        ),
        execution_scopes=("direct", "transaction", "mcp", "planner", "preview_command"),
        feature_kind="counterbore",
        endpoint_slug="counterbores",
        mcp_tool_names={
            "direct": "draft_add_counterbore",
            "transaction": "draft_transaction_add_counterbore",
        },
        supports_preview=True,
        supports_source_emission=True,
        authority_level="draft_write",
        human_review_posture="not_required",
    ),
    DraftOperationDescriptor(
        operation_id="add_slot",
        title="Add draft slot",
        summary="Add a rounded slot on a target face.",
        category="draft_feature",
        parameter_schema=_schema(
            {
                "face": {"type": "string"},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "length": {"type": "number", "minimum": 0.0},
                "width": {"type": "number", "minimum": 0.0},
                "angle": {"type": "number"},
            },
            required=["face", "x", "y", "length", "width"],
        ),
        execution_scopes=("direct", "transaction", "mcp", "planner", "preview_command"),
        feature_kind="slot",
        endpoint_slug="slots",
        mcp_tool_names={
            "direct": "draft_add_slot",
            "transaction": "draft_transaction_add_slot",
        },
        supports_preview=True,
        supports_source_emission=True,
        authority_level="draft_write",
        human_review_posture="not_required",
    ),
    DraftOperationDescriptor(
        operation_id="add_raised_wall",
        title="Add raised wall",
        summary="Add a raised wall feature as positive relief on a draft face.",
        category="draft_feature",
        parameter_schema=_schema(
            {
                "face": {"type": "string"},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "length": {"type": "number", "minimum": 0.0},
                "width": {"type": "number", "minimum": 0.0},
                "height": {"type": "number", "minimum": 0.0},
            },
            required=["face", "x", "y", "length", "width", "height"],
        ),
        execution_scopes=("direct", "transaction", "mcp", "planner"),
        feature_kind="raised_wall",
        endpoint_slug="raised-walls",
        mcp_tool_names={
            "direct": "draft_add_raised_wall",
            "transaction": "draft_transaction_add_raised_wall",
        },
        supports_preview=True,
        supports_source_emission=True,
        authority_level="draft_write",
        human_review_posture="not_required",
    ),
    DraftOperationDescriptor(
        operation_id="add_louver_pattern",
        title="Add draft louver pattern",
        summary="Add a repeated rounded slot pattern (louver feature bank).",
        category="draft_feature",
        parameter_schema=_schema(
            {
                "face": {"type": "string"},
                "count": {"type": "integer", "minimum": 1},
                "pitch": {"type": "number", "minimum": 0.0},
                "x": {"type": "number"},
                "y": {"type": "number"},
                "width": {"type": "number", "minimum": 0.0},
                "height": {"type": "number", "minimum": 0.0},
                "angle": {"type": "number"},
            },
            required=["face", "count", "pitch", "x", "y", "width", "height"],
        ),
        execution_scopes=("direct", "transaction", "mcp", "planner", "preview_command"),
        feature_kind="slot",
        endpoint_slug="louver-patterns",
        mcp_tool_names={
            "direct": "draft_add_louver_pattern",
            "transaction": "draft_transaction_add_louver_pattern",
        },
        supports_preview=True,
        supports_source_emission=True,
        authority_level="draft_write",
        human_review_posture="not_required",
    ),
    DraftOperationDescriptor(
        operation_id="mirror_features",
        title="Mirror draft features",
        summary="Mirror existing draft features from one face to its opposite.",
        category="draft_feature",
        parameter_schema=_schema(
            {
                "source_face": {"type": "string"},
                "target_face": {"type": "string"},
            },
            required=["source_face", "target_face"],
        ),
        execution_scopes=("direct", "transaction", "mcp", "planner", "preview_command"),
        feature_kind=None,
        endpoint_slug="mirror-features",
        mcp_tool_names={
            "direct": "draft_mirror_features",
            "transaction": "draft_transaction_mirror_features",
        },
        supports_preview=True,
        supports_source_emission=True,
        authority_level="draft_write",
        human_review_posture="not_required",
    ),
    DraftOperationDescriptor(
        operation_id="measure",
        title="Measure draft geometry",
        summary="Read measured facts for the active draft token or transaction draft.",
        category="draft_inspection",
        parameter_schema={
            "type": "object",
            "oneOf": [
                {"required": ["draft_token"]},
                {"required": ["transaction_token"]},
            ],
            "properties": {
                "draft_token": {"type": "string"},
                "transaction_token": {"type": "string"},
            },
            "additionalProperties": False,
        },
        execution_scopes=("direct", "transaction", "mcp", "planner"),
        feature_kind=None,
        endpoint_slug="measure",
        mcp_tool_names={
            "direct": "draft_measure",
            "transaction": "draft_transaction_measure",
        },
        supports_preview=False,
        supports_source_emission=False,
        authority_level="draft_read",
        human_review_posture="not_required",
    ),
    DraftOperationDescriptor(
        operation_id="export_step",
        title="Export draft STEP preview",
        summary="Emit a draft STEP artifact for the current draft geometry.",
        category="draft_workflow",
        parameter_schema=_schema(
            {
                "draft_token": {"type": "string"},
                "transaction_token": {"type": "string"},
            },
            required=["draft_token"],
            additional_properties=False,
        ),
        execution_scopes=("direct", "mcp"),
        feature_kind=None,
        endpoint_slug="export",
        mcp_tool_names={
            "direct": "draft_export_step",
            "transaction": None,
        },
        supports_preview=True,
        supports_source_emission=False,
        authority_level="draft_write",
        human_review_posture="not_required",
    ),
    DraftOperationDescriptor(
        operation_id="preview",
        title="Generate draft preview",
        summary="Export a transaction draft STEP and prepare preview metadata.",
        category="draft_workflow",
        parameter_schema=_schema(
            {
                "transaction_token": {"type": "string"},
            },
            required=["transaction_token"],
            additional_properties=False,
        ),
        execution_scopes=("transaction", "mcp", "planner"),
        feature_kind=None,
        endpoint_slug="preview",
        mcp_tool_names={
            "direct": None,
            "transaction": "draft_transaction_preview",
        },
        supports_preview=True,
        supports_source_emission=False,
        authority_level="draft_write",
        human_review_posture="not_required",
    ),
    DraftOperationDescriptor(
        operation_id="accept",
        title="Accept transaction",
        summary="Convert transaction draft results into reviewable source artifacts.",
        category="draft_workflow",
        parameter_schema=_schema(
            {
                "transaction_token": {"type": "string"},
            },
            required=["transaction_token"],
            additional_properties=False,
        ),
        execution_scopes=("transaction", "mcp", "planner"),
        feature_kind=None,
        endpoint_slug="accept",
        mcp_tool_names={
            "direct": None,
            "transaction": "draft_transaction_accept",
        },
        supports_preview=True,
        supports_source_emission=True,
        authority_level="review_artifact",
        human_review_posture="required",
    ),
    DraftOperationDescriptor(
        operation_id="discard",
        title="Discard draft",
        summary="Discard the active draft or draft transaction and remove temporary runtime artifacts.",
        category="draft_workflow",
        parameter_schema={
            "type": "object",
            "oneOf": [
                {"required": ["draft_token"]},
                {"required": ["transaction_token"]},
            ],
            "properties": {
                "draft_token": {"type": "string"},
                "transaction_token": {"type": "string"},
            },
            "additionalProperties": False,
        },
        execution_scopes=("direct", "transaction", "mcp", "planner"),
        feature_kind=None,
        endpoint_slug="discard",
        mcp_tool_names={
            "direct": "draft_discard",
            "transaction": "draft_transaction_discard",
        },
        supports_preview=False,
        supports_source_emission=False,
        authority_level="draft_write",
        human_review_posture="not_required",
    ),
)
