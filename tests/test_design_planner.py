from __future__ import annotations

import json
import subprocess
import sys

import pytest
from flow_cad import design_planner


def test_plan_design_turn_robot_head_is_questions_plan() -> None:
    payload = design_planner.plan_design_turn("Make a robot head")

    assert payload["plan_type"] == "questions"
    assert len(payload["steps"]) >= 5
    step_ids = {step["step_id"] for step in payload["steps"]}
    assert "question-purpose" in step_ids
    assert "question-size" in step_ids
    assert "question-mounting" in step_ids
    assert "question-sensors-openings" in step_ids
    assert "question-style-manufacturing" in step_ids
    assert json.dumps(payload)


def test_plan_design_turn_deterministic_plate_prompt_is_draft_plan() -> None:
    payload = design_planner.plan_design_turn("create a plate that is 100 x 120 x 10 mm")

    assert payload["plan_type"] == "draft_plan"
    operation_ids = [step["operation_id"] for step in payload["steps"] if step["operation_id"]]
    assert "create_box" in operation_ids
    assert "preview" in operation_ids
    create_box_step = next(step for step in payload["steps"] if step["operation_id"] == "create_box")
    assert create_box_step["parameters"]["length"] == 100.0
    assert create_box_step["parameters"]["width"] == 120.0
    assert create_box_step["parameters"]["height"] == 10.0
    assert json.dumps(payload)


def test_plan_design_turn_annotated_counterbore_prompt_includes_intent_steps_and_ops() -> None:
    payload = design_planner.plan_design_turn(
        "Use this drawing to add counterbore points from the sketch",
        context_snapshot={
            "annotations": [
                {"kind": "circle", "x": 0.25, "y": 0.33, "radius": 0.04},
                {"kind": "circle", "x": 0.75, "y": 0.66, "radius": 0.04},
            ],
            "draft_transaction_token": "tx-123",
        },
    )

    assert payload["plan_type"] == "draft_plan"
    step_ids = {step["step_id"] for step in payload["steps"]}
    assert "derive_footprint_from_annotations" in step_ids
    assert "locate_hole_marks" in step_ids
    operation_ids = [step["operation_id"] for step in payload["steps"] if step["operation_id"]]
    assert "create_sketch_profile" in operation_ids
    assert operation_ids.index("create_sketch_profile") < operation_ids.index("add_counterbore")
    assert "add_counterbore" in operation_ids
    assert "preview" in operation_ids
    assert json.dumps(payload)


def test_plan_design_turn_viewport_plate_prompt_with_annotations_is_draft_plan() -> None:
    payload = design_planner.plan_design_turn(
        (
            "Id like to create a 10mm thick part on the xy plane similar to the design in the viewport, "
            "roughly 65 x 100mm, with M4 counterbore screws in the rough positions shown."
        ),
        context_snapshot={
            "annotations": [
                {"kind": "freehand", "points": [{"x": 0.1, "y": 0.2}, {"x": 0.8, "y": 0.7}]},
                {"kind": "circle", "x": 0.25, "y": 0.35, "radius": 0.04},
            ],
        },
    )

    assert payload["plan_type"] == "draft_plan"
    step_ids = {step["step_id"] for step in payload["steps"]}
    assert "derive_footprint_from_annotations" in step_ids
    assert "locate_hole_marks" in step_ids


def test_plan_design_turn_annotation_outline_prompt_is_profile_first_draft_plan() -> None:
    payload = design_planner.plan_design_turn(
        "Please cleanly follow this sketch outline",
        context_snapshot={
            "annotations": [
                {"kind": "freehand", "points": [{"x": 0.1, "y": 0.2}, {"x": 0.9, "y": 0.8}]},
            ],
        },
    )

    assert payload["plan_type"] == "draft_plan"
    operation_ids = [step["operation_id"] for step in payload["steps"] if step["operation_id"]]
    assert operation_ids == ["create_sketch_profile", "preview"]
    assert json.dumps(payload)


def test_plan_design_turn_revise_sketch_following_curves_is_draft_plan_with_profile_step() -> None:
    payload = design_planner.plan_design_turn(
        "it is not following the curves from the original sketch",
        context_snapshot={
            "draft_transaction_token": "tx-789",
        },
    )

    assert payload["plan_type"] == "draft_plan"
    operation_ids = [step["operation_id"] for step in payload["steps"] if step["operation_id"]]
    assert "create_sketch_profile" in operation_ids
    assert "preview" in operation_ids
    assert "add_hole" not in operation_ids
    assert json.dumps(payload)


@pytest.mark.parametrize("case", design_planner.intent_planner_verification_cases(), ids=lambda case: case["id"])
def test_intent_planner_verification_matrix(case: dict[str, object]) -> None:
    payload = design_planner.plan_design_turn(
        str(case["message"]),
        case.get("context_snapshot") if isinstance(case.get("context_snapshot"), dict) else None,
    )
    coverage = payload["coverage"]
    assert payload["plan_type"] == case["expect_plan_type"]
    assert coverage["execution_readiness"] == case["expect_readiness"]
    intent_kinds = {item["kind"] for item in payload["intent_items"]}
    for expected_kind in case.get("expect_kinds", ()):
        assert expected_kind in intent_kinds
    assert "summary" in coverage
    assert isinstance(payload["verification"], list)
    assert json.dumps(payload)


@pytest.mark.parametrize(
    ("message", "expected_ready", "expected_statuses"),
    [
        (
            "make a 90 x 40 x 3 mm plate with two M3 holes 8mm from the front edge",
            "ready",
            {"base_geometry": "covered", "hole_pattern": "covered"},
        ),
        (
            "make a 120 x 80 x 4 mm plate with four M4 corner holes and five louvers",
            "ready",
            {"base_geometry": "covered", "hole_pattern": "covered", "louver_pattern": "covered"},
        ),
        (
            "add four 25mm tall standoffs in the corners with M3 side holes",
            "partial_requires_review",
            {"boss_or_pillar": "partial", "hole_pattern": "partial"},
        ),
        (
            "add a 3mm recessed insert pocket and keep all screw holes clear of the interior",
            "partial_requires_review",
            {"insert_or_recess": "unsupported", "constraint": "verification_only"},
        ),
        (
            "fillet every edge, shell it hollow, and loft a curved front fairing",
            "partial_requires_review",
            {"advanced_surface_modeling": "unsupported"},
        ),
    ],
)
def test_intent_planner_easy_to_complex_coverage(
    message: str,
    expected_ready: str,
    expected_statuses: dict[str, str],
) -> None:
    payload = design_planner.plan_design_turn(message)
    coverage = payload["coverage"]
    by_kind = {item["kind"]: item for item in payload["intent_items"]}

    assert coverage["execution_readiness"] == expected_ready
    assert coverage["can_auto_execute"] is (expected_ready == "ready")
    for kind, status in expected_statuses.items():
        assert by_kind[kind]["status"] == status
    assert coverage["total_count"] >= len(expected_statuses)


def test_complex_pillar_prompt_is_not_silently_auto_executable() -> None:
    payload = design_planner.plan_design_turn(
        (
            "Add pillars in all 4 corners. Each pillar should be 40mm tall. Pillars should be insert 3mm "
            "for plates that attach to the pillars on all 4 sides. Each pillar needs 4 mounting holes. "
            "2 on each external face. The M4 mounting holes should not overlap on the interior of the pillars."
        )
    )

    coverage = payload["coverage"]
    by_kind = {item["kind"]: item for item in payload["intent_items"]}

    assert payload["plan_type"] == "draft_plan"
    assert coverage["can_auto_execute"] is False
    assert coverage["execution_readiness"] == "partial_requires_review"
    assert by_kind["boss_or_pillar"]["status"] == "partial"
    assert by_kind["insert_or_recess"]["status"] == "unsupported"
    assert by_kind["constraint"]["status"] == "verification_only"
    assert "pillars" in coverage["blocking_items"]
    assert "inserts" in coverage["blocking_items"]


def test_selected_context_satisfies_target_geometry_for_feature_addition() -> None:
    payload = design_planner.plan_design_turn(
        "Add pillars in all 4 corners with M4 mounting holes",
        context_snapshot={"selected_part_ids": ["example_block"]},
    )
    by_kind = {item["kind"]: item for item in payload["intent_items"]}

    assert by_kind["base_geometry"]["status"] == "covered"
    assert by_kind["base_geometry"]["parameters"]["target_context"] == "selected_or_active_draft"
    assert "base-geometry" not in payload["coverage"]["blocking_items"]
    assert payload["coverage"]["can_auto_execute"] is False


def test_verify_intent_planner_cases_reports_all_green() -> None:
    report = design_planner.verify_intent_planner_cases()

    assert report["ok"] is True
    assert report["case_count"] >= 7
    assert all(result["ok"] for result in report["results"])


def test_design_planner_module_verify_entrypoint() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "flow_cad.design_planner", "--verify"],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["ok"] is True
    assert payload["case_count"] >= 7
