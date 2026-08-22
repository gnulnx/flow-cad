from __future__ import annotations

import json
import shutil
from pathlib import Path

from click.testing import CliRunner

from flow_cad.cli import flow


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "projects"


def _copy_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "minimal_alpha"
    shutil.copytree(FIXTURES / "minimal_alpha", root)
    return root


def test_sync_and_part_queries_work_from_a_nested_project_path(tmp_path: Path, monkeypatch) -> None:
    root = _copy_fixture(tmp_path)
    nested = root / "minimal_alpha"
    monkeypatch.chdir(nested)

    synced = CliRunner().invoke(flow, ["sync"], catch_exceptions=False)
    listed = CliRunner().invoke(
        flow, ["part", "list", "--json-output"], catch_exceptions=False
    )
    shown = CliRunner().invoke(
        flow,
        ["part", "show", "original_alpha_panel", "--json-output"],
        catch_exceptions=False,
    )

    assert synced.exit_code == 0
    assert "parts=1" in synced.output
    assert json.loads(listed.output)[0]["key"] == "alpha_panel"
    assert json.loads(shown.output)["uuid"] == "11111111-1111-4111-8111-111111111111"


def test_part_rename_and_retire_commands_publish_revision(tmp_path: Path, monkeypatch) -> None:
    root = _copy_fixture(tmp_path)
    monkeypatch.chdir(root)
    runner = CliRunner()
    runner.invoke(flow, ["sync"], catch_exceptions=False)

    renamed = runner.invoke(
        flow,
        ["part", "rename", "alpha_panel", "alpha_mounting_panel"],
        catch_exceptions=False,
    )
    retired = runner.invoke(
        flow,
        ["part", "retire", "alpha_panel"],
        catch_exceptions=False,
    )

    assert renamed.exit_code == 0
    assert "alpha_panel -> alpha_mounting_panel" in renamed.output
    assert "revision=2" in renamed.output
    assert retired.exit_code == 0
    assert "Retired alpha_mounting_panel" in retired.output
    assert "revision=3" in retired.output
