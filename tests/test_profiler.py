import json
import time
from pathlib import Path

from click.testing import CliRunner

from flow_cad.cli import flow
from flow_cad.profiler import FlowCadProfiler, format_profile_summary, load_latest_build_profile, write_build_profile
from flow_cad.project import init_project


def test_profiler_writes_latest_profile_and_summary(tmp_path: Path) -> None:
    profiler = FlowCadProfiler(
        project_id="demo",
        project_root=tmp_path,
        command="flow cad build",
        build_profile="active",
    )

    with profiler.measure("part_generation", "panel", part_id="panel"):
        time.sleep(0.001)
    profiler.record_skip("stl_export", "panel.stl", part_id="panel", reason="no_stl_requested")
    profiler.finish("ok")

    paths = write_build_profile(profiler, tmp_path / ".flow")
    latest = load_latest_build_profile(tmp_path / ".flow")

    assert paths.profile_path.exists()
    assert paths.latest_path.exists()
    assert latest is not None
    assert latest["schema_version"] == 1
    assert latest["status"] == "ok"
    assert latest["summary"]["totals_by_phase_ms"]["part_generation"] > 0
    assert latest["events"][1]["status"] == "skipped"
    assert latest["events"][1]["metadata"]["reason"] == "no_stl_requested"
    assert "part_generation [panel]: panel" in format_profile_summary(latest)


def test_flow_cad_build_records_profile_and_profile_command_reads_it(tmp_path: Path) -> None:
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path):
        project_root = Path.cwd()
        init_project(project_root)

        build_result = runner.invoke(
            flow,
            ["cad", "build", "--no-bundle", "--no-snapshots"],
            catch_exceptions=False,
        )

        assert build_result.exit_code == 0
        assert "Wrote build profile" in build_result.output

        latest_path = project_root / ".flow" / "profiles" / "latest-build-profile.json"
        profile_data = json.loads(latest_path.read_text(encoding="utf-8"))
        phases = {event["phase"] for event in profile_data["events"]}

        assert profile_data["status"] == "ok"
        assert profile_data["command"] == "flow cad build"
        assert profile_data["build_profile"] == "all"
        assert {
            "part_generation",
            "step_export",
            "stl_export",
            "report_generation",
            "active_cache_write",
            "viewer_cache_update",
            "interference_check",
            "validator",
            "project_tests",
        }.issubset(phases)

        part_events = [event for event in profile_data["events"] if event["phase"] == "part_generation"]
        assert part_events[0]["part_id"] == "example_block"

        step_events = [event for event in profile_data["events"] if event["phase"] == "step_export"]
        assert step_events[0]["metadata"]["artifact_cache_status"] == "rebuilt"
        assert step_events[0]["metadata"]["artifact_cache_reason"] == "full_build"

        summary_result = runner.invoke(flow, ["cad", "profile", "--last"], catch_exceptions=False)
        assert summary_result.exit_code == 0
        assert "Slowest operations:" in summary_result.output
        assert "step_export" in summary_result.output

        json_result = runner.invoke(flow, ["cad", "profile", "--json"], catch_exceptions=False)
        assert json_result.exit_code == 0
        assert json.loads(json_result.output)["profile_id"] == profile_data["profile_id"]


def test_failed_build_still_writes_failed_profile(tmp_path: Path) -> None:
    runner = CliRunner()

    with runner.isolated_filesystem(temp_dir=tmp_path):
        project_root = Path.cwd()
        init_project(project_root)

        build_result = runner.invoke(flow, ["cad", "build", "--profile", "missing"])

        assert build_result.exit_code != 0
        profile_data = json.loads(
            (project_root / ".flow" / "profiles" / "latest-build-profile.json").read_text(encoding="utf-8")
        )
        assert profile_data["status"] == "failed"
        assert profile_data["events"][0]["phase"] == "build_total"
        assert profile_data["events"][0]["status"] == "failed"
