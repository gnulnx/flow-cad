from __future__ import annotations

from pathlib import Path
import sys
import types

import pytest

from flow_cad.mcp import server as mcp_server
from flow_cad.project import init_project


def tiny_png_data_url() -> str:
    return (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X9nSAAAAAASUVORK5CYII="
    )


class FakeFastMCP:
    def __init__(self, name: str, instructions: str):
        self.name = name
        self.instructions = instructions
        self.tools: dict[str, object] = {}

    def tool(self, *, name: str, description: str):
        def decorator(func):
            self.tools[name] = func
            return func

        return decorator


def install_fake_fastmcp(monkeypatch) -> None:
    fastmcp_module = types.ModuleType("mcp.server.fastmcp")
    fastmcp_module.FastMCP = FakeFastMCP
    server_module = types.ModuleType("mcp.server")
    server_module.fastmcp = fastmcp_module
    mcp_module = types.ModuleType("mcp")
    mcp_module.server = server_module
    monkeypatch.setitem(sys.modules, "mcp", mcp_module)
    monkeypatch.setitem(sys.modules, "mcp.server", server_module)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fastmcp_module)


@pytest.fixture(autouse=True)
def clear_mcp_state(monkeypatch) -> None:
    mcp_server._DRAFT_STORES.clear()
    monkeypatch.delenv("FLOW_CAD_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS", raising=False)
    monkeypatch.delenv("FLOW_CAD_MCP_TOOLSET", raising=False)


def test_build_server_registers_default_agent_toolset(monkeypatch) -> None:
    install_fake_fastmcp(monkeypatch)

    server = mcp_server.build_server()

    assert server.name == "Flow CAD MCP"
    assert "draft-only CAD geometry operations" in server.instructions
    assert set(server.tools) == mcp_server.DEFAULT_TOOL_NAMES
    assert len(server.tools) == 22
    assert "draft_create_box" not in server.tools
    assert "visual_evidence_create" not in server.tools
    assert "draft_begin_transaction" in server.tools
    assert "draft_transaction_create_box" in server.tools
    assert "draft_transaction_create_profile" in server.tools
    assert "request_visual_evidence" in server.tools
    assert mcp_server.DRAFT_OPERATION_REGISTRY_TOOL_NAME in server.tools
    assert "draft_transaction_add_raised_wall" in server.tools


def test_build_server_registers_advanced_toolset(monkeypatch) -> None:
    install_fake_fastmcp(monkeypatch)
    monkeypatch.setenv("FLOW_CAD_MCP_TOOLSET", "advanced")

    server = mcp_server.build_server()

    assert set(server.tools) == mcp_server.TOOLSET_TOOL_NAMES["advanced"]
    assert len(server.tools) == 35
    assert "draft_create_box" in server.tools
    assert "draft_create_profile" in server.tools
    assert "draft_add_raised_wall" in server.tools
    assert "draft_transaction_create_profile" in server.tools
    assert "draft_transaction_add_raised_wall" in server.tools
    assert "visual_evidence_create" in server.tools
    assert mcp_server.DRAFT_OPERATION_REGISTRY_TOOL_NAME in server.tools


def test_build_server_registers_visual_toolset(monkeypatch) -> None:
    install_fake_fastmcp(monkeypatch)
    monkeypatch.setenv("FLOW_CAD_MCP_TOOLSET", "visual")

    server = mcp_server.build_server()

    assert set(server.tools) == mcp_server.TOOLSET_TOOL_NAMES["visual"]
    assert set(server.tools) == mcp_server.ADVANCED_VISUAL_TOOL_NAMES
    assert "draft_begin_transaction" not in server.tools
    assert mcp_server.DRAFT_OPERATION_REGISTRY_TOOL_NAME not in server.tools


def test_build_server_registers_transactions_toolset(monkeypatch) -> None:
    install_fake_fastmcp(monkeypatch)
    monkeypatch.setenv("FLOW_CAD_MCP_TOOLSET", "transactions")

    server = mcp_server.build_server()

    assert set(server.tools) == mcp_server.TOOLSET_TOOL_NAMES["transactions"]
    assert len(server.tools) == 18
    assert "draft_begin_transaction" in server.tools
    assert "draft_transaction_create_profile" in server.tools
    assert "draft_transaction_add_raised_wall" in server.tools
    assert "validator_run" in server.tools
    assert "request_visual_evidence" not in server.tools
    assert "draft_create_box" not in server.tools
    assert mcp_server.DRAFT_OPERATION_REGISTRY_TOOL_NAME in server.tools


def test_build_server_unknown_toolset_falls_back_to_default(monkeypatch) -> None:
    install_fake_fastmcp(monkeypatch)
    monkeypatch.setenv("FLOW_CAD_MCP_TOOLSET", "typo")

    server = mcp_server.build_server()

    assert set(server.tools) == mcp_server.DEFAULT_TOOL_NAMES


def test_draft_operation_registry_tool_returns_add_raised_wall_metadata(monkeypatch) -> None:
    install_fake_fastmcp(monkeypatch)

    server = mcp_server.build_server()
    registry = server.tools[mcp_server.DRAFT_OPERATION_REGISTRY_TOOL_NAME]()

    assert registry["ok"] is True
    operations = registry["operations"]
    assert isinstance(operations, list)
    raised_wall_operation = next(
        (
            op
            for op in operations
            if isinstance(op, dict) and (op.get("id") == "add_raised_wall" or op.get("name") == "add_raised_wall")
        ),
        None,
    )
    assert raised_wall_operation is not None
    assert isinstance(raised_wall_operation, dict)
    assert raised_wall_operation["title"] == "Add raised wall"
    assert raised_wall_operation["endpoint_slug"] == "raised-walls"
    assert raised_wall_operation["direct_tool_name"] == "draft_add_raised_wall"
    assert raised_wall_operation["transaction_tool_name"] == "draft_transaction_add_raised_wall"
    assert raised_wall_operation["supports_preview"] is True


def test_mcp_draft_tools_write_only_project_local_draft_state(monkeypatch, tmp_path: Path) -> None:
    install_fake_fastmcp(monkeypatch)
    init_project(tmp_path)
    monkeypatch.setenv("FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS", str(tmp_path))
    monkeypatch.setenv("FLOW_CAD_MCP_TOOLSET", "advanced")

    server = mcp_server.build_server()
    created = server.tools["draft_create_box"](
        length=120.0,
        width=45.0,
        height=3.0,
        project_root=str(tmp_path),
        part_id="mcp_panel",
        material="PETG",
    )
    draft_token = created["draft_token"]

    server.tools["draft_add_hole"](
        draft_token,
        "top",
        12.0,
        8.0,
        4.2,
        project_root=str(tmp_path),
    )
    mirrored = server.tools["draft_mirror_features"](
        draft_token,
        "top",
        "bottom",
        project_root=str(tmp_path),
    )
    measured = server.tools["draft_measure"](draft_token, project_root=str(tmp_path))
    exported = server.tools["draft_export_step"](draft_token, project_root=str(tmp_path))
    preview_path = Path(str(exported["preview_step_path"]))

    assert mirrored["hole_centers"][1]["axis"] == [0.0, 0.0, -1.0]
    assert measured["bounding_box"]["size"] == [120.0, 45.0, 3.0]
    assert [center["axis"] for center in measured["hole_centers"]] == [[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]]
    assert preview_path.exists()
    assert preview_path.is_relative_to(tmp_path / ".flow" / "drafts")
    assert not preview_path.is_relative_to(tmp_path / "exports")
    assert not any(path.is_file() for path in (tmp_path / "exports").rglob("*"))


def test_mcp_draft_transaction_tools_create_review_artifacts_only(monkeypatch, tmp_path: Path) -> None:
    install_fake_fastmcp(monkeypatch)
    init_project(tmp_path)
    monkeypatch.setenv("FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS", str(tmp_path))

    server = mcp_server.build_server()
    begun = server.tools["draft_begin_transaction"](
        project_root=str(tmp_path),
        part_id="mcp_transaction_panel",
    )
    transaction_token = begun["transaction_token"]

    server.tools["draft_transaction_create_box"](
        transaction_token,
        80.0,
        30.0,
        2.5,
        project_root=str(tmp_path),
        material="PETG",
    )
    server.tools["draft_transaction_add_hole"](
        transaction_token,
        "top",
        10.0,
        7.5,
        3.2,
        project_root=str(tmp_path),
    )
    previewed = server.tools["draft_transaction_preview"](transaction_token, project_root=str(tmp_path))
    accepted = server.tools["draft_transaction_accept"](transaction_token, project_root=str(tmp_path))
    preview_path = Path(str(previewed["preview_step_path"]))
    source_patch_path = Path(str(accepted["source_patch_path"]))

    assert accepted["status"] == "accepted"
    assert preview_path.exists()
    assert preview_path.is_relative_to(tmp_path / ".flow" / "drafts")
    assert source_patch_path.exists()
    assert source_patch_path.is_relative_to(tmp_path / ".flow" / "draft-transactions")
    assert "flow/parts/mcp_transaction_panel.py" in source_patch_path.read_text(encoding="utf-8")
    assert not (tmp_path / "flow" / "parts" / "mcp_transaction_panel.py").exists()
    assert not any(path.is_file() for path in (tmp_path / "exports").rglob("*"))


def test_mcp_draft_transaction_profile_tool_creates_profile_review_artifacts_only(monkeypatch, tmp_path: Path) -> None:
    install_fake_fastmcp(monkeypatch)
    init_project(tmp_path)
    monkeypatch.setenv("FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS", str(tmp_path))

    server = mcp_server.build_server()
    begun = server.tools["draft_begin_transaction"](
        project_root=str(tmp_path),
        part_id="mcp_sketch_profile",
    )
    transaction_token = begun["transaction_token"]
    profile_points = [
        [-50.0, -12.0],
        [-20.0, -32.5],
        [0.0, -18.0],
        [20.0, -32.5],
        [50.0, -12.0],
        [34.0, 12.0],
        [0.0, 32.5],
        [-34.0, 12.0],
        [-50.0, -12.0],
    ]

    created = server.tools["draft_transaction_create_profile"](
        transaction_token,
        100.0,
        65.0,
        10.0,
        profile_points,
        project_root=str(tmp_path),
    )
    server.tools["draft_transaction_add_counterbore"](
        transaction_token,
        "top",
        25.0,
        32.5,
        8.0,
        2.0,
        project_root=str(tmp_path),
    )
    previewed = server.tools["draft_transaction_preview"](transaction_token, project_root=str(tmp_path))
    accepted = server.tools["draft_transaction_accept"](transaction_token, project_root=str(tmp_path))
    source_patch_path = Path(str(accepted["source_patch_path"]))

    assert created["draft"]["profile_points"] == profile_points
    assert Path(str(previewed["preview_step_path"])).is_relative_to(tmp_path / ".flow" / "drafts")
    assert source_patch_path.is_relative_to(tmp_path / ".flow" / "draft-transactions")
    source_patch = source_patch_path.read_text(encoding="utf-8")
    assert "Polyline" in source_patch
    assert "make_face" in source_patch
    assert not (tmp_path / "flow" / "parts" / "mcp_sketch_profile.py").exists()
    assert not any(path.is_file() for path in (tmp_path / "exports").rglob("*"))


def test_mcp_draft_tools_reject_project_roots_outside_allowed_roots(monkeypatch, tmp_path: Path) -> None:
    install_fake_fastmcp(monkeypatch)
    monkeypatch.setenv("FLOW_CAD_MCP_TOOLSET", "advanced")
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    monkeypatch.setenv("FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS", str(allowed_root))

    server = mcp_server.build_server()

    with pytest.raises(ValueError, match="outside allowed Flow CAD MCP roots"):
        server.tools["draft_create_box"](
            length=1.0,
            width=1.0,
            height=1.0,
            project_root=str(outside_root),
        )


def test_mcp_validator_tools_return_structured_reports(monkeypatch, tmp_path: Path) -> None:
    install_fake_fastmcp(monkeypatch)
    init_project(tmp_path)
    monkeypatch.setenv("FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS", str(tmp_path))

    server = mcp_server.build_server()
    listed = server.tools["validator_list"](project_root=str(tmp_path))
    result = server.tools["validator_run"]("project", project_root=str(tmp_path))
    profile = server.tools["profile_last"](project_root=str(tmp_path))

    assert listed["ok"] is True
    assert any(validator["id"] == "panel-basic" for validator in listed["validators"])
    assert result["ok"] is True
    assert result["reports"][0]["metadata"]["id"] == "project"
    assert profile["ok"] is True
    assert "Flow CAD profile" in profile["summary"]
    assert not any(path.is_file() for path in (tmp_path / "exports").rglob("*"))


def test_mcp_visual_evidence_tools_write_thread_local_artifacts(monkeypatch, tmp_path: Path) -> None:
    install_fake_fastmcp(monkeypatch)
    init_project(tmp_path)
    monkeypatch.setenv("FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS", str(tmp_path))
    monkeypatch.setenv("FLOW_CAD_MCP_TOOLSET", "visual")

    service = mcp_server.design_thread_service(str(tmp_path))
    thread = service.create_thread({"title": "MCP visual evidence"})

    server = mcp_server.build_server()
    created = server.tools["visual_evidence_create"](
        thread["thread_id"],
        project_root=str(tmp_path),
        data_url=tiny_png_data_url(),
        source="agent",
        view="front",
        width=320,
        height=240,
        purpose="mcp review",
        selected_ids=["example_block"],
        visible_ids=["example_block"],
        part_ids=["example_block"],
        metadata={"caller": "mcp-test"},
    )
    listed = server.tools["visual_evidence_list"](thread["thread_id"], project_root=str(tmp_path))
    loaded = server.tools["visual_evidence_get"](
        thread["thread_id"],
        created["artifact_id"],
        project_root=str(tmp_path),
    )

    evidence_root = tmp_path / ".flow" / "design-threads" / thread["thread_id"] / "visual-evidence"
    png_path = tmp_path / ".flow" / "design-threads" / created["path"]

    assert created["kind"] == "visual_evidence"
    assert created["view"] == "front"
    assert created["image_url"] == (
        f"/api/design-threads/{thread['thread_id']}/visual-evidence/{created['artifact_id']}/image"
    )
    assert listed["ok"] is True
    assert listed["count"] == 1
    assert loaded["artifact_id"] == created["artifact_id"]
    assert loaded["metadata"]["caller"] == "mcp-test"
    assert png_path.exists()
    assert png_path.is_relative_to(evidence_root)
    assert not any(path.is_file() for path in (tmp_path / "exports").rglob("*"))


def test_mcp_request_visual_evidence_writes_thread_local_request(monkeypatch, tmp_path: Path) -> None:
    install_fake_fastmcp(monkeypatch)
    init_project(tmp_path)
    monkeypatch.setenv("FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS", str(tmp_path))

    service = mcp_server.design_thread_service(str(tmp_path))
    thread = service.create_thread({"title": "MCP visual evidence request"})

    server = mcp_server.build_server()
    requested = server.tools["request_visual_evidence"](
        thread["thread_id"],
        project_root=str(tmp_path),
        view="right",
        width=1024,
        height=768,
        purpose="agent wants side view",
        selected_ids=["example_block"],
        visible_ids=["example_block", "other"],
        part_ids=["example_block"],
        metadata={"agent": "mcp-test"},
        request_id="../../agent/request",
    )
    listed = server.tools["visual_evidence_requests_list"](
        thread["thread_id"],
        project_root=str(tmp_path),
        status="pending",
    )

    request_root = tmp_path / ".flow" / "design-threads" / thread["thread_id"] / "visual-evidence" / "requests"
    request_path = request_root / f"{requested['request_id']}.json"

    assert requested["request_id"] == "agent-request"
    assert requested["status"] == "pending"
    assert requested["view"] == "right"
    assert requested["width"] == 1024
    assert requested["height"] == 768
    assert requested["purpose"] == "agent wants side view"
    assert listed["ok"] is True
    assert listed["count"] == 1
    assert listed["visual_evidence_requests"][0]["request_id"] == requested["request_id"]
    assert request_path.exists()
    assert request_path.is_relative_to(request_root)
    assert not any(path.is_file() for path in (tmp_path / "exports").rglob("*"))
