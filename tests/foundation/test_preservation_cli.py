from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from click.testing import CliRunner

from flow_cad.cli import flow


def _git_source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", source], check=True)
    (source / "src").mkdir()
    (source / "src" / "tracked.py").write_bytes(b"tracked\r\n")
    (source / "artifacts").mkdir()
    (source / "artifacts" / "model.step").write_bytes(b"\x00STEP\n")
    subprocess.run(
        ["git", "-C", source, "add", "src/tracked.py"],
        check=True,
    )
    return source


def test_preserve_cli_manifest_copy_verify_and_map(tmp_path: Path) -> None:
    source = _git_source(tmp_path)
    archive = tmp_path / "archive"
    manifest_path = tmp_path / "artifact-manifest.sha256"
    migration_map = tmp_path / "MIGRATION_MAP.csv"
    runner = CliRunner()
    scope = [
        "--source",
        str(source),
        "--tracked",
        "src",
        "--tree",
        "artifacts",
    ]

    manifest_result = runner.invoke(
        flow,
        ["preserve", "manifest", *scope, "--output", str(manifest_path)],
        catch_exceptions=False,
    )
    copy_result = runner.invoke(
        flow,
        ["preserve", "copy", *scope, "--archive", str(archive)],
        catch_exceptions=False,
    )
    verify_result = runner.invoke(
        flow,
        ["preserve", "verify", *scope, "--archive", str(archive)],
        catch_exceptions=False,
    )
    map_result = runner.invoke(
        flow,
        ["preserve", "migration-map", *scope, "--output", str(migration_map)],
        catch_exceptions=False,
    )

    assert manifest_result.exit_code == 0
    assert copy_result.exit_code == 0
    assert verify_result.exit_code == 0
    assert map_result.exit_code == 0
    assert "phase=running" in copy_result.output
    assert json.loads(verify_result.output.splitlines()[-1])["verified"] is True
    assert (archive / "src" / "tracked.py").read_bytes() == b"tracked\r\n"
    assert (archive / "artifacts" / "model.step").read_bytes() == b"\x00STEP\n"
    with migration_map.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["original_path"] for row in rows] == [
        "artifacts/model.step",
        "src/tracked.py",
    ]
    assert {row["status"] for row in rows} == {"preserved-only"}


def test_preserve_cli_rejects_tree_traversal(tmp_path: Path) -> None:
    source = _git_source(tmp_path)

    result = CliRunner().invoke(
        flow,
        [
            "preserve",
            "manifest",
            "--source",
            str(source),
            "--tree",
            "../source",
            "--output",
            str(tmp_path / "unsafe.sha256"),
        ],
    )

    assert result.exit_code != 0
    assert "safe relative path" in result.output
