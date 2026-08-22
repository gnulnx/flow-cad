from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from flow_cad.viewer.api import create_workbench_app


def test_workbench_includes_persistent_chat_and_browser_post_cors(tmp_path: Path) -> None:
    client = TestClient(
        create_workbench_app(tmp_path, enable_default_chat_provider=False)
    )

    default = client.get("/api/chat/threads")
    assert default.status_code == 200
    assert default.json()["threads"][0]["thread_id"] == "default"

    turn = client.post(
        "/api/chat/threads/default/turns",
        json={"content": "Inspect the selected part", "request_id": "turn-request"},
        headers={"Origin": "http://127.0.0.1:3000"},
    )
    assert turn.status_code == 202
    assert turn.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert turn.json()["events"][1]["event_type"] == "assistant_created"

    preflight = client.options(
        "/api/chat/threads/default/turns",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert preflight.status_code == 200
    assert "POST" in preflight.headers["access-control-allow-methods"]
