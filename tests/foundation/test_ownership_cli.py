from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from flow_cad.cli import flow


def test_ownership_cli_reports_clean_sdk_only_project(tmp_path: Path) -> None:
    package = tmp_path / "flow_b2"
    package.mkdir()
    (package / "part.py").write_text("from flow_cad.sdk import ManifestPart\n", encoding="utf-8")

    result = CliRunner().invoke(
        flow,
        ["ownership", "check", "--project-root", str(tmp_path)],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "status=ok" in result.output


def test_ownership_cli_fails_and_supports_explicit_archive_exclusion(tmp_path: Path) -> None:
    package = tmp_path / "flow_b2"
    package.mkdir()
    (package / "part.py").write_text("import flow_cad.viewer\n", encoding="utf-8")
    migration = tmp_path / "migration"
    migration.mkdir()
    (migration / "legacy.py").write_text("import flow_cad.core.geometry\n", encoding="utf-8")
    runner = CliRunner()

    failed = runner.invoke(
        flow,
        ["ownership", "check", "--project-root", str(tmp_path), "--exclude", "migration"],
    )
    (package / "part.py").write_text("from flow_cad.sdk import PartRole\n", encoding="utf-8")
    clean = runner.invoke(
        flow,
        ["ownership", "check", "--project-root", str(tmp_path), "--exclude", "migration"],
        catch_exceptions=False,
    )

    assert failed.exit_code != 0
    assert "flow_cad.viewer" in failed.output
    assert "flow_cad.core.geometry" not in failed.output
    assert clean.exit_code == 0
