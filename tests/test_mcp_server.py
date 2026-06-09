from __future__ import annotations

from pathlib import Path
import sys
import types

import pytest

from flow_cad.mcp import server as mcp_server
from flow_cad.project import init_project


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


def test_build_server_registers_draft_geometry_tools(monkeypatch) -> None:
    install_fake_fastmcp(monkeypatch)

    server = mcp_server.build_server()

    assert server.name == "Flow CAD MCP"
    assert "draft-only CAD geometry operations" in server.instructions
    assert "draft_create_box" in server.tools
    assert "draft_set_panel_thickness" in server.tools
    assert "draft_add_hole" in server.tools
    assert "draft_add_counterbore" in server.tools
    assert "draft_add_slot" in server.tools
    assert "draft_add_louver_pattern" in server.tools
    assert "draft_mirror_features" in server.tools
    assert "draft_measure" in server.tools
    assert "draft_export_step" in server.tools
    assert "draft_discard" in server.tools
    assert "draft_begin_transaction" in server.tools
    assert "draft_transaction_create_box" in server.tools
    assert "draft_transaction_set_panel_thickness" in server.tools
    assert "draft_transaction_add_hole" in server.tools
    assert "draft_transaction_add_counterbore" in server.tools
    assert "draft_transaction_add_slot" in server.tools
    assert "draft_transaction_add_louver_pattern" in server.tools
    assert "draft_transaction_mirror_features" in server.tools
    assert "draft_transaction_measure" in server.tools
    assert "draft_transaction_preview" in server.tools
    assert "draft_transaction_accept" in server.tools
    assert "draft_transaction_discard" in server.tools


def test_mcp_draft_tools_write_only_project_local_draft_state(monkeypatch, tmp_path: Path) -> None:
    install_fake_fastmcp(monkeypatch)
    init_project(tmp_path)
    monkeypatch.setenv("FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS", str(tmp_path))

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


def test_mcp_draft_tools_reject_project_roots_outside_allowed_roots(monkeypatch, tmp_path: Path) -> None:
    install_fake_fastmcp(monkeypatch)
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
