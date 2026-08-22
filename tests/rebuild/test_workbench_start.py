from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from flow_cad.cli import flow
from flow_cad.registry.db import database_path


def test_flow_start_uses_replacement_manifest_and_api_factory(tmp_path: Path, monkeypatch) -> None:
    manifest = {
        "schema_version": 1,
        "project_id": "start_fixture",
        "python_package": "start_fixture",
        "parts": [],
        "assemblies": {"active": {"occurrences": []}},
    }
    (tmp_path / "flowcad.project.yaml").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    captured: dict[str, object] = {}

    def fake_start_viewer(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr("flow_cad.viewer.cli.start_viewer", fake_start_viewer)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(flow, ["start", "--no-open-browser"], catch_exceptions=False)

    assert result.exit_code == 0
    assert database_path(tmp_path).is_file()
    assert captured["project_root"] == tmp_path.resolve()
    assert captured["backend_application"] == (
        "flow_cad.viewer.api.app:create_app_from_environment"
    )
    assert captured["backend_factory"] is True
    assert captured["open_browser"] is False
