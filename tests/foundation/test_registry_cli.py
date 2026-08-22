from __future__ import annotations

import shutil
from pathlib import Path

from click.testing import CliRunner

from flow_cad.registry import sync_project
from flow_cad.registry_cli import registry


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "projects"


def test_registry_cli_queries_strict_metadata_index(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "minimal_alpha"
    shutil.copytree(FIXTURES / "minimal_alpha", root)
    sync_project(root)
    monkeypatch.chdir(root)
    runner = CliRunner()

    listed = runner.invoke(registry, ["list"])
    shown = runner.invoke(registry, ["show", "original_alpha_panel"])

    assert listed.exit_code == 0, listed.output
    assert "alpha_panel" in listed.output
    assert "active" in listed.output
    assert shown.exit_code == 0, shown.output
    assert "key: alpha_panel" in shown.output
    assert "aliases: original_alpha_panel" in shown.output
    assert "artifact[step]: missing exports/step/alpha_panel.step" in shown.output


def test_registry_cli_requires_generated_index(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "minimal_alpha"
    shutil.copytree(FIXTURES / "minimal_alpha", root)
    monkeypatch.chdir(root)

    result = CliRunner().invoke(registry, ["list"])

    assert result.exit_code != 0
    assert "Run `flow sync` first" in result.output
