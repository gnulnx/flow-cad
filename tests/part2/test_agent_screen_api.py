from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from flow_cad.viewer.api import create_workbench_app


TINY_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X9nSAAAAAASUVORK5CYII="
)


def test_replacement_agent_screen_preserves_live_canvas_capture(tmp_path: Path) -> None:
    client = TestClient(create_workbench_app(tmp_path))
    requested = client.post(
        "/api/agent-screen/requests",
        json={"request_id": "../review/one", "purpose": "review live viewport"},
    )
    assert requested.status_code == 200
    assert requested.json()["request_id"] == "review-one"

    captured = client.post(
        "/api/agent-screen/capture",
        json={
            "request_id": "review-one",
            "capture_id": "../capture/one",
            "data_url": TINY_PNG_DATA_URL,
            "width": 1,
            "height": 1,
            "selected_ids": ["part-1"],
            "visible_ids": ["part-1", "part-2"],
            "active_part_id": "part-1",
            "backend_revision": 4,
            "viewport": {
                "render_context": "viewport-canvas",
                "camera": {"position": [1, 2, 3]},
            },
            "metadata": {"annotation_overlay": True},
        },
    )
    assert captured.status_code == 200
    payload = captured.json()
    assert payload["capture_id"] == "capture-one"
    assert payload["viewport"]["render_context"] == "viewport-canvas"
    assert payload["metadata"]["annotation_overlay"] is True

    latest = client.get("/api/agent-screen/latest")
    assert latest.status_code == 200
    assert latest.json()["capture_id"] == "capture-one"
    image = client.get(latest.json()["image_url"])
    assert image.status_code == 200
    assert image.content.startswith(b"\x89PNG")

    request = client.get("/api/agent-screen/requests/latest?status=fulfilled")
    assert request.status_code == 200
    assert request.json()["capture_id"] == "capture-one"
    assert request.json()["status"] == "fulfilled"


def test_agent_screen_module_import_is_kernel_free() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import flow_cad.viewer.agent_screen; "
                "print(any(name == 'build123d' or name.startswith('OCP') "
                "for name in sys.modules))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "False"
