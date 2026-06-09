import json
from pathlib import Path

from fastapi.testclient import TestClient

from flow_cad.viewer.app import create_app
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


def test_viewer_design_threads_chat_turn_persists_user_assistant_and_view_context(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

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
    assert payload["messages"][1]["type"] == "assistant_message"
    assert payload["messages"][1]["role"] == "assistant"
    assert payload["messages"][1]["metadata"]["runtime"] == "flow_cad_stub"
    assert "viewport image attached" in payload["messages"][1]["content"]
    assert payload["thread"]["message_count"] == 2

    reloaded = client.get(f"/api/design-threads/{thread_id}").json()
    assert [message["type"] for message in reloaded["messages"]] == ["user_message", "assistant_message"]
    assert reloaded["context_snapshots"][0]["viewer_state"]["viewport_screenshot"]["data_url"].startswith("data:image/png")


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
