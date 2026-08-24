from __future__ import annotations

import shutil
from pathlib import Path

from flow_cad.chat import default_chat_tools
from flow_cad.registry import sync_project


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "projects"


def test_default_chat_tools_inspect_only_registered_project_facts(tmp_path: Path) -> None:
    root = tmp_path / "minimal_alpha"
    shutil.copytree(FIXTURES / "minimal_alpha", root)
    sync_project(root)
    tools = default_chat_tools(root)
    context = {
        "selected_part_uuid": "11111111-1111-4111-8111-111111111111",
        "visible_occurrence_ids": ["alpha-primary"],
        "camera": {"position": [1, 2, 3]},
        "measurements": [{"total_mm": 10.0}],
        "annotations": [{"kind": "arrow"}],
    }

    part = tools.execute("flow_inspect_part", {}, context)
    placement = tools.execute(
        "flow_inspect_placement",
        {"identity": "original_alpha_panel"},
        context,
    )
    view = tools.execute("flow_current_view", {}, context)
    build = tools.execute("flow_request_build", {}, context)

    assert part["part"]["key"] == "alpha_panel"
    assert placement["occurrences"][0]["id"] == "alpha_panel_main"
    assert view["camera"] == {"position": [1, 2, 3]}
    assert build == {
        "operation": "request_build",
        "status": "authorization_required",
        "part_uuid": "11111111-1111-4111-8111-111111111111",
        "part_key": "alpha_panel",
        "message": (
            "The user must explicitly submit the scoped Build operation in the "
            "workbench before files or artifacts change."
        ),
    }
    assert {spec["name"] for spec in tools.provider_specs} == {
        "flow_current_view",
        "flow_inspect_part",
        "flow_inspect_placement",
        "flow_request_build",
    }
