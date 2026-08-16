import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from flow_cad.viewer.agent_runtime import FakeAgentRuntimeClient
from flow_cad.viewer.app import (
    create_app,
)
import flow_cad.viewer.app as viewer_app
from flow_cad.viewer.service import ViewerService


def _write_example_step(project_root: Path) -> Path:
    path = project_root / "example" / "exports" / "step" / "example" / "example_block.step"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
    return path


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


def test_viewer_design_threads_crud_and_list(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    initial = client.get("/api/design-threads").json()
    assert initial["count"] == 0
    assert initial["threads"] == []

    create_response = client.post(
        "/api/design-threads",
        json={
            "title": "Panel exploration",
            "tags": ["draft", "cad"],
            "linked_part_ids": ["example_block"],
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()

    thread_id = created["thread_id"]
    thread_dir = service.project.paths.local_state / "design-threads" / thread_id
    assert created["title"] == "Panel exploration"
    assert created["thread_id"] == thread_id
    assert created["tags"] == ["draft", "cad"]
    assert thread_dir.is_dir()
    assert (thread_dir / "thread.json").exists()

    list_response = client.get("/api/design-threads").json()
    assert list_response["count"] == 1
    assert list_response["threads"][0]["thread_id"] == thread_id

    get_response = client.get(f"/api/design-threads/{thread_id}").json()
    assert get_response["thread_id"] == thread_id
    assert get_response["message_count"] == 0
    assert get_response["snapshot_count"] == 0
    assert get_response["messages"] == []


def test_design_thread_validate_and_build_buttons_run_draft_mode_actions(tmp_path, monkeypatch) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))
    thread_id = client.post("/api/design-threads", json={"title": "Draft mode"}).json()["thread_id"]
    calls: list[list[str]] = []

    def fake_run_flow_cli(project_root: Path, args: list[str]) -> dict[str, object]:
        calls.append(args)
        if args[:2] == ["validate", "run"]:
            return {
                "command": "python -m flow_cad.cli " + " ".join(args),
                "argv": [],
                "exit_code": 0,
                "stdout": json.dumps({"ok": True, "reports": [], "profile": {"profile_id": "validator-profile"}}),
                "stderr": "",
                "ok": True,
            }
        return {
            "command": "python -m flow_cad.cli " + " ".join(args),
            "argv": [],
            "exit_code": 0,
            "stdout": "Exported 1 STEP files\n",
            "stderr": "",
            "ok": True,
        }

    monkeypatch.setattr(viewer_app, "_run_flow_cli", fake_run_flow_cli)

    validate = client.post(
        f"/api/design-threads/{thread_id}/validate",
        json={"draft_transaction_token": "draft-1", "part_id": "example_block"},
    )
    build = client.post(
        f"/api/design-threads/{thread_id}/build",
        json={"draft_transaction_token": "draft-1", "part_id": "example_block"},
    )

    assert validate.status_code == 200
    assert validate.json()["ok"] is True
    assert build.status_code == 200
    assert build.json()["ok"] is True
    assert calls == [
        ["validate", "run", "panel-basic", "--json", "--draft-transaction", "draft-1"],
        ["validate", "run", "panel-basic", "--json", "--draft-transaction", "draft-1"],
        ["cad", "build", "--part", "example_block", "--no-reports"],
    ]
    thread = client.get(f"/api/design-threads/{thread_id}").json()
    summaries = [
        message["content"]["summary"]
        for message in thread["messages"]
        if isinstance(message.get("content"), dict) and "summary" in message["content"]
    ]
    assert "Validation passed for draft transaction draft-1." in summaries
    assert "Build passed for part example_block." in summaries


def test_viewer_design_threads_append_messages_and_reload_from_disk(tmp_path) -> None:
    _write_example_step(tmp_path)

    create_payload = {
        "title": "Reload test",
        "linked_part_ids": ["example_block"],
    }

    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    create_response = client.post("/api/design-threads", json=create_payload)
    assert create_response.status_code == 200
    thread_id = create_response.json()["thread_id"]

    first_message = client.post(
        f"/api/design-threads/{thread_id}/messages",
        json={
            "type": "user_message",
            "role": "user",
            "content": {"text": "Start panel changes"},
        },
    )
    assert first_message.status_code == 200

    second_message = client.post(
        f"/api/design-threads/{thread_id}/messages",
        json={
            "type": "assistant_message",
            "role": "assistant",
            "content": {"text": "Captured baseline"},
        },
    )
    assert second_message.status_code == 200

    thread_dir = service.project.paths.local_state / "design-threads" / thread_id
    messages_path = thread_dir / "messages.jsonl"
    assert messages_path.exists()
    assert len(messages_path.read_text(encoding="utf-8").splitlines()) == 2

    reloaded_get = TestClient(create_app(service=ViewerService(tmp_path))).get(
        f"/api/design-threads/{thread_id}"
    )
    assert reloaded_get.status_code == 200
    reloaded = reloaded_get.json()

    assert reloaded["message_count"] == 2
    assert reloaded["messages"][0]["type"] == "user_message"
    assert reloaded["messages"][1]["type"] == "assistant_message"


def test_viewer_design_threads_patch_title_and_archive(tmp_path) -> None:
    _write_example_step(tmp_path)
    client = TestClient(create_app(service=ViewerService(tmp_path)))

    create_response = client.post(
        "/api/design-threads",
        json={"title": "Before", "tags": ["work-in-progress"]},
    )
    assert create_response.status_code == 200
    thread_id = create_response.json()["thread_id"]

    patched = client.patch(
        f"/api/design-threads/{thread_id}",
        json={"title": "After rename", "archived": True},
    )
    assert patched.status_code == 200
    payload = patched.json()
    assert payload["title"] == "After rename"
    assert payload["archived"] is True

    listed = client.get("/api/design-threads").json()
    listing = next(item for item in listed["threads"] if item["thread_id"] == thread_id)
    assert listing["title"] == "After rename"
    assert listing["archived"] is True


def test_viewer_design_threads_keep_ids_inside_thread_store(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    create_response = client.post(
        "/api/design-threads",
        json={"thread_id": "../../outside", "title": "Contained"},
    )
    assert create_response.status_code == 200
    thread_id = create_response.json()["thread_id"]
    assert "/" not in thread_id
    assert "\\" not in thread_id

    snapshot_response = client.post(
        f"/api/design-threads/{thread_id}/context-snapshots",
        json={
            "snapshot_id": "../../bad",
            "visible_part_ids": ["example_block"],
            "selected_part_ids": ["example_block"],
        },
    )
    assert snapshot_response.status_code == 200
    snapshot_id = snapshot_response.json()["snapshot_id"]
    assert "/" not in snapshot_id
    assert "\\" not in snapshot_id

    store = (service.project.paths.local_state / "design-threads").resolve()
    thread_path = (store / thread_id / "thread.json").resolve()
    snapshot_path = (store / thread_id / "context-snapshots" / f"{snapshot_id}.json").resolve()
    assert thread_path.is_relative_to(store)
    assert snapshot_path.is_relative_to(store)
    assert not (tmp_path.parent / "outside").exists()
    assert not (tmp_path.parent / "bad.json").exists()


def test_viewer_design_threads_context_snapshot_expands_viewer_state(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    create_response = client.post("/api/design-threads", json={"title": "Snapshot check"})
    assert create_response.status_code == 200
    thread_id = create_response.json()["thread_id"]

    transaction = client.post("/api/draft-transactions", json={"part_id": "example_block"}).json()
    transaction_token = transaction["transaction_token"]
    create_box = client.post(
        f"/api/draft-transactions/{transaction_token}/box",
        json={"length": 120.0, "width": 45.0, "height": 3.0},
    )
    assert create_box.status_code == 200

    snapshot_response = client.post(
        f"/api/design-threads/{thread_id}/context-snapshots",
        json={
            "camera": {
                "position": [1.0, 2.0, 3.0],
                "target": [0.0, 0.0, 0.0],
            },
            "visible_part_ids": ["example_block", "ghost_part"],
            "selected_part_ids": ["example_block"],
            "measurements": [
                {
                    "id": "m-1",
                    "value": {
                        "length_mm": 120.0,
                    },
                }
            ],
            "draft_transaction_token": transaction_token,
            "viewport_size": {"width": 1024, "height": 768},
        },
    )
    assert snapshot_response.status_code == 200

    snapshot = snapshot_response.json()
    assert snapshot["thread_id"] == thread_id
    assert snapshot["schema_version"] == 1
    assert snapshot["project"]["project_id"] == "flow_example"
    assert snapshot["project"]["revision"] == 0
    assert snapshot["draft_transaction"]["status"] == "open"

    visible = snapshot["parts"]["visible"]
    visible_lookup = {entry["part_id"]: entry for entry in visible}
    assert visible_lookup["example_block"]["found"] is True
    assert visible_lookup["example_block"]["geometry_authority"] == "step_kernel"
    assert visible_lookup["example_block"]["source_context_available"] is True
    assert visible_lookup["ghost_part"]["found"] is False

    snapshot_id = snapshot["snapshot_id"]
    snapshot_path = (
        service.project.paths.local_state
        / "design-threads"
        / thread_id
        / "context-snapshots"
        / f"{snapshot_id}.json"
    )
    assert snapshot_path.exists()


def test_viewer_design_threads_chat_fallback_persists_runtime_assistant_and_view_context(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    runtime = FakeAgentRuntimeClient(
        [
            {"type": "assistant_delta", "text": "Runtime-backed fallback response."},
            {"type": "done"},
        ]
    )
    client = TestClient(create_app(service=service, agent_runtime_client=runtime))

    create_response = client.post("/api/design-threads", json={"title": "Chat check"})
    assert create_response.status_code == 200
    thread_id = create_response.json()["thread_id"]

    chat_response = client.post(
        f"/api/design-threads/{thread_id}/chat",
        json={
            "message": "Move the holes to the front face.",
            "context_snapshot": {
                "visible_part_ids": ["example_block"],
                "selected_part_ids": ["example_block"],
                "viewport_screenshot": {
                    "kind": "viewport_screenshot",
                    "content_type": "image/png",
                    "data_url": "data:image/png;base64,AAA=",
                },
                "viewport_size": {"width": 640, "height": 480},
            },
        },
    )
    assert chat_response.status_code == 200
    payload = chat_response.json()

    assert payload["messages"][0]["type"] == "user_message"
    assert payload["messages"][0]["metadata"]["context_snapshot_id"] == payload["context_snapshot"]["snapshot_id"]
    assert payload["messages"][0]["metadata"]["viewport_screenshot"] is True
    assert payload["messages"][1]["type"] == "design_plan"
    assert payload["messages"][1]["content"]["plan_type"] == "concept_plan"
    assert payload["messages"][2]["type"] == "assistant_message"
    assert payload["messages"][2]["role"] == "assistant"
    assert payload["messages"][2]["metadata"]["runtime"] == "FakeAgentRuntimeClient"
    assert payload["messages"][2]["content"] == "Runtime-backed fallback response."
    assert payload["events"][-1]["type"] == "done"
    assert payload["thread"]["message_count"] == 3

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    assert [message["type"] for message in reloaded["messages"]] == [
        "user_message",
        "design_plan",
        "assistant_message",
    ]
    assert reloaded["context_snapshots"][0]["viewer_state"]["viewport_screenshot"]["data_url"].startswith("data:image/png")


def test_viewer_design_threads_chat_creates_deterministic_base_plate_draft(tmp_path) -> None:
    _write_example_step(tmp_path)

    def fake_converter(step_path: Path, stl_path: Path) -> Path:
        assert step_path.exists()
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        stl_path.write_text("solid preview\nendsolid preview\n", encoding="utf-8")
        return stl_path

    service = ViewerService(tmp_path, converter=fake_converter)

    runtime = FakeAgentRuntimeClient(
        [
            {"type": "assistant_delta", "text": "This should not be used."},
            {"type": "done"},
        ]
    )
    client = TestClient(create_app(service=service, agent_runtime_client=runtime))

    thread_id = client.post("/api/design-threads", json={"title": "Draft from chat"}).json()["thread_id"]

    response = client.post(
        f"/api/design-threads/{thread_id}/chat",
        json={
            "message": "Please create a base plate that is 100mm x 100mm x 10mm thick",
            "context_snapshot": {
                "visible_part_ids": [],
                "selected_part_ids": [],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["draft_result"]["ok"] is True
    assert payload["draft_result"]["part_id"] == "base_plate"
    assert payload["draft_preview_model"]["part_id"] == "base_plate"
    assert payload["draft_preview_model"]["dimensions"]["length_mm"] == 100.0
    assert payload["draft_preview_model"]["dimensions"]["width_mm"] == 100.0
    assert payload["draft_preview_model"]["dimensions"]["height_mm"] == 10.0

    message_types = [message["type"] for message in payload["messages"]]
    assert message_types == [
        "user_message",
        "design_plan",
        "draft_event",
        "draft_event",
        "draft_event",
        "assistant_message",
    ]
    assert payload["messages"][1]["content"]["plan_type"] == "draft_plan"
    assert payload["messages"][1]["content"]["steps"][0]["operation_id"] == "create_box"
    draft_events = [message for message in payload["messages"] if message["type"] == "draft_event"]
    assert [event["content"]["action"] for event in draft_events] == ["propose", "apply", "preview"]
    transaction_token = payload["draft_result"]["transaction_token"]
    assert draft_events[-1]["content"]["draft_transaction_token"] == transaction_token
    assert draft_events[-1]["content"]["preview_model"]["model_url"].startswith(
        f"/api/draft-transactions/{transaction_token}/model?v="
    )
    assert payload["messages"][-1]["content"].startswith("Created draft `base_plate` as 100 x 100 x 10 mm.")
    assert "This should not be used." not in payload["messages"][-1]["content"]

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    assert reloaded["linked_draft_transaction_tokens"] == [transaction_token]
    assert [message["type"] for message in reloaded["messages"]] == message_types
    assert (service.project.paths.local_state / "draft-transactions" / transaction_token / "transaction.json").exists()


def test_viewer_design_threads_complex_intent_does_not_auto_run_partial_draft(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    runtime = FakeAgentRuntimeClient(
        [
            {"type": "assistant_delta", "text": "This should not be used."},
            {"type": "done"},
        ]
    )
    client = TestClient(create_app(service=service, agent_runtime_client=runtime))
    thread_id = client.post("/api/design-threads", json={"title": "Complex intent"}).json()["thread_id"]

    response = client.post(
        f"/api/design-threads/{thread_id}/chat",
        json={
            "message": (
                "Add pillars in all 4 corners. Each pillar should be 40mm tall. Pillars should be insert 3mm "
                "for plates that attach to the pillars on all 4 sides. Each pillar needs 4 mounting holes. "
                "2 on each external face. The M4 mounting holes should not overlap on the interior of the pillars."
            ),
            "context_snapshot": {
                "visible_part_ids": ["example_block"],
                "selected_part_ids": ["example_block"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "draft_result" not in payload
    assert [message["type"] for message in payload["messages"]] == [
        "user_message",
        "design_plan",
        "assistant_message",
    ]
    plan = payload["messages"][1]["content"]
    assert plan["coverage"]["can_auto_execute"] is False
    assert plan["coverage"]["execution_readiness"] == "partial_requires_review"
    assert {item["kind"] for item in plan["intent_items"]} >= {
        "boss_or_pillar",
        "insert_or_recess",
        "hole_pattern",
        "constraint",
    }
    assert payload["messages"][2]["metadata"]["status"] == "intent_incomplete"
    assert "partial result" in payload["messages"][2]["content"]
    assert "This should not be used." not in payload["messages"][2]["content"]

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    assert reloaded["linked_draft_transaction_tokens"] == []
    assert not (service.project.paths.local_state / "draft-transactions").exists()


def test_viewer_design_threads_chat_broad_prompt_persists_question_plan_without_runtime(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    runtime = FakeAgentRuntimeClient(
        [
            {"type": "assistant_delta", "text": "This should not be used."},
            {"type": "done"},
        ]
    )
    client = TestClient(create_app(service=service, agent_runtime_client=runtime))

    thread_id = client.post("/api/design-threads", json={"title": "Planner questions"}).json()["thread_id"]
    response = client.post(
        f"/api/design-threads/{thread_id}/chat",
        json={
            "message": "Make a robot head",
            "context_snapshot": {
                "visible_part_ids": [],
                "selected_part_ids": [],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [message["type"] for message in payload["messages"]] == [
        "user_message",
        "design_plan",
        "assistant_message",
    ]
    design_plan = payload["messages"][1]
    assert design_plan["content"]["plan_type"] == "questions"
    assert design_plan["content"]["status"] == "needs_user_input"
    assert design_plan["content"]["brief"]["goal"] == "Make a robot head"
    assert "size envelope" in design_plan["content"]["missing_decisions"]
    assert "mount" in payload["messages"][2]["content"].lower()
    assert "This should not be used." not in payload["messages"][2]["content"]

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    assert [message["type"] for message in reloaded["messages"]] == [
        "user_message",
        "design_plan",
        "assistant_message",
    ]


def test_viewer_design_threads_chat_annotated_draft_plan_requests_visual_evidence_without_runtime(tmp_path) -> None:
    _write_example_step(tmp_path)

    def fake_converter(step_path: Path, stl_path: Path) -> Path:
        assert step_path.exists()
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        stl_path.write_text("solid preview\nendsolid preview\n", encoding="utf-8")
        return stl_path

    service = ViewerService(tmp_path, converter=fake_converter)

    def fail_preview_command_proposal(_payload: dict[str, object]) -> dict[str, object]:
        raise AssertionError("annotated sketch planning must request visual evidence before preview commands")

    service.preview_command_proposal = fail_preview_command_proposal  # type: ignore[method-assign]
    runtime = FakeAgentRuntimeClient(
        [
            {"type": "assistant_delta", "text": "This should not be used."},
            {"type": "done"},
        ]
    )
    client = TestClient(create_app(service=service, agent_runtime_client=runtime))

    thread_id = client.post("/api/design-threads", json={"title": "Annotated plate"}).json()["thread_id"]
    response = client.post(
        f"/api/design-threads/{thread_id}/chat",
        json={
            "message": (
                "I'd like to create a 10mm thick plate in the xy plane shaped similar to this "
                "with counter bore m4 holes."
            ),
            "context_snapshot": {
                "visible_part_ids": ["example_block"],
                "selected_part_ids": ["example_block"],
                "annotations": _lobed_sketch_annotations(),
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert [message["type"] for message in payload["messages"]] == [
        "user_message",
        "design_plan",
        "assistant_message",
    ]
    assert payload["messages"][1]["content"]["plan_type"] == "draft_plan"
    assert payload["visual_evidence_request"]["status"] == "pending"
    assert payload["visual_evidence_request"]["view"] == "top"
    assert payload["visual_evidence_request"]["part_ids"] == ["example_block"]
    assert "visual-evidence request" in payload["messages"][2]["content"]
    assert "This should not be used." not in payload["messages"][2]["content"]

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    assert reloaded["visual_evidence_request_count"] == 1
    assert reloaded["visual_evidence_requests"][0]["status"] == "pending"

    completed = client.post(
        f"/api/design-threads/{thread_id}/visual-evidence-requests/{payload['visual_evidence_request']['request_id']}/complete",
        json={
            "source": "agent",
            "view": "top",
            "content_type": "image/png",
            "data_url": _tiny_png_data_url(),
            "width": 640,
            "height": 480,
            "metadata": {
                **payload["visual_evidence_request"]["metadata"],
                "render_context": "viewport-canvas",
            },
        },
    )

    assert completed.status_code == 200
    completed_payload = completed.json()
    assert completed_payload["request"]["status"] == "fulfilled"
    assert completed_payload["continuation"]["draft_result"]["ok"] is True
    assert completed_payload["continuation"]["draft_result"]["part_id"] == "sketch_plate"
    operations = completed_payload["continuation"]["draft_result"]["applied_operations"]
    assert operations[0]["name"] == "create_sketch_profile"
    assert operations[0]["endpoint"] == "profile"
    assert operations[0]["parameters"]["height"] == 10.0
    profile_points = operations[0]["parameters"]["profile_points"]
    assert len(profile_points) > 6
    assert profile_points[0] == profile_points[-1]
    assert any(
        abs(profile_points[index][0] - profile_points[index - 1][0]) > 1e-6
        and abs(profile_points[index][1] - profile_points[index - 1][1]) > 1e-6
        for index in range(1, len(profile_points))
    )
    assert any(operation["name"] == "add_counterbore" for operation in operations)
    assert completed_payload["continuation"]["draft_preview_model"]["part_id"] == "sketch_plate"
    assert completed_payload["continuation"]["draft_preview_model"]["draft"]["profile_points"] == profile_points

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    message_types = [message["type"] for message in reloaded["messages"]]
    assert message_types[-3:] == ["draft_event", "draft_event", "assistant_message"]
    assert reloaded["messages"][-1]["metadata"]["status"] == "draft_preview_ready"


def test_viewer_design_threads_chat_request_visual_evidence_tool_creates_request(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    runtime = FakeAgentRuntimeClient(
        [
            {
                "type": "tool_call",
                "tool": "request_visual_evidence",
                "arguments": {
                    "thread_id": "ignored-by-server",
                    "view": "top",
                    "purpose": "inspect annotated top view",
                    "part_ids": ["example_block"],
                },
            },
            {"type": "done"},
        ]
    )
    client = TestClient(create_app(service=service, agent_runtime_client=runtime))

    thread_id = client.post("/api/design-threads", json={"title": "Tool evidence"}).json()["thread_id"]
    response = client.post(
        f"/api/design-threads/{thread_id}/chat",
        json={
            "message": "Review this preview.",
            "context_snapshot": {
                "visible_part_ids": ["example_block"],
                "selected_part_ids": ["example_block"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    message_types = [message["type"] for message in payload["messages"]]
    assert message_types == ["user_message", "design_plan", "tool_call", "tool_result"]
    assert payload["messages"][3]["content"]["tool"] == "request_visual_evidence"
    assert payload["messages"][3]["content"]["status"] == "pending"

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    assert reloaded["visual_evidence_request_count"] == 1
    assert reloaded["visual_evidence_requests"][0]["view"] == "top"
    assert reloaded["visual_evidence_requests"][0]["part_ids"] == ["example_block"]


def test_viewer_design_threads_chat_creates_deterministic_panel_draft_with_selected_part_context(tmp_path) -> None:
    _write_example_step(tmp_path)

    def fake_converter(step_path: Path, stl_path: Path) -> Path:
        assert step_path.exists()
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        stl_path.write_text("solid preview\nendsolid preview\n", encoding="utf-8")
        return stl_path

    service = ViewerService(tmp_path, converter=fake_converter)
    runtime = FakeAgentRuntimeClient(
        [
            {"type": "assistant_delta", "text": "This should not be used."},
            {"type": "done"},
        ]
    )
    client = TestClient(create_app(service=service, agent_runtime_client=runtime))

    thread_id = client.post("/api/design-threads", json={"title": "ThirdTest"}).json()["thread_id"]

    response = client.post(
        f"/api/design-threads/{thread_id}/chat",
        json={
            "message": "Please create a panel that is 100mm x 100mm and 10mm thick.",
            "context_snapshot": {
                "visible_part_ids": [],
                "selected_part_ids": ["example_block"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["draft_result"]["ok"] is True
    assert payload["draft_result"]["part_id"] == "draft_panel"
    assert payload["draft_result"]["selected_part_id"] == "example_block"
    assert payload["draft_preview_model"]["dimensions"]["length_mm"] == 100.0
    assert payload["draft_preview_model"]["dimensions"]["width_mm"] == 100.0
    assert payload["draft_preview_model"]["dimensions"]["height_mm"] == 10.0
    assert [message["type"] for message in payload["messages"]] == [
        "user_message",
        "design_plan",
        "draft_event",
        "draft_event",
        "draft_event",
        "assistant_message",
    ]
    assert "This should not be used." not in payload["messages"][-1]["content"]


def test_viewer_design_threads_chat_creates_deterministic_plate_draft_with_by_typo(tmp_path) -> None:
    _write_example_step(tmp_path)

    def fake_converter(step_path: Path, stl_path: Path) -> Path:
        assert step_path.exists()
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        stl_path.write_text("solid preview\nendsolid preview\n", encoding="utf-8")
        return stl_path

    service = ViewerService(tmp_path, converter=fake_converter)
    runtime = FakeAgentRuntimeClient(
        [
            {"type": "assistant_delta", "text": "This should not be used."},
            {"type": "done"},
        ]
    )
    client = TestClient(create_app(service=service, agent_runtime_client=runtime))

    thread_id = client.post("/api/design-threads", json={"title": "4th test"}).json()["thread_id"]

    response = client.post(
        f"/api/design-threads/{thread_id}/chat",
        json={
            "message": "create a plate that is 100mm byu 100mm by 10mm",
            "context_snapshot": {
                "visible_part_ids": [],
                "selected_part_ids": ["example_block"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["draft_result"]["ok"] is True
    assert payload["draft_result"]["part_id"] == "draft_plate"
    assert payload["draft_result"]["selected_part_id"] == "example_block"
    assert payload["draft_preview_model"]["dimensions"]["length_mm"] == 100.0
    assert payload["draft_preview_model"]["dimensions"]["width_mm"] == 100.0
    assert payload["draft_preview_model"]["dimensions"]["height_mm"] == 10.0
    assert [message["type"] for message in payload["messages"]] == [
        "user_message",
        "design_plan",
        "draft_event",
        "draft_event",
        "draft_event",
        "assistant_message",
    ]
    assert "This should not be used." not in payload["messages"][-1]["content"]


def test_viewer_design_threads_chat_applies_followup_holes_to_active_draft_transaction(tmp_path) -> None:
    _write_example_step(tmp_path)

    def fake_converter(step_path: Path, stl_path: Path) -> Path:
        assert step_path.exists()
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        stl_path.write_text("solid preview\nendsolid preview\n", encoding="utf-8")
        return stl_path

    service = ViewerService(tmp_path, converter=fake_converter)
    runtime = FakeAgentRuntimeClient(
        [
            {"type": "assistant_delta", "text": "This should not be used."},
            {"type": "done"},
        ]
    )
    client = TestClient(create_app(service=service, agent_runtime_client=runtime))

    thread_id = client.post("/api/design-threads", json={"title": "Followup draft"}).json()["thread_id"]
    create_response = client.post(
        f"/api/design-threads/{thread_id}/chat",
        json={
            "message": "create a plate that is 100mm by 120mm by 10mm",
            "context_snapshot": {
                "visible_part_ids": [],
                "selected_part_ids": ["example_block"],
            },
        },
    )
    create_payload = create_response.json()
    transaction_token = create_payload["draft_result"]["transaction_token"]

    followup_response = client.post(
        f"/api/design-threads/{thread_id}/chat",
        json={
            "message": "Place m5 holes in each corner 10mm from each side",
            "context_snapshot": {
                "visible_part_ids": [f"draft:{transaction_token}"],
                "selected_part_ids": ["example_block"],
                "draft_transaction_token": transaction_token,
            },
        },
    )

    assert followup_response.status_code == 200
    followup_payload = followup_response.json()
    assert followup_payload["draft_result"]["ok"] is True
    assert followup_payload["draft_result"]["transaction_token"] == transaction_token
    operations = followup_payload["draft_result"]["applied_operations"]
    hole_operations = [operation for operation in operations if operation["name"] == "add_hole"]
    assert len(hole_operations) == 4
    assert [operation["parameters"]["diameter"] for operation in hole_operations] == [5.0, 5.0, 5.0, 5.0]
    assert {(operation["parameters"]["x"], operation["parameters"]["y"]) for operation in hole_operations} == {
        (10.0, 10.0),
        (90.0, 10.0),
        (10.0, 110.0),
        (90.0, 110.0),
    }
    assert followup_payload["draft_preview_model"]["transaction_token"] == transaction_token
    assert followup_payload["draft_preview_model"]["draft"]["features"]
    assert "This should not be used." not in followup_payload["messages"][-1]["content"]


def test_viewer_design_threads_chat_applies_annotated_raised_walls_to_active_draft_transaction(tmp_path) -> None:
    _write_example_step(tmp_path)

    def fake_converter(step_path: Path, stl_path: Path) -> Path:
        assert step_path.exists()
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        stl_path.write_text("solid preview\nendsolid preview\n", encoding="utf-8")
        return stl_path

    def freehand_box(min_x: float, max_x: float, min_y: float, max_y: float) -> dict[str, object]:
        return {
            "kind": "freehand",
            "points": [
                {"x": min_x, "y": min_y},
                {"x": max_x, "y": min_y},
                {"x": max_x, "y": max_y},
                {"x": min_x, "y": max_y},
                {"x": min_x, "y": min_y},
            ]
        }

    service = ViewerService(tmp_path, converter=fake_converter)
    runtime = FakeAgentRuntimeClient(
        [
            {"type": "assistant_delta", "text": "This should not be used."},
            {"type": "done"},
        ]
    )
    client = TestClient(create_app(service=service, agent_runtime_client=runtime))

    thread_id = client.post("/api/design-threads", json={"title": "Annotated walls"}).json()["thread_id"]
    create_payload = client.post(
        f"/api/design-threads/{thread_id}/chat",
        json={
            "message": "create a plate that is 100mm by 120mm by 10mm",
            "context_snapshot": {
                "visible_part_ids": [],
                "selected_part_ids": ["example_block"],
            },
        },
    ).json()
    transaction_token = create_payload["draft_result"]["transaction_token"]

    followup_response = client.post(
        f"/api/design-threads/{thread_id}/chat",
        json={
            "message": (
                "Using your view tool examine the annotated image. I'd like to see raised wall from our "
                "base part in these rectangles that raise up 20, 30, 40, 50mm high respectively."
            ),
            "context_snapshot": {
                "visible_part_ids": [f"draft:{transaction_token}"],
                "selected_part_ids": ["example_block"],
                "draft_transaction_token": transaction_token,
                "annotations": [
                    freehand_box(0.10, 0.20, 0.20, 0.40),
                    freehand_box(0.30, 0.60, 0.10, 0.20),
                    freehand_box(0.70, 0.80, 0.25, 0.55),
                    freehand_box(0.35, 0.65, 0.70, 0.80),
                ],
            },
        },
    )

    assert followup_response.status_code == 200
    followup_payload = followup_response.json()
    assert followup_payload["draft_result"]["ok"] is True
    assert followup_payload["draft_result"]["transaction_token"] == transaction_token
    operations = followup_payload["draft_result"]["applied_operations"]
    wall_operations = [operation for operation in operations if operation["name"] == "add_raised_wall"]
    assert len(wall_operations) == 4
    assert [operation["parameters"]["height"] for operation in wall_operations] == [20.0, 30.0, 40.0, 50.0]
    assert wall_operations[0]["parameters"]["face"] == "top"
    assert wall_operations[0]["parameters"]["x"] == pytest.approx(15.0)
    assert wall_operations[0]["parameters"]["y"] == pytest.approx(36.0)
    assert wall_operations[0]["parameters"]["length"] == pytest.approx(10.0)
    assert wall_operations[0]["parameters"]["width"] == pytest.approx(24.0)
    assert wall_operations[0]["parameters"]["height"] == pytest.approx(20.0)
    features = followup_payload["draft_preview_model"]["draft"]["feature_list"]
    assert len([feature for feature in features if feature["kind"] == "raised_wall"]) == 4
    assert "This should not be used." not in followup_payload["messages"][-1]["content"]


def _sse_payloads(stream_text: str) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for line in stream_text.splitlines():
        if not line.startswith("data:"):
            continue
        value = line.removeprefix("data:").strip()
        if not value or value == "[DONE]":
            continue
        decoded = json.loads(value)
        assert isinstance(decoded, dict)
        payloads.append(decoded)
    return payloads


def test_viewer_design_threads_stream_chat_persists_runtime_events(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    runtime = FakeAgentRuntimeClient(
        [
            {"type": "assistant_delta", "text": "Draft response"},
            {
                "type": "tool_call",
                "tool": "run_focused_validator",
                "arguments": {"validator_id": "panel-clearance"},
            },
            {
                "type": "tool_result",
                "tool": "run_focused_validator",
                "result": {"status": "pass", "summary": "Panel clearance passed", "report_id": "val-001"},
            },
            {"type": "assistant_delta", "text": " ready."},
            {"type": "done"},
        ]
    )
    client = TestClient(create_app(service=service, agent_runtime_client=runtime))

    thread_id = client.post("/api/design-threads", json={"title": "Stream check"}).json()["thread_id"]

    with client.stream(
        "POST",
        f"/api/design-threads/{thread_id}/chat/stream",
        json={
            "message": "Review this preview.",
            "context_snapshot": {
                "visible_part_ids": ["example_block"],
                "selected_part_ids": ["example_block"],
                "viewport_screenshot": {"kind": "viewport_screenshot", "attachment_id": "att-1"},
            },
        },
    ) as response:
        assert response.status_code == 200
        payloads = _sse_payloads("".join(response.iter_text()))

    assert any(payload.get("message", {}).get("type") == "user_message" for payload in payloads)
    assert any(payload.get("message", {}).get("type") == "design_plan" for payload in payloads)
    assert any(payload.get("event", {}).get("type") == "assistant_delta" for payload in payloads)
    assert any(payload.get("message", {}).get("type") == "tool_call" for payload in payloads)
    assert any(payload.get("message", {}).get("type") == "tool_result" for payload in payloads)
    assert any(payload.get("message", {}).get("type") == "assistant_message" for payload in payloads)
    assert payloads[-1]["done"] is True

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    assert [message["type"] for message in reloaded["messages"]] == [
        "user_message",
        "design_plan",
        "tool_call",
        "tool_result",
        "assistant_message",
    ]
    assert reloaded["messages"][-1]["content"] == "Draft response ready."
    assert reloaded["messages"][3]["metadata"]["report_ids"] == ["val-001"]
    assert reloaded["messages"][0]["metadata"]["viewport_attachment_id"] == "att-1"


def test_viewer_design_threads_stream_chat_missing_thread_returns_404(tmp_path) -> None:
    _write_example_step(tmp_path)
    client = TestClient(create_app(service=ViewerService(tmp_path)))

    response = client.post(
        "/api/design-threads/missing/chat/stream",
        json={"message": "Will not stream"},
    )

    assert response.status_code == 404


def test_viewer_design_threads_viewport_screenshot_attachment_stores_png_and_sidecar(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    thread_id = client.post("/api/design-threads", json={"title": "Screenshot thread"}).json()["thread_id"]

    response = client.post(
        f"/api/design-threads/{thread_id}/attachments/viewport-screenshot",
        json={
            "data_url": _tiny_png_data_url(),
            "selected_part_ids": ["example_block", 123],
            "visible_part_ids": ["example_block"],
            "backend_revision": 5,
            "camera": {"position": [1.0, 2.0, 3.0], "target": [0.0, 0.0, 0.0]},
            "viewport": {"width": 64, "height": 48},
            "annotations": [
                {"id": "../note 1", "kind": "note", "text": "Check this edge", "x": 0.9, "y": 0.1},
                {"kind": "circle", "x": 0.25, "y": 0.25, "radius": 0.12},
                {
                    "kind": "freehand",
                    "points": [{"x": -0.1, "y": 0.2}, {"x": 0.4, "y": 1.2}],
                    "width": 0.2,
                },
                {"kind": "unsupported", "text": "drop"},
            ],
        },
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["kind"] == "viewport_screenshot"
    assert payload["content_type"] == "image/png"
    assert payload["selected_part_ids"] == ["example_block", "123"]
    assert payload["visible_part_ids"] == ["example_block"]
    assert payload["annotations"][0] == {
        "id": "note-1",
        "kind": "note",
        "text": "Check this edge",
        "x": 0.9,
        "y": 0.1,
    }
    assert payload["annotations"][1]["kind"] == "circle"
    assert payload["annotations"][1]["id"].startswith("ann_")
    assert payload["annotations"][1]["radius"] == 0.12
    assert payload["annotations"][2]["kind"] == "freehand"
    assert payload["annotations"][2]["points"] == [{"x": 0.0, "y": 0.2}, {"x": 0.4, "y": 1.0}]
    assert payload["annotations"][2]["width"] == 0.05
    assert payload["metadata_path"].endswith(".json")

    threads_root = service.project.paths.local_state / "design-threads"
    png_path = threads_root / payload["path"]
    meta_path = threads_root / payload["metadata_path"]
    assert png_path.exists()
    assert png_path.read_bytes().startswith(b"\x89PNG")
    assert meta_path.exists()

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    assert metadata["attachment_id"] == payload["attachment_id"]
    assert metadata["backend_revision"] == 5
    assert metadata["camera"]["position"] == [1.0, 2.0, 3.0]
    assert metadata["viewport"] == {"width": 64, "height": 48}
    assert metadata["annotations"][0]["kind"] == "note"

    assert png_path.resolve().is_relative_to(threads_root.resolve())

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    assert reloaded["attachment_count"] == 1
    assert reloaded["attachments"][0]["attachment_id"] == payload["attachment_id"]
    assert reloaded["attachments"][0]["annotations"][0]["id"] == "note-1"


def test_viewer_design_threads_viewport_screenshot_rejects_missing_image_data(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    thread_id = client.post("/api/design-threads", json={"title": "Rejected screenshot thread"}).json()["thread_id"]

    response = client.post(
        f"/api/design-threads/{thread_id}/attachments/viewport-screenshot",
        json={"selected_part_ids": ["example_block"]},
    )
    assert response.status_code == 400

    unsupported = client.post(
        f"/api/design-threads/{thread_id}/attachments/viewport-screenshot",
        json={"data_url": "data:text/plain;base64,SGVsbG8="},
    )
    assert unsupported.status_code == 400


def test_viewer_design_threads_visual_evidence_create_list_and_retrieve(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    thread_id = client.post("/api/design-threads", json={"title": "Visual evidence thread"}).json()["thread_id"]

    create_response = client.post(
        f"/api/design-threads/{thread_id}/visual-evidence",
        json={
            "source": "browser",
            "preset": "front",
            "width": 320,
            "height": 240,
            "selected_ids": ["example_block"],
            "visible_ids": ["example_block", "ghost-part"],
            "part_ids": ["example_block", 22],
            "purpose": "review",
            "camera": {"position": [1.0, 2.0, 3.0], "target": [0.0, 0.0, 0.0]},
            "viewport": {"width": 320, "height": 240},
            "metadata": {"run": "snapshot"},
            "data_url": _tiny_png_data_url(),
        },
    )
    assert create_response.status_code == 200
    payload = create_response.json()

    assert payload["kind"] == "visual_evidence"
    assert payload["source"] == "browser"
    assert payload["view"] == "front"
    assert payload["width"] == 320
    assert payload["height"] == 240
    assert payload["image_url"] == f"/api/design-threads/{thread_id}/visual-evidence/{payload['artifact_id']}/image"

    threads_root = service.project.paths.local_state / "design-threads"
    png_path = threads_root / payload["path"]
    metadata_path = threads_root / payload["metadata_path"]
    assert png_path.exists()
    assert png_path.read_bytes().startswith(b"\x89PNG")
    assert metadata_path.exists()
    assert png_path.resolve().is_relative_to(threads_root.resolve())

    thread_payload = client.get(f"/api/design-threads/{thread_id}").json()
    assert thread_payload["visual_evidence_count"] == 1
    assert thread_payload["visual_evidence"][0]["artifact_id"] == payload["artifact_id"]
    assert thread_payload["visual_evidence"][0]["view"] == "front"

    metadata_response = client.get(
        f"/api/design-threads/{thread_id}/visual-evidence/{payload['artifact_id']}"
    ).json()
    assert metadata_response["artifact_id"] == payload["artifact_id"]
    assert metadata_response["source"] == "browser"
    assert metadata_response["purpose"] == "review"

    image_response = client.get(
        f"/api/design-threads/{thread_id}/visual-evidence/{payload['artifact_id']}/image"
    )
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"
    assert image_response.content.startswith(b"\x89PNG")


def test_viewer_design_threads_visual_evidence_rejects_bad_preset_and_image(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    missing_thread = client.post(
        "/api/design-threads/missing-thread/visual-evidence",
        json={"data_url": _tiny_png_data_url()},
    )
    assert missing_thread.status_code == 404

    thread_id = client.post("/api/design-threads", json={"title": "Bad visual evidence input"}).json()["thread_id"]

    bad_preset = client.post(
        f"/api/design-threads/{thread_id}/visual-evidence",
        json={
            "preset": "diagonal",
            "image_data": _tiny_png_data_url().removeprefix("data:image/png;base64,"),
        },
    )
    assert bad_preset.status_code == 400

    non_png = client.post(
        f"/api/design-threads/{thread_id}/visual-evidence",
        json={
            "source": "agent",
            "data_url": "data:text/plain;base64,SGVsbG8=",
        },
    )
    assert non_png.status_code == 400

    missing_evidence = client.get(f"/api/design-threads/{thread_id}/visual-evidence/missing-artifact")
    assert missing_evidence.status_code == 404


def test_viewer_design_threads_visual_evidence_id_sanitization_and_thread_containment(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    thread_id = client.post("/api/design-threads", json={"title": "Visual evidence id safety"}).json()["thread_id"]
    threads_root = service.project.paths.local_state / "design-threads"

    response = client.post(
        f"/api/design-threads/{thread_id}/visual-evidence",
        json={"artifact_id": "../../outside/path", "data_url": _tiny_png_data_url()},
    )
    assert response.status_code == 200
    payload = response.json()

    artifact_id = payload["artifact_id"]
    assert "/" not in artifact_id and "\\" not in artifact_id
    assert ".." not in artifact_id
    stored_png = threads_root / payload["path"]
    stored_meta = threads_root / payload["metadata_path"]
    assert stored_png.resolve().is_relative_to(threads_root.resolve())
    assert stored_meta.resolve().is_relative_to(threads_root.resolve())

    reloaded = client.get(f"/api/design-threads/{thread_id}/visual-evidence/{artifact_id}").json()
    assert reloaded["artifact_id"] == artifact_id


def test_viewer_design_threads_visual_evidence_request_lifecycle(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    thread_id = client.post("/api/design-threads", json={"title": "Visual evidence requests"}).json()["thread_id"]
    request_response = client.post(
        f"/api/design-threads/{thread_id}/visual-evidence-requests",
        json={
            "request_id": "../../agent/request",
            "source": "agent",
            "view": "top",
            "width": 1200,
            "height": 800,
            "selected_ids": ["example_block"],
            "visible_ids": ["example_block", "other"],
            "part_ids": ["example_block"],
            "purpose": "inspect top clearance",
            "metadata": {"caller": "mcp"},
        },
    )
    assert request_response.status_code == 200
    request = request_response.json()

    assert request["request_id"] == "agent-request"
    assert request["status"] == "pending"
    assert request["view"] == "top"
    assert request["width"] == 1200
    assert request["height"] == 800

    listed = client.get(f"/api/design-threads/{thread_id}/visual-evidence-requests?status=pending").json()
    assert listed["count"] == 1
    assert listed["visual_evidence_requests"][0]["request_id"] == request["request_id"]

    completed = client.post(
        f"/api/design-threads/{thread_id}/visual-evidence-requests/{request['request_id']}/complete",
        json={
            "data_url": _tiny_png_data_url(),
            "width": 640,
            "height": 480,
            "camera": {"view": "top", "position": [0.0, 0.0, 10.0]},
            "viewport": {"width": 640, "height": 480, "render_context": "offscreen-browser"},
            "metadata": {"render_context": "offscreen-browser"},
        },
    )
    assert completed.status_code == 200
    completed_payload = completed.json()

    evidence = completed_payload["visual_evidence"]
    fulfilled_request = completed_payload["request"]
    assert fulfilled_request["status"] == "fulfilled"
    assert fulfilled_request["artifact_id"] == evidence["artifact_id"]
    assert evidence["source"] == "agent"
    assert evidence["view"] == "top"
    assert evidence["purpose"] == "inspect top clearance"
    assert evidence["metadata"]["caller"] == "mcp"
    assert evidence["metadata"]["visual_evidence_request_id"] == request["request_id"]

    threads_root = service.project.paths.local_state / "design-threads"
    request_path = threads_root / thread_id / "visual-evidence" / "requests" / f"{request['request_id']}.json"
    evidence_path = threads_root / evidence["path"]
    assert request_path.exists()
    assert request_path.resolve().is_relative_to(threads_root.resolve())
    assert evidence_path.exists()
    assert evidence_path.resolve().is_relative_to(threads_root.resolve())

    reloaded_thread = client.get(f"/api/design-threads/{thread_id}").json()
    assert reloaded_thread["visual_evidence_request_count"] == 1
    assert reloaded_thread["visual_evidence_requests"][0]["status"] == "fulfilled"
    assert reloaded_thread["visual_evidence_count"] == 1

    repeat = client.post(
        f"/api/design-threads/{thread_id}/visual-evidence-requests/{request['request_id']}/complete",
        json={"data_url": _tiny_png_data_url()},
    )
    assert repeat.status_code == 400


def test_viewer_design_threads_visual_evidence_request_rejects_bad_input_and_records_failures(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    missing_thread = client.post(
        "/api/design-threads/missing-thread/visual-evidence-requests",
        json={"view": "iso"},
    )
    assert missing_thread.status_code == 404

    thread_id = client.post("/api/design-threads", json={"title": "Bad evidence requests"}).json()["thread_id"]
    bad_preset = client.post(
        f"/api/design-threads/{thread_id}/visual-evidence-requests",
        json={"view": "diagonal"},
    )
    assert bad_preset.status_code == 400

    request = client.post(
        f"/api/design-threads/{thread_id}/visual-evidence-requests",
        json={"view": "front", "purpose": "expected render failure"},
    ).json()
    failed = client.post(
        f"/api/design-threads/{thread_id}/visual-evidence-requests/{request['request_id']}/fail",
        json={"error": "No visible models available"},
    )
    assert failed.status_code == 200
    assert failed.json()["request"]["status"] == "failed"
    assert failed.json()["request"]["error"] == "No visible models available"

    pending = client.get(f"/api/design-threads/{thread_id}/visual-evidence-requests?status=pending").json()
    assert pending["count"] == 0

    missing_request = client.get(f"/api/design-threads/{thread_id}/visual-evidence-requests/missing-request")
    assert missing_request.status_code == 404


def test_viewer_design_threads_context_snapshot_can_reference_attachment_id(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    thread_id = client.post("/api/design-threads", json={"title": "Attachment ref"}).json()["thread_id"]
    attachment_id = client.post(
        f"/api/design-threads/{thread_id}/attachments/viewport-screenshot",
        json={"data_url": _tiny_png_data_url()},
    ).json()["attachment_id"]

    snapshot = client.post(
        f"/api/design-threads/{thread_id}/context-snapshots",
        json={
            "viewport_screenshot": {"kind": "viewport_screenshot", "attachment_id": attachment_id},
            "visible_part_ids": ["example_block"],
            "selected_part_ids": ["example_block"],
        },
    )
    assert snapshot.status_code == 200
    snapshot_payload = snapshot.json()
    assert snapshot_payload["viewer_state"]["viewport_screenshot"]["attachment_id"] == attachment_id

    chat_response = client.post(
        f"/api/design-threads/{thread_id}/chat",
        json={
            "message": "How do I improve this?",
            "context_snapshot": {
                "viewport_screenshot": {"kind": "viewport_screenshot", "attachment_id": attachment_id},
                "visible_part_ids": ["example_block"],
                "selected_part_ids": ["example_block"],
            },
        },
    )
    assert chat_response.status_code == 200
    chat_payload = chat_response.json()
    assert chat_payload["messages"][0]["metadata"]["viewport_screenshot"] is True
    assert chat_payload["messages"][0]["metadata"]["viewport_attachment_id"] == attachment_id
    assert chat_payload["messages"][0]["attachments"] == [attachment_id]
    assert chat_payload["thread"]["attachments"][0]["attachment_id"] == attachment_id


def test_viewer_design_threads_viewport_attachment_id_sanitization_and_thread_containment(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    thread_id = client.post("/api/design-threads", json={"title": "Attachment id safety"}).json()["thread_id"]
    threads_root = service.project.paths.local_state / "design-threads"

    response = client.post(
        f"/api/design-threads/{thread_id}/attachments/viewport-screenshot",
        json={"attachment_id": "../../outside/path", "data_url": _tiny_png_data_url()},
    )
    assert response.status_code == 200
    payload = response.json()

    assert "/" not in payload["attachment_id"] and "\\" not in payload["attachment_id"]
    assert ".." not in payload["attachment_id"]
    png_path = threads_root / payload["path"]
    assert png_path.resolve().is_relative_to(threads_root.resolve())


def test_viewer_design_threads_draft_events_persist_and_link_metadata(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    thread_id = client.post("/api/design-threads", json={"title": "Draft event thread"}).json()["thread_id"]
    transaction = client.post("/api/draft-transactions", json={"part_id": "example_block"}).json()
    transaction_token = transaction["transaction_token"]

    events = [
        {
            "action": "begin",
            "summary": "Draft start",
            "draft_transaction_token": transaction_token,
        },
        {
            "action": "apply",
            "summary": "Applied requested feature",
            "transaction_token": transaction_token,
        },
        {
            "action": "preview",
            "summary": "Preview generated",
            "token": transaction_token,
        },
        {
            "action": "accept",
            "summary": "Accepted changes",
            "draft_transaction_token": transaction_token,
            "source_patch_path": "source_patches/txn_accepted.patch",
            "generated_source_path": "generated/source.py",
            "validator_stub_path": "validator/stubs/accept.json",
            "acceptance_manifest_path": "drafts/accept/manifest.json",
            "source_loop_command": "python do_accept.py",
            "accepted_artifact_paths": [
                "accept/overview.step",
                "accept/commands.txt",
            ],
            "artifacts": {
                "source_patch": "artifacts/patch.step",
                "stl": "artifacts/accepted.stl",
            },
        },
        {
            "action": "discard",
            "summary": "Discard pending draft",
            "draft_transaction_token": transaction_token,
        },
    ]

    for payload in events:
        response = client.post(f"/api/design-threads/{thread_id}/draft-events", json=payload)
        assert response.status_code == 200
        record = response.json()
        assert record["type"] == "draft_event"
        assert record["role"] == "system"
        assert record["content"]["action"] in {"begin", "apply", "preview", "accept", "discard"}

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    assert reloaded["message_count"] == 5
    assert reloaded["linked_draft_transaction_tokens"] == [transaction_token]
    assert len(reloaded["accepted_artifact_paths"]) >= 7
    assert "source_patches/txn_accepted.patch" in reloaded["accepted_artifact_paths"]
    assert "generated/source.py" in reloaded["accepted_artifact_paths"]
    assert "validator/stubs/accept.json" in reloaded["accepted_artifact_paths"]
    assert "drafts/accept/manifest.json" in reloaded["accepted_artifact_paths"]
    assert "accept/overview.step" in reloaded["accepted_artifact_paths"]
    assert "artifacts/patch.step" in reloaded["accepted_artifact_paths"]
    assert "artifacts/accepted.stl" in reloaded["accepted_artifact_paths"]
    assert reloaded["messages"][2]["content"]["action"] == "preview"
    assert reloaded["messages"][3]["content"]["action"] == "accept"
    assert len((service.project.paths.local_state / "design-threads" / thread_id / "messages.jsonl").read_text(encoding="utf-8").splitlines()) == 5


def test_viewer_design_threads_draft_events_accept_frontend_nested_content_shape(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    thread_id = client.post("/api/design-threads", json={"title": "Nested draft event"}).json()["thread_id"]
    response = client.post(
        f"/api/design-threads/{thread_id}/draft-events",
        json={
            "message_id": "draft-event-thread-1-1",
            "thread_id": thread_id,
            "created_at": "2026-06-09T12:00:00Z",
            "type": "draft_event",
            "role": "assistant",
            "content": {
                "summary": "apply: Draft operations applied",
                "content": {
                    "action": "apply",
                    "summary": "Draft operations applied",
                    "draft_transaction_token": "txn-ui",
                    "operation_count": 2,
                },
            },
            "metadata": {
                "action": "apply",
                "draft_transaction_token": "txn-ui",
                "operation_count": 2,
            },
        },
    )

    assert response.status_code == 200
    message = response.json()
    assert message["type"] == "draft_event"
    assert message["role"] == "system"
    assert message["content"]["action"] == "apply"
    assert message["content"]["summary"] == "Draft operations applied"
    assert message["content"]["operation_count"] == 2
    assert message["metadata"]["draft_transaction_token"] == "txn-ui"

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    assert reloaded["linked_draft_transaction_tokens"] == ["txn-ui"]


def test_viewer_design_threads_design_plans_persist_and_reload(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    thread_id = client.post("/api/design-threads", json={"title": "Plan thread"}).json()["thread_id"]
    response = client.post(
        f"/api/design-threads/{thread_id}/design-plans",
        json={
            "plan": {
                "plan_id": "plan-test-1",
                "plan_type": "questions",
                "status": "needs_user_input",
                "brief": {
                    "brief_id": "brief-test-1",
                    "goal": "Make a robot head",
                    "known_facts": [],
                    "missing_decisions": ["mounting interface"],
                },
                "steps": [
                    {
                        "step_id": "q-purpose",
                        "kind": "question",
                        "question": "What is the intended purpose?",
                    }
                ],
            },
            "metadata": {"runtime": "flow_cad_design_planner"},
        },
    )

    assert response.status_code == 200
    message = response.json()
    assert message["type"] == "design_plan"
    assert message["content"]["plan_id"] == "plan-test-1"
    assert message["content"]["plan_type"] == "questions"
    assert message["metadata"]["plan_id"] == "plan-test-1"
    assert message["metadata"]["plan_type"] == "questions"
    assert message["metadata"]["brief_id"] == "brief-test-1"

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    assert reloaded["messages"][-1]["type"] == "design_plan"
    assert reloaded["messages"][-1]["content"]["steps"][0]["kind"] == "question"


def test_viewer_design_threads_validator_and_profile_events_preserve_evidence(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    thread_id = client.post("/api/design-threads", json={"title": "Validator event thread"}).json()["thread_id"]

    tool_result_response = client.post(
        f"/api/design-threads/{thread_id}/validator-events",
        json={
            "event_type": "tool_result",
            "status": "pass",
            "summary": "Focused validator passed",
            "report_id": "report_main",
            "reports": [
                {"id": "report_nested", "summary": "Nested report", "status": "pass"},
                {"report_id": "report_alias", "metadata": {"id": "meta_report", "summary": "metadata summary"}},
            ],
            "data": {"report_id": "report_data", "summary": "Data summary"},
            "metadata": {
                "report_summaries": ["meta report", "metadata summary"],
            },
            "content": {
                "warnings": ["No issues found"],
                "report_id": "report_content",
            },
        },
    )
    assert tool_result_response.status_code == 200
    message = tool_result_response.json()
    assert message["type"] == "tool_result"
    assert message["content"]["status"] == "pass"
    assert "report_main" in message["metadata"]["report_ids"]
    assert "report_nested" in message["metadata"]["report_ids"]
    assert "report_alias" in message["metadata"]["report_ids"]
    assert "report_content" in message["metadata"]["report_ids"]
    assert "report_data" in message["metadata"]["report_ids"]

    review_response = client.post(
        f"/api/design-threads/{thread_id}/validator-events",
        json={
            "event_type": "review_event",
            "summary": "Profile summary",
            "profile_id": "prof-meta",
            "profiles": [
                {"profile_id": "prof-1", "summary": "Profile summary line", "status": "pass"},
                {"id": "ignore", "metadata": {"profile_id": "prof-metadata"}},
            ],
            "metadata": {"status": "complete"},
            "data": {"summary": "Data profile summary", "profile_id": "prof-data"},
        },
    )
    assert review_response.status_code == 200
    review_message = review_response.json()
    assert review_message["type"] == "review_event"
    assert review_message["content"]["summary"] == "Profile summary"
    assert "prof-meta" in review_message["metadata"]["profile_ids"]
    assert "prof-1" in review_message["metadata"]["profile_ids"]
    assert "prof-metadata" in review_message["metadata"]["profile_ids"]
    assert "prof-data" in review_message["metadata"]["profile_ids"]

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    assert reloaded["message_count"] == 2
    assert len(reloaded["messages"]) == 2
    assert reloaded["messages"][0]["type"] == "tool_result"
    assert reloaded["messages"][1]["type"] == "review_event"


def test_viewer_design_threads_event_endpoints_return_404_for_missing_thread(tmp_path) -> None:
    _write_example_step(tmp_path)
    client = TestClient(create_app(service=ViewerService(tmp_path)))

    draft_response = client.post("/api/design-threads/missing-thread/draft-events", json={"action": "begin"})
    assert draft_response.status_code == 404

    validator_response = client.post("/api/design-threads/missing-thread/validator-events", json={"event_type": "tool_result"})
    assert validator_response.status_code == 404
