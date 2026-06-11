"""Tests for the unified tool registry."""

from __future__ import annotations

import pytest

from flow_cad.tools.registry import registry


def test_tool_registry_contains_registered_tools() -> None:
    tools = registry.get_tools()
    assert len(tools) > 0
    assert "draft_create_box" in tools
    assert "draft_begin_transaction" in tools
    assert "draft_operation_registry" in tools
    assert "validator_run" in tools
    assert "request_visual_evidence" in tools


def test_tool_registry_get_tool() -> None:
    tool = registry.get_tool("draft_create_box")
    assert tool is not None
    assert tool["name"] == "draft_create_box"
    assert "Create a draft-only rectangular box" in tool["description"]


def test_tool_registry_execute() -> None:
    result = registry.execute("draft_operation_registry")
    assert isinstance(result, dict)
    assert result.get("ok") is True
    assert "operations" in result
    assert result.get("count", 0) > 0


def test_tool_registry_execute_invalid_name() -> None:
    with pytest.raises(ValueError, match="is not registered in ToolRegistry"):
        registry.execute("non_existent_tool_name")


def test_tool_registry_get_schemas() -> None:
    schemas = registry.get_schemas()
    assert len(schemas) > 0
    names = [s["name"] for s in schemas]
    assert "draft_create_box" in names
    assert "read_viewer_context" in names
    
    # Check shape of a schema
    box_schema = next(s for s in schemas if s["name"] == "draft_create_box")
    assert box_schema["description"] is not None
    assert box_schema["parameters"]["type"] == "object"
    assert "length" in box_schema["parameters"]["properties"]
    assert box_schema["parameters"]["properties"]["length"]["type"] == "number"


def test_tool_registry_get_schemas_with_filter() -> None:
    schemas = registry.get_schemas(["draft_create_box"])
    assert len(schemas) == 1
    assert schemas[0]["name"] == "draft_create_box"


