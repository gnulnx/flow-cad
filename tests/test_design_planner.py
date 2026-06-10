from __future__ import annotations

import json

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
