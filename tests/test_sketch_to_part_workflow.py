from __future__ import annotations

from pathlib import Path

from build123d import Box, export_step

from flow_cad.viewer.app import (
    _append_design_plan_for_turn,
    _append_visual_evidence_request_for_plan,
    _continue_annotated_draft_after_visual_evidence,
    _should_request_visual_evidence_before_deterministic_draft,
)
from flow_cad.viewer.service import ViewerService
from flow_cad.viewer.threads import DesignThreadService


def _tiny_png_data_url() -> str:
    return (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X9nSAAAAAASUVORK5CYII="
    )


def _lobed_sketch_annotations() -> list[dict[str, object]]:
    return [
        {
            "kind": "freehand",
            "points": [
                {"x": 0.18, "y": 0.50},
                {"x": 0.25, "y": 0.27},
                {"x": 0.44, "y": 0.16},
                {"x": 0.57, "y": 0.19},
                {"x": 0.72, "y": 0.32},
                {"x": 0.90, "y": 0.50},
                {"x": 0.72, "y": 0.68},
                {"x": 0.58, "y": 0.86},
                {"x": 0.43, "y": 0.82},
                {"x": 0.24, "y": 0.66},
            ],
        },
        {"kind": "circle", "x": 0.30, "y": 0.36, "radius": 0.03},
        {"kind": "circle", "x": 0.74, "y": 0.62, "radius": 0.03},
        {
            "kind": "freehand",
            "points": [
                {"x": 0.50, "y": 0.72},
                {"x": 0.53, "y": 0.76},
                {"x": 0.56, "y": 0.72},
                {"x": 0.53, "y": 0.68},
            ],
        },
    ]


def test_sketch_to_part_real_step_visual_evidence_creates_profile_preview(tmp_path) -> None:
    step_path = tmp_path / "example" / "exports" / "step" / "example" / "example_block.step"
    step_path.parent.mkdir(parents=True, exist_ok=True)
    export_step(Box(20, 20, 5), step_path)

    def fake_converter(_step_path: Path, stl_path: Path) -> Path:
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        stl_path.write_text("solid preview\nendsolid preview\n", encoding="utf-8")
        return stl_path

    viewer_service = ViewerService(tmp_path, converter=fake_converter)
    design_threads = DesignThreadService(viewer_service)
    thread_id = design_threads.create_thread({"title": "Real STEP sketch smoke"})["thread_id"]
    prepared = design_threads.begin_chat_turn(
        thread_id,
        {
            "message": (
                "Create a 10mm thick 100 x 65mm plate shaped similar to this sketch "
                "with M4 counterbore holes."
            ),
            "context_snapshot": {
                "visible_part_ids": ["example_block"],
                "selected_part_ids": ["example_block"],
                "annotations": _lobed_sketch_annotations(),
            },
        },
    )
    plan_message = _append_design_plan_for_turn(design_threads, thread_id, prepared)

    assert _should_request_visual_evidence_before_deterministic_draft(plan_message, prepared) is True
    request_bundle = _append_visual_evidence_request_for_plan(design_threads, thread_id, prepared, plan_message)
    request = request_bundle["request"]
    completion = design_threads.fulfill_visual_evidence_request(
        thread_id,
        request["request_id"],
        {
            "source": "agent",
            "view": "top",
            "content_type": "image/png",
            "data_url": _tiny_png_data_url(),
            "width": 960,
            "height": 720,
            "metadata": {**request["metadata"], "render_context": "viewport-canvas"},
        },
    )
    continuation = _continue_annotated_draft_after_visual_evidence(
        design_threads,
        viewer_service,
        thread_id,
        completion,
    )

    assert continuation is not None
    operations = continuation["draft_result"]["applied_operations"]
    profile_points = operations[0]["parameters"]["profile_points"]
    assert operations[0]["name"] == "create_sketch_profile"
    assert operations[0]["endpoint"] == "profile"
    assert len(profile_points) > 6
    assert profile_points[0] == profile_points[-1]
    assert any(operation["name"] == "add_counterbore" for operation in operations)

    transaction_token = continuation["draft_result"]["transaction_token"]
    status = viewer_service.draft_transaction_status(transaction_token)
    assert status["status"] == "open"
    assert Path(status["preview_step_path"]).exists()
