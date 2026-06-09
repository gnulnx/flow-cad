import json
import os
import time
from pathlib import Path

from click.testing import CliRunner

from flow_cad.cli import flow
from flow_cad.draft_geometry import DraftGeometryStore
from flow_cad.project import init_project, load_project
from flow_cad.validation import (
    ValidatorMetadata,
    ValidatorReport,
    ValidationFactProvider,
    coerce_validator_result,
    placement_issues,
    validate_panel_facts,
)


def _invoke_in(project_root: Path, args: list[str]):
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=project_root.parent):
        cwd = Path.cwd()
        if cwd != project_root:
            os.chdir(project_root)
        return runner.invoke(flow, args, catch_exceptions=False)


def test_validator_contracts_serialize_counts_and_legacy_results() -> None:
    metadata = ValidatorMetadata(
        id="demo",
        family="panel",
        description="Demo validator.",
        inputs=("draft",),
        tags=("fast",),
    )

    report = coerce_validator_result(
        [{"message": "hole is wrong", "part_id": "panel_a", "expected": 4.2, "actual": 3.0, "units": "mm"}],
        metadata,
        elapsed_ms=12.5,
    )
    payload = report.to_dict()

    assert payload["schema_version"] == 1
    assert payload["ok"] is False
    assert payload["issue_counts"] == {"error": 1, "warning": 0, "info": 0, "total": 1}
    assert payload["issues"][0]["check_id"] == "legacy_sequence_issue"
    assert payload["issues"][0]["expected"] == 4.2

    slow_report = ValidatorReport(metadata=ValidatorMetadata("slow", "panel", "Slow validator.", budget_ms=1.0), elapsed_ms=5.0)
    assert slow_report.profile_metadata()["over_budget"] is True


def test_flow_init_copies_structured_validator_template(tmp_path: Path) -> None:
    init_project(tmp_path)

    manifest = (tmp_path / "flowcad.project.yaml").read_text(encoding="utf-8")

    assert "project-panel-example: flow.validators.panel_example:validate_project_panel_example" in manifest
    assert (tmp_path / "flow" / "validators" / "panel_example.py").exists()
    assert "ValidatorMetadata" in (tmp_path / "flow" / "validators" / "project.py").read_text(encoding="utf-8")


def test_flow_validate_lists_and_runs_fresh_project_without_exports_or_cache(tmp_path: Path, monkeypatch) -> None:
    init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    listed = runner.invoke(flow, ["validate", "list"], catch_exceptions=False)
    listed_by_tag = runner.invoke(flow, ["validate", "list", "--tag", "example", "--json"], catch_exceptions=False)
    run_by_family = runner.invoke(flow, ["validate", "run", "--family", "project", "--json"], catch_exceptions=False)
    result = runner.invoke(flow, ["validate", "run", "project", "--json"], catch_exceptions=False)

    assert listed.exit_code == 0
    assert "panel-basic" in listed.output
    assert "project-panel-example" in listed.output
    assert listed_by_tag.exit_code == 0
    assert json.loads(listed_by_tag.output)["validators"][0]["id"] == "project-panel-example"
    assert run_by_family.exit_code == 0
    assert json.loads(run_by_family.output)["reports"][0]["metadata"]["family"] == "project"
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["reports"][0]["metadata"]["id"] == "project"
    assert (tmp_path / ".flow" / "profiles" / "latest-validator-profile.json").exists()
    assert not (tmp_path / ".flow" / "registry.db").exists()
    assert not any(path.is_file() for path in (tmp_path / "exports").rglob("*"))


def test_flow_validate_panel_basic_uses_step_and_profile_command_reads_validator_profile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    build = runner.invoke(
        flow,
        ["cad", "build", "--part", "example_block", "--no-stl", "--no-snapshots", "--no-reports"],
        catch_exceptions=False,
    )
    result = runner.invoke(
        flow,
        ["validate", "run", "panel-basic", "--part", "example_block", "--json"],
        catch_exceptions=False,
    )
    summary = runner.invoke(flow, ["cad", "profile", "--last"], catch_exceptions=False)

    assert build.exit_code == 0
    assert result.exit_code == 0
    payload = json.loads(result.output)
    report = payload["reports"][0]
    assert report["ok"] is True
    assert report["metadata"]["id"] == "panel-basic"
    assert report["input_summary"]["geometry_authority"] == "step"
    assert (tmp_path / ".flow" / "profiles" / "latest-validator-profile.json").exists()
    assert summary.exit_code == 0
    assert "Flow CAD profile" in summary.output
    assert "panel-basic" in summary.output


def test_fact_providers_cover_cache_step_draft_and_stale_cache(tmp_path: Path, monkeypatch) -> None:
    init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    build = runner.invoke(flow, ["cad", "build", "--no-bundle", "--no-snapshots"], catch_exceptions=False)
    assert build.exit_code == 0

    project = load_project(tmp_path, fallback_to_bundled=False)
    facts = ValidationFactProvider(project)
    cache = facts.active_cache_row("example_block")
    step = facts.step_bounding_box("example_block")
    snap = facts.step_snap_features("example_block")
    draft_store = DraftGeometryStore(project)
    draft = draft_store.create_box_part(part_id="fact_panel", length=20.0, width=10.0, height=2.0)
    draft_facts = facts.draft_facts(str(draft["draft_token"]))
    placements = facts.viewer_placements(part_id="example_block")
    missing = facts.step_bounding_box("missing_part")

    assert cache.facts is not None
    assert cache.facts["geometry_authority"] == "cache"
    assert step.facts is not None
    assert step.facts["geometry_authority"] == "step"
    assert snap.facts is not None
    assert snap.facts["geometry_authority"] == "step"
    assert "features" in snap.facts
    assert draft_facts.facts is not None
    assert draft_facts.facts["geometry_authority"] == "draft"
    assert placements.facts is not None
    assert placements.facts["placements"][0]["part_id"] == "example_block"
    assert missing.facts is None
    assert missing.issues[0].check_id == "definition_missing"

    source = tmp_path / "flow" / "parts" / "example.py"
    future = time.time() + 10_000_000
    os.utime(source, (future, future))
    stale = facts.active_cache_row("example_block")

    assert any(issue.check_id == "cache_source_stale" for issue in stale.issues)
    assert "flow/parts/example.py" in stale.issues[0].actual


def test_panel_validator_uses_draft_transaction_acceptance_facts() -> None:
    runner = CliRunner()
    with runner.isolated_filesystem() as root:
        project_root = Path(root)
        init_project(project_root)
        project = load_project(project_root, fallback_to_bundled=False)
        store = DraftGeometryStore(project)
        begun = store.begin_transaction(part_id="accepted_panel")
        token = str(begun["transaction_token"])
        store.transaction_create_box(token, length=120.0, width=45.0, height=3.0)
        store.transaction_add_hole(token, face="top", x=12.0, y=8.0, diameter=4.2)
        accepted = store.accept_transaction(token)
        cli_result = runner.invoke(
            flow,
            ["validate", "run", "panel-basic", "--draft-transaction", token, "--json"],
            catch_exceptions=False,
        )
        manifest_path = Path(str(accepted["acceptance_manifest_path"]))
        draft = json.loads(manifest_path.read_text(encoding="utf-8"))["draft"]

    cli_payload = json.loads(cli_result.output)
    report = validate_panel_facts(
        draft,
        part_id="accepted_panel",
        expected_dimensions_mm=(120.0, 45.0, 3.0),
        expected_holes=[{"feature_id": "hole_1", "face": "top", "x": 12.0, "y": 8.0, "diameter": 4.2}],
        min_edge_distance_mm=2.0,
    )
    failing = validate_panel_facts(
        draft,
        part_id="accepted_panel",
        expected_holes=[{"feature_id": "hole_1", "diameter": 3.0}],
        keepout_rectangles=[{"id": "switch", "face": "top", "x_min": 10.0, "x_max": 14.0, "y_min": 6.0, "y_max": 10.0}],
    )

    assert cli_result.exit_code == 0
    assert cli_payload["reports"][0]["input_summary"]["geometry_authority"] == "draft"
    assert cli_payload["reports"][0]["elapsed_ms"] < 2000.0
    assert report.ok is True
    assert failing.ok is False
    assert {issue.check_id for issue in failing.issues} >= {
        "panel_hole_diameter_mismatch",
        "panel_keepout_violation",
    }


def test_runner_reports_missing_validator_and_missing_manifest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    missing_manifest = runner.invoke(flow, ["validate", "list"])
    init_project(tmp_path)
    missing_validator = runner.invoke(flow, ["validate", "run", "missing-validator"])

    assert missing_manifest.exit_code != 0
    assert "flowcad.project.yaml" in missing_manifest.output
    assert missing_validator.exit_code != 0
    assert "Focused validator not found" in missing_validator.output


def test_flow_validate_failure_json_is_machine_readable(tmp_path: Path, monkeypatch) -> None:
    init_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    result = runner.invoke(flow, ["validate", "run", "panel-basic", "--json"], catch_exceptions=False)
    payload = json.loads(result.output)

    assert result.exit_code == 1
    assert payload["ok"] is False
    assert payload["reports"][0]["issues"][0]["check_id"] == "panel_part_required"


def test_placement_helper_reports_mispositioned_and_missing_neighbors() -> None:
    issues = placement_issues(
        [
            {
                "name": "panel",
                "part_id": "panel_a",
                "location": [1.0, 0.0, 0.0],
                "rotation": [0.0, 0.0, 5.0],
            }
        ],
        part_id="panel_a",
        expected_translation=(0.0, 0.0, 0.0),
        expected_rotation=(0.0, 0.0, 0.0),
        expected_neighbor_ids=["panel_b"],
    )

    assert {issue.check_id for issue in issues} == {
        "placement_translation_mismatch",
        "placement_rotation_mismatch",
        "placement_neighbor_missing",
    }
