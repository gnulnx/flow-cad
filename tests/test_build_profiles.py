import json
import os
import time
from pathlib import Path
from textwrap import dedent

from click.testing import CliRunner

from flow_cad.cli import flow
from flow_cad.project import init_project


def _run_build(tmp_path: Path, monkeypatch, args: list[str]):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    return runner.invoke(flow, ["cad", "build", *args], catch_exceptions=False)


def _latest_profile(tmp_path: Path) -> dict:
    return json.loads((tmp_path / ".flow" / "profiles" / "latest-build-profile.json").read_text(encoding="utf-8"))


def _latest_phase_events(profile: dict, phase: str) -> list[dict]:
    return [event for event in profile["events"] if event.get("phase") == phase]


def _build_total_event(profile: dict) -> dict:
    for event in profile["events"]:
        if event.get("phase") == "build_total":
            return event
    raise AssertionError("build_total event missing from profile")


def _write_two_part_project(tmp_path: Path) -> None:
    init_project(tmp_path)
    project_id = tmp_path.name.replace("-", "_")
    (tmp_path / "flow" / "params.py").write_text(
        dedent(
            f"""
            from __future__ import annotations

            from dataclasses import dataclass


            @dataclass(frozen=True)
            class ProjectParams:
                project_id: str = "{project_id}"
                panel_width: float = 20.0
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "flow" / "parts" / "panel_a.py").write_text(
        dedent(
            """
            from __future__ import annotations

            from build123d import Box


            def make_panel_a(params):
                return Box(params.panel_width, 12.0, 3.0)
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "flow" / "parts" / "panel_b.py").write_text(
        dedent(
            """
            from __future__ import annotations

            from build123d import Box


            def make_panel_b(_params):
                return Box(14.0, 8.0, 2.0)
            """
        ).lstrip(),
        encoding="utf-8",
    )
    (tmp_path / "flow" / "assemblies" / "robot.py").write_text(
        dedent(
            """
            from __future__ import annotations

            from flow_cad.core.metadata import PartDefinition
            from flow.parts.panel_a import make_panel_a
            from flow.parts.panel_b import make_panel_b


            PART_DEFINITIONS = (
                PartDefinition("panel_a", "panel", "panel_a.step", make_panel_a),
                PartDefinition("panel_b", "panel", "panel_b.step", make_panel_b),
            )


            def iter_part_definitions(*, include_references: bool = True):
                yield from PART_DEFINITIONS


            def get_assembly_placements(_params, *, include_references: bool = False):
                return [
                    {
                        "name": "panel_a",
                        "part_key": "panel_a",
                        "location": (0.0, 0.0, 0.0),
                        "rotation": (0.0, 0.0, 0.0),
                    },
                    {
                        "name": "panel_b",
                        "part_key": "panel_b",
                        "location": (40.0, 0.0, 0.0),
                        "rotation": (0.0, 0.0, 0.0),
                    },
                ]
            """
        ).lstrip(),
        encoding="utf-8",
    )


def test_build_part_profile_exports_only_one_part_and_skips_assembly(tmp_path: Path, monkeypatch) -> None:
    init_project(tmp_path)

    result = _run_build(tmp_path, monkeypatch, ["--no-bundle", "--no-cache", "--no-snapshots", "--part", "example_block"])

    assert result.exit_code == 0
    assert "Exported 1 STEP files to" in result.output
    assert "Exported 2 STEP files" not in result.output

    step_root = tmp_path / "exports" / "step"
    assert (step_root / "example" / "example_block.step").exists()
    assert not (step_root / "assembly" / f"{tmp_path.name}_assembly.step").exists()

    profile = _latest_profile(tmp_path)
    assert profile["build_profile"] == "all"
    assert _build_total_event(profile)["metadata"]["build_mode"] == "part"


def test_build_changed_profile_only_rebuilds_touched_part(tmp_path: Path, monkeypatch) -> None:
    _write_two_part_project(tmp_path)

    baseline = _run_build(tmp_path, monkeypatch, ["--no-bundle", "--no-snapshots"])
    assert baseline.exit_code == 0

    part_source = tmp_path / "flow" / "parts" / "panel_a.py"
    future = time.time() + 10_000_000
    os.utime(part_source, (future, future))

    result = _run_build(tmp_path, monkeypatch, ["--changed", "--no-bundle", "--no-cache", "--no-snapshots"])
    assert result.exit_code == 0
    assert "Exported 1 STEP files to" in result.output
    assert "Updated active cache" not in result.output

    profile = _latest_profile(tmp_path)
    assert profile["build_profile"] == "all"
    assert _build_total_event(profile)["metadata"]["build_mode"] == "changed"
    assert len(_latest_phase_events(profile, "assembly_generation")) == 1
    assert _latest_phase_events(profile, "assembly_generation")[0]["status"] == "skipped"
    step_events = _latest_phase_events(profile, "step_export")
    assert [event for event in step_events if event.get("part_id") == "panel_a" and event["status"] == "ok"]
    panel_b_events = [event for event in step_events if event.get("part_id") == "panel_b"]
    assert len(panel_b_events) == 1
    assert panel_b_events[0]["status"] == "skipped"
    assert panel_b_events[0]["metadata"]["artifact_cache_reason"] == "cache_hit"


def test_build_changed_profile_succeeds_when_everything_is_cached(tmp_path: Path, monkeypatch) -> None:
    _write_two_part_project(tmp_path)

    baseline = _run_build(tmp_path, monkeypatch, ["--no-bundle", "--no-snapshots"])
    assert baseline.exit_code == 0

    result = _run_build(tmp_path, monkeypatch, ["--changed", "--no-bundle", "--no-cache", "--no-snapshots"])
    assert result.exit_code == 0
    assert "Exported 0 STEP files to" in result.output

    profile = _latest_profile(tmp_path)
    assert _build_total_event(profile)["metadata"]["build_mode"] == "changed"
    step_events = _latest_phase_events(profile, "step_export")
    cached_steps = [event for event in step_events if event.get("part_id") in {"panel_a", "panel_b"}]
    assert len(cached_steps) == 2
    assert all(event["status"] == "skipped" for event in cached_steps)
    assert all(event["metadata"]["artifact_cache_reason"] == "cache_hit" for event in cached_steps)
    report_events = _latest_phase_events(profile, "report_generation")
    assert report_events[-1]["status"] == "skipped"
    assert report_events[-1]["metadata"]["reason"] == "no_changed_definitions"


def test_build_changed_profile_rebuilds_all_parts_when_params_change(tmp_path: Path, monkeypatch) -> None:
    _write_two_part_project(tmp_path)

    baseline = _run_build(tmp_path, monkeypatch, ["--no-bundle", "--no-snapshots"])
    assert baseline.exit_code == 0

    params_path = tmp_path / "flow" / "params.py"
    params_path.write_text(params_path.read_text(encoding="utf-8").replace("20.0", "24.0"), encoding="utf-8")
    future = time.time() + 10_000_000
    os.utime(params_path, (future, future))

    result = _run_build(tmp_path, monkeypatch, ["--changed", "--no-bundle", "--no-cache", "--no-snapshots"])
    assert result.exit_code == 0
    assert "Exported 2 STEP files to" in result.output

    profile = _latest_profile(tmp_path)
    step_events = [event for event in _latest_phase_events(profile, "step_export") if event.get("part_id") in {"panel_a", "panel_b"}]
    assert len(step_events) == 2
    assert all(event["status"] == "ok" for event in step_events)
    assert all(event["metadata"]["artifact_cache_reason"] == "params_changed" for event in step_events)


def test_build_no_stl_option_skips_stl_export(tmp_path: Path, monkeypatch) -> None:
    init_project(tmp_path)

    result = _run_build(
        tmp_path,
        monkeypatch,
        ["--no-stl", "--no-bundle", "--no-cache", "--no-snapshots"],
    )

    assert result.exit_code == 0
    assert "Exported 2 STEP files to" in result.output
    assert "Exported 2 STL files to" not in result.output
    assert not (tmp_path / "exports" / "stl" / "example" / "example_block.stl").exists()
    assert not (tmp_path / "exports" / "stl" / "assembly" / f"{tmp_path.name}_assembly.stl").exists()

    profile = _latest_profile(tmp_path)
    stl_skips = [event for event in profile["events"] if event.get("phase") == "stl_export"]
    assert len(stl_skips) == 2
    assert all(event["status"] == "skipped" for event in stl_skips)
    assert all(event["metadata"]["reason"] == "stl_disabled" for event in stl_skips)


def test_build_snapshots_only_does_not_export_step_or_stl(tmp_path: Path, monkeypatch) -> None:
    init_project(tmp_path)

    result = _run_build(
        tmp_path,
        monkeypatch,
        ["--snapshots-only", "--no-bundle", "--no-cache"],
    )

    assert result.exit_code == 0
    assert not (tmp_path / "exports" / "step" / "example" / "example_block.step").exists()
    assert not (tmp_path / "exports" / "stl" / "example" / "example_block.stl").exists()

    profile = _latest_profile(tmp_path)
    step_skips = _latest_phase_events(profile, "step_export")
    stl_skips = _latest_phase_events(profile, "stl_export")
    assert step_skips
    assert stl_skips
    assert all(event["status"] == "skipped" for event in step_skips)
    assert all(event["metadata"]["reason"] == "snapshots_only" for event in step_skips)
    assert all(event["status"] == "skipped" for event in stl_skips)
    assert all(event["metadata"]["reason"] == "snapshots_only" for event in stl_skips)


def test_build_no_reports_option_disables_report_generation(tmp_path: Path, monkeypatch) -> None:
    init_project(tmp_path)

    result = _run_build(
        tmp_path,
        monkeypatch,
        ["--no-reports", "--no-bundle", "--no-cache", "--no-snapshots"],
    )
    assert result.exit_code == 0
    assert "Wrote report to" not in result.output
    assert not (tmp_path / "reports" / f"{tmp_path.name}_cad_report.txt").exists()

    profile = _latest_profile(tmp_path)
    report_events = _latest_phase_events(profile, "report_generation")
    assert len(report_events) == 1
    assert report_events[0]["status"] == "skipped"
    assert report_events[0]["metadata"]["reason"] == "reports_disabled"


def test_build_assembly_preview_refreshes_assembly_without_handoff_packaging(tmp_path: Path, monkeypatch) -> None:
    init_project(tmp_path)

    result = _run_build(
        tmp_path,
        monkeypatch,
        ["--assembly-preview", "--no-bundle", "--no-cache"],
    )

    assert result.exit_code == 0
    assert "Created exports handoff bundle" not in result.output
    assert "Updated active cache" not in result.output
    assert (tmp_path / "exports" / "step" / "assembly" / f"{tmp_path.name}_assembly.step").exists()

    profile = _latest_profile(tmp_path)
    assert _build_total_event(profile)["metadata"]["build_mode"] == "assembly-preview"


def test_build_handoff_forces_full_profile_behavior(tmp_path: Path, monkeypatch) -> None:
    init_project(tmp_path)

    result = _run_build(
        tmp_path,
        monkeypatch,
        ["--handoff", "--no-bundle", "--no-cache", "--no-reports", "--no-snapshots", "--no-stl"],
    )

    assert result.exit_code == 0
    assert "Created exports handoff bundle" in result.output
    assert "Updated active cache" in result.output
    assert "Exported 2 STL files to" in result.output
    assert "Wrote report to" in result.output

    assert (tmp_path / "handoff" / "exports.tar.gz").exists()


def test_build_modes_are_mutually_exclusive(tmp_path: Path, monkeypatch) -> None:
    init_project(tmp_path)

    conflict_result = _run_build(
        tmp_path,
        monkeypatch,
        ["--part", "example_block", "--changed"],
    )
    assert conflict_result.exit_code != 0
    assert "Choose one build profile mode only" in conflict_result.output


def test_changed_mode_without_cache_builds_all_definitions(tmp_path: Path, monkeypatch) -> None:
    init_project(tmp_path)

    result = _run_build(tmp_path, monkeypatch, ["--changed", "--no-bundle", "--no-cache", "--no-snapshots"])
    assert result.exit_code == 0
    assert "Exported 1 STEP files to" in result.output
