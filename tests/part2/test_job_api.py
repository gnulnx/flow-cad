from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from flow_cad.jobs import JobState
from flow_cad.viewer.api import create_workbench_app


def test_job_routes_list_observe_stream_and_cancel(tmp_path: Path) -> None:
    app = create_workbench_app(tmp_path, max_concurrent_jobs=1)
    service = app.state.job_service
    release = threading.Event()
    started = threading.Event()

    def work(context):
        context.report("extract", 0.25, "Extracting exact topology")
        started.set()
        while not release.is_set():
            context.checkpoint()
            time.sleep(0.005)
        return {"artifact_revision": "abc"}

    with TestClient(app) as client:
        submission = service.submit(
            request_id="exact-part-1",
            kind="exact-topology",
            work=work,
            payload={"label": "Exact topology", "part_uuid": "part-1"},
        )
        assert started.wait(timeout=1)

        listing = client.get("/api/workbench/v1/jobs")
        assert listing.status_code == 200
        assert listing.json()["jobs"][0]["job_id"] == submission.job.job_id
        assert listing.json()["jobs"][0]["phase"] == "extract"

        cancelled = client.post(f"/api/workbench/v1/jobs/{submission.job.job_id}/cancel")
        assert cancelled.status_code == 202
        assert service.wait(submission.job.job_id).state is JobState.CANCELLED

        events = client.get(f"/api/workbench/v1/jobs/{submission.job.job_id}/events")
        assert events.status_code == 200
        assert events.json()["events"][-1]["event_type"] == "cancelled"

        stream = client.get(f"/api/workbench/v1/jobs/{submission.job.job_id}/stream")
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert "event: cancelled" in stream.text


def test_job_routes_return_not_found(tmp_path: Path) -> None:
    app = create_workbench_app(tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/workbench/v1/jobs/missing").status_code == 404
        assert client.post("/api/workbench/v1/jobs/missing/cancel").status_code == 404
