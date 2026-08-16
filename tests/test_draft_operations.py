from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

from flow_cad import draft_operations


def test_draft_operation_registry_ids_are_unique() -> None:
    operations = draft_operations.draft_operation_registry()

    ids = [operation.operation_id for operation in operations]
    assert len(ids) == len(set(ids))
    assert len(operations) == 14


def test_draft_operation_registry_includes_required_operations() -> None:
    required_operation_ids = {
        "create_box",
        "create_sketch_profile",
        "set_panel_thickness",
        "add_hole",
        "add_counterbore",
        "add_slot",
        "add_raised_wall",
        "add_louver_pattern",
        "mirror_features",
        "measure",
        "export_step",
        "preview",
        "accept",
        "discard",
    }

    operation_ids = {operation.operation_id for operation in draft_operations.draft_operation_registry()}
    assert required_operation_ids <= operation_ids


def test_draft_operation_payload_shape_and_json_safety() -> None:
    payloads = draft_operations.draft_operation_payloads()
    serialized = json.dumps(payloads, sort_keys=True)
    assert serialized
    payload_keys = {
        "id",
        "title",
        "summary",
        "category",
        "parameter_schema",
        "execution_scopes",
        "feature_kind",
        "endpoint_slug",
        "mcp_tool_names",
        "direct_tool_name",
        "transaction_tool_name",
        "supports_preview",
        "supports_source_emission",
        "authority_level",
        "human_review_posture",
    }

    for payload in payloads:
        assert set(payload_keys) <= set(payload)
        assert isinstance(payload["id"], str) and payload["id"]
        assert isinstance(payload["title"], str) and payload["title"]
        assert isinstance(payload["summary"], str) and payload["summary"]
        assert isinstance(payload["category"], str)
        assert isinstance(payload["parameter_schema"], dict)
        assert isinstance(payload["execution_scopes"], list)
        assert set(payload["execution_scopes"]).issubset({"direct", "transaction", "mcp", "planner", "preview_command"})
        assert isinstance(payload["mcp_tool_names"], dict)
        assert set(payload["mcp_tool_names"]) == {"direct", "transaction"}
        for value in payload["mcp_tool_names"].values():
            assert value is None or isinstance(value, str)
        assert isinstance(payload["supports_preview"], bool)
        assert isinstance(payload["supports_source_emission"], bool)
        assert payload["authority_level"] in {"draft_read", "draft_write", "review_artifact"}
        assert payload["human_review_posture"] in {"not_required", "required"}


def test_add_raised_wall_metadata() -> None:
    operation = draft_operations.get_draft_operation("add_raised_wall")
    assert operation is not None

    payload = operation.to_payload()
    assert payload["title"] == "Add raised wall"
    assert payload["summary"] == "Add a raised wall feature as positive relief on a draft face."
    assert payload["feature_kind"] == "raised_wall"
    assert payload["endpoint_slug"] == "raised-walls"
    assert payload["execution_scopes"] == ["direct", "transaction", "mcp", "planner"]
    assert payload["mcp_tool_names"]["transaction"] == "draft_transaction_add_raised_wall"
    assert payload["mcp_tool_names"]["direct"] == "draft_add_raised_wall"
    assert payload["direct_tool_name"] == "draft_add_raised_wall"
    assert payload["transaction_tool_name"] == "draft_transaction_add_raised_wall"
    assert payload["supports_source_emission"] is True
    assert payload["supports_preview"] is True
    assert payload["human_review_posture"] == "not_required"

    schema = payload["parameter_schema"]
    assert schema["required"] == ["face", "x", "y", "length", "width", "height"]
    for field in ("face", "x", "y", "length", "width", "height"):
        assert field in schema["properties"]


def test_draft_operations_import_has_no_filesystem_side_effects(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    before = {path.name for path in Path(tmp_path).iterdir()}

    module_name = "flow_cad.draft_operations"
    cached_module = sys.modules.pop(module_name, None)
    try:
        module = importlib.import_module(module_name)
        module.draft_operation_payloads()
    finally:
        if cached_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = cached_module

    after = {path.name for path in Path(tmp_path).iterdir()}
    assert after == before
    assert (tmp_path / ".flow").exists() is False
    assert (tmp_path / "exports").exists() is False
    assert (tmp_path / "flow").exists() is False
