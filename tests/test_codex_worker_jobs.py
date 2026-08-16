import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from flow_cad.viewer.app import create_app
from flow_cad.viewer.service import ViewerService
from flow_cad.viewer.threads import DesignThreadService
from flow_cad.viewer.worker_jobs import CodexWorkerJobManager, WorkerRunResult


class RecordingWorkerRunner:
    def __init__(
        self,
        *,
        last_message: str = "Worker completed.\n\nValidation: not run.",
        returncode: int = 0,
        stderr: str = "",
        session_id: str = "session-123",
        write_path: str | None = None,
        write_text: str = "changed\n",
        wait_for_cancel: bool = False,
        events: list[dict[str, Any]] | None = None,
    ) -> None:
        self.last_message = last_message
        self.returncode = returncode
        self.stderr = stderr
        self.session_id = session_id
        self.write_path = write_path
        self.write_text = write_text
        self.wait_for_cancel = wait_for_cancel
        self.events = events or []
        self.calls: list[dict[str, Any]] = []
        self.started = threading.Event()

    def run(
        self,
        command: list[str],
        prompt: str,
        *,
        cwd: Path,
        job_dir: Path,
        cancel_event: threading.Event,
        on_event,
    ) -> WorkerRunResult:
        self.calls.append({"command": command, "prompt": prompt, "cwd": cwd, "job_dir": job_dir})
        self.started.set()
        on_event({"type": "session_configured", "session_id": self.session_id})
        for event in self.events:
            on_event(event)
        if self.wait_for_cancel:
            cancel_event.wait(timeout=5)
            return WorkerRunResult(returncode=-15, stderr="cancelled", cancelled=cancel_event.is_set())
        if self.write_path:
            target = cwd / self.write_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.write_text, encoding="utf-8")
        (job_dir / "last-message.md").write_text(self.last_message, encoding="utf-8")
        return WorkerRunResult(
            returncode=self.returncode,
            stdout=json.dumps({"item": {"type": "agent_message", "text": self.last_message}}) + "\n",
            stderr=self.stderr,
        )


def _write_example_step(project_root: Path) -> None:
    path = project_root / "example" / "exports" / "step" / "example" / "example_block.step"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")


def _init_git_project(project_root: Path) -> None:
    _write_example_step(project_root)
    (project_root / "flow").mkdir(exist_ok=True)
    (project_root / "flow" / "part.py").write_text("value = 1\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=project_root, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "flow@example.test"], cwd=project_root, check=True)
    subprocess.run(["git", "config", "user.name", "Flow Test"], cwd=project_root, check=True)
    subprocess.run(["git", "add", "flow/part.py"], cwd=project_root, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=project_root, check=True, capture_output=True, text=True)


def _client(tmp_path: Path, runner: RecordingWorkerRunner) -> TestClient:
    service = ViewerService(tmp_path)
    design_threads = DesignThreadService(service)
    manager = CodexWorkerJobManager(
        service,
        design_threads,
        codex_command="codex-test",
        model="gpt-test",
        runner=runner,
    )
    return TestClient(create_app(service=service, thread_service=design_threads, worker_job_manager=manager))


def _create_thread(client: TestClient, title: str = "Worker thread") -> str:
    response = client.post("/api/design-threads", json={"title": title})
    assert response.status_code == 200
    return response.json()["thread_id"]


def _start_job(client: TestClient, thread_id: str, message: str = "Update the part") -> str:
    response = client.post(
        f"/api/design-threads/{thread_id}/worker-jobs",
        json={
            "message": message,
            "context_snapshot": {"selected_part_ids": ["example_block"], "visible_part_ids": ["example_block"]},
            "attachments": ["att-1"],
            "metadata": {"source": "test", "viewer_api_base": "http://127.0.0.1:8001"},
        },
    )
    assert response.status_code == 200
    return response.json()["job"]["job_id"]


def _wait_for_status(client: TestClient, thread_id: str, job_id: str, status: str) -> dict[str, Any]:
    for _ in range(100):
        response = client.get(f"/api/design-threads/{thread_id}/worker-jobs/{job_id}")
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] == status:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"worker job did not reach {status}")


def test_codex_worker_initial_command_uses_workspace_write_stdin_and_last_message(tmp_path) -> None:
    _init_git_project(tmp_path)
    runner = RecordingWorkerRunner()
    client = _client(tmp_path, runner)
    thread_id = _create_thread(client)

    job_id = _start_job(client, thread_id)
    record = _wait_for_status(client, thread_id, job_id, "succeeded")

    assert runner.calls
    command = runner.calls[0]["command"]
    assert command[:3] == ["codex-test", "exec", "--json"]
    assert "--sandbox" in command
    assert command[command.index("--sandbox") + 1] == "workspace-write"
    assert "--skip-git-repo-check" in command
    assert "-C" in command
    assert command[command.index("-C") + 1] == str(tmp_path.resolve())
    assert "-o" in command
    assert command[command.index("-o") + 1].endswith("last-message.md")
    assert ["-m", "gpt-test"] == command[-3:-1]
    assert command[-1] == "-"
    assert "--ephemeral" not in command
    assert "FLOW_CAD_WORKER_CONTEXT=" in runner.calls[0]["prompt"]
    assert '"viewer_api_base": "http://127.0.0.1:8001"' in runner.calls[0]["prompt"]
    assert "flow reload --backend-url <metadata.viewer_api_base>" in runner.calls[0]["prompt"]
    assert record["codex_session_id"] == "session-123"


def test_worker_job_start_returns_visible_progress_before_completion(tmp_path) -> None:
    _init_git_project(tmp_path)
    runner = RecordingWorkerRunner(wait_for_cancel=True)
    client = _client(tmp_path, runner)
    thread_id = _create_thread(client)

    response = client.post(
        f"/api/design-threads/{thread_id}/worker-jobs",
        json={
            "message": "Run a long worker job",
            "context_snapshot": {"selected_part_ids": ["example_block"], "visible_part_ids": ["example_block"]},
            "metadata": {"viewer_api_base": "http://127.0.0.1:8001"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    job_id = payload["job"]["job_id"]
    progress_messages = [
        message
        for message in payload["messages"]
        if message["type"] == "status" and message["metadata"].get("worker_job_id") == job_id
    ]
    assert progress_messages
    assert progress_messages[0]["content"]["kind"] == "worker_status"
    assert progress_messages[0]["content"]["status"] == "starting"

    cancel_response = client.post(f"/api/design-threads/{thread_id}/worker-jobs/{job_id}/cancel", json={})
    assert cancel_response.status_code == 200


def test_codex_worker_followup_resumes_saved_session(tmp_path) -> None:
    _init_git_project(tmp_path)
    runner = RecordingWorkerRunner()
    client = _client(tmp_path, runner)
    thread_id = _create_thread(client)

    first_job = _start_job(client, thread_id, "First turn")
    _wait_for_status(client, thread_id, first_job, "succeeded")
    second_job = _start_job(client, thread_id, "Follow up")
    _wait_for_status(client, thread_id, second_job, "succeeded")

    command = runner.calls[1]["command"]
    assert command[:4] == ["codex-test", "exec", "resume", "--json"]
    assert "session-123" in command
    assert "--skip-git-repo-check" in command
    assert "-C" not in command
    assert command[-1] == "-"
    assert "--ephemeral" not in command


def test_worker_job_stream_and_thread_reload_persist_final_message_and_record(tmp_path) -> None:
    _init_git_project(tmp_path)
    runner = RecordingWorkerRunner(
        last_message="Changed flow/part.py.\n\nCommands run: python -m pytest tests/test_part.py",
        write_path="flow/part.py",
        write_text="value = 2\n",
    )
    client = _client(tmp_path, runner)
    thread_id = _create_thread(client)

    job_id = _start_job(client, thread_id)
    record = _wait_for_status(client, thread_id, job_id, "succeeded")
    assert record["changed_paths"] == ["flow/part.py"]
    assert record["commit_ready"] is True
    assert record["validation_evidence"]

    with client.stream("GET", f"/api/design-threads/{thread_id}/worker-jobs/{job_id}/stream") as response:
        stream_text = response.read().decode("utf-8")
    assert '"type": "succeeded"' in stream_text
    assert "Changed flow/part.py" in stream_text

    reloaded = TestClient(create_app(service=ViewerService(tmp_path))).get(f"/api/design-threads/{thread_id}")
    assert reloaded.status_code == 200
    thread = reloaded.json()
    assert thread["worker_job_count"] == 1
    assert thread["worker_jobs"][0]["job_id"] == job_id
    assert thread["messages"][-1]["metadata"]["worker_job_id"] == job_id


def test_worker_job_in_non_git_project_does_not_treat_git_error_as_changed_path(tmp_path) -> None:
    _write_example_step(tmp_path)
    runner = RecordingWorkerRunner(write_path="flow/part.py", write_text="value = 2\n")
    client = _client(tmp_path, runner)
    thread_id = _create_thread(client)

    job_id = _start_job(client, thread_id)
    record = _wait_for_status(client, thread_id, job_id, "succeeded")

    assert record["changed_paths"] == []
    assert record["commit_ready"] is False
    assert "git status unavailable" in record["pre_git_status"]
    assert record["diff_snapshot"]["paths"] == []
    assert record["diff_snapshot"]["git_error"]


def test_legacy_non_git_worker_job_record_is_not_exposed_as_commit_ready(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    design_threads = DesignThreadService(service)
    thread = design_threads.create_thread({"title": "Legacy no-git job"})
    thread_id = thread["thread_id"]
    job_id = "job-legacy"
    job_dir = service.project.paths.local_state / "design-threads" / thread_id / "worker-jobs" / job_id
    job_dir.mkdir(parents=True)
    legacy_record = {
        "schema_version": 1,
        "job_id": job_id,
        "thread_id": thread_id,
        "status": "succeeded",
        "created_at": "2026-06-09T12:00:00Z",
        "updated_at": "2026-06-09T12:05:00Z",
        "completed_at": "2026-06-09T12:05:00Z",
        "pre_git_status": "fatal: not a git repository (or any of the parent directories): .git\n",
        "post_git_status": "fatal: not a git repository (or any of the parent directories): .git\n",
        "changed_paths": ["al: not a git repository (or any of the parent directories): .git"],
        "diff_summary": "",
        "diff_snapshot": {
            "paths": ["al: not a git repository (or any of the parent directories): .git"],
            "status": "fatal: not a git repository (or any of the parent directories): .git\n",
            "summary": "",
            "entries": [{"path": "al: not a git repository (or any of the parent directories): .git"}],
        },
        "validation_evidence": [],
        "commit_ready": True,
    }
    (job_dir / "job.json").write_text(json.dumps(legacy_record), encoding="utf-8")

    thread_payload = design_threads.get_thread(thread_id)
    thread_job = thread_payload["worker_jobs"][0]
    assert thread_job["changed_paths"] == []
    assert thread_job["commit_ready"] is False

    manager = CodexWorkerJobManager(service, design_threads, runner=RecordingWorkerRunner())
    record = manager.get_job(thread_id, job_id)
    assert record["changed_paths"] == []
    assert record["commit_ready"] is False
    persisted = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
    assert persisted["changed_paths"] == []
    assert persisted["commit_ready"] is False


def test_worker_job_progress_messages_are_persisted_before_final_message(tmp_path) -> None:
    _init_git_project(tmp_path)
    runner = RecordingWorkerRunner(
        last_message="Finished the source update.",
        events=[{"item": {"type": "agent_message", "text": "Running flow cad build before finalizing."}}],
    )
    client = _client(tmp_path, runner)
    thread_id = _create_thread(client)

    job_id = _start_job(client, thread_id)
    _wait_for_status(client, thread_id, job_id, "succeeded")
    thread = client.get(f"/api/design-threads/{thread_id}").json()

    progress_messages = [
        message
        for message in thread["messages"]
        if message["type"] == "status" and message["metadata"].get("worker_job_id") == job_id
    ]
    assert progress_messages
    thinking_messages = [
        message
        for message in progress_messages
        if message["metadata"].get("worker_progress_kind") == "thinking"
    ]
    assert thinking_messages[0]["content"]["summary"] == "Running flow cad build before finalizing."
    assert thread["messages"][-1]["content"] == "Finished the source update."


def test_worker_job_command_and_file_progress_are_persisted(tmp_path) -> None:
    _init_git_project(tmp_path)
    runner = RecordingWorkerRunner(
        last_message="Finished.",
        events=[
            {
                "item": {
                    "id": "edit-1",
                    "type": "file_change",
                    "status": "completed",
                    "changes": [{"kind": "update", "path": str(tmp_path / "flow" / "part.py")}],
                }
            },
            {
                "item": {
                    "id": "cmd-1",
                    "type": "command_execution",
                    "status": "completed",
                    "command": "flow cad build --part example_block",
                    "exit_code": 0,
                    "aggregated_output": "Exported 1 STEP files\n",
                }
            },
        ],
    )
    client = _client(tmp_path, runner)
    thread_id = _create_thread(client)

    job_id = _start_job(client, thread_id)
    _wait_for_status(client, thread_id, job_id, "succeeded")
    thread = client.get(f"/api/design-threads/{thread_id}").json()
    progress_messages = [
        message
        for message in thread["messages"]
        if message["type"] == "status" and message["metadata"].get("worker_job_id") == job_id
    ]

    kinds = [message["metadata"].get("worker_progress_kind") for message in progress_messages]
    assert "file_change" in kinds
    assert "command" in kinds
    command_message = next(message for message in progress_messages if message["metadata"].get("worker_progress_kind") == "command")
    assert command_message["content"]["kind"] == "worker_command"
    assert command_message["content"]["command"] == "flow cad build --part example_block"
    assert command_message["content"]["status"] == "completed"


def test_reloaded_manager_marks_unattached_running_worker_job_failed(tmp_path) -> None:
    _write_example_step(tmp_path)
    service = ViewerService(tmp_path)
    design_threads = DesignThreadService(service)
    thread = design_threads.create_thread({"title": "Orphaned job"})
    thread_id = thread["thread_id"]
    job_id = "job-orphaned"
    job_dir = service.project.paths.local_state / "design-threads" / thread_id / "worker-jobs" / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "job_id": job_id,
                "thread_id": thread_id,
                "status": "running",
                "created_at": "2026-06-09T12:00:00Z",
                "updated_at": "2026-06-09T12:00:00Z",
                "started_at": "2026-06-09T12:00:00Z",
                "completed_at": None,
                "changed_paths": [],
                "diff_summary": "",
                "validation_evidence": [],
                "commit_ready": False,
            }
        ),
        encoding="utf-8",
    )

    reloaded_manager = CodexWorkerJobManager(service, design_threads, runner=RecordingWorkerRunner())
    record = reloaded_manager.get_job(thread_id, job_id)

    assert record["status"] == "failed"
    assert "no longer attached" in record["error"]
    assert record["commit_ready"] is False
    reloaded_thread = design_threads.get_thread(thread_id)
    assert "no longer attached" in reloaded_thread["messages"][-1]["content"]


def test_worker_job_failure_and_cancel_are_persisted(tmp_path) -> None:
    _init_git_project(tmp_path)
    failing_runner = RecordingWorkerRunner(returncode=2, stderr="boom")
    client = _client(tmp_path, failing_runner)
    thread_id = _create_thread(client, "Failure thread")
    failed_job = _start_job(client, thread_id)
    failed_record = _wait_for_status(client, thread_id, failed_job, "failed")
    assert failed_record["error"] == "boom"

    blocking_runner = RecordingWorkerRunner(wait_for_cancel=True)
    cancel_client = _client(tmp_path, blocking_runner)
    cancel_thread_id = _create_thread(cancel_client, "Cancel thread")
    cancel_job = _start_job(cancel_client, cancel_thread_id)
    assert blocking_runner.started.wait(timeout=2)
    response = cancel_client.post(f"/api/design-threads/{cancel_thread_id}/worker-jobs/{cancel_job}/cancel", json={})
    assert response.status_code == 200
    cancelled = _wait_for_status(cancel_client, cancel_thread_id, cancel_job, "cancelled")
    assert cancelled["status"] == "cancelled"


def test_worker_job_commit_commits_only_recorded_paths_and_detects_drift(tmp_path) -> None:
    _init_git_project(tmp_path)
    runner = RecordingWorkerRunner(write_path="flow/part.py", write_text="value = 2\n")
    client = _client(tmp_path, runner)
    thread_id = _create_thread(client)
    job_id = _start_job(client, thread_id)
    _wait_for_status(client, thread_id, job_id, "succeeded")

    (tmp_path / "unrelated.txt").write_text("leave me untracked\n", encoding="utf-8")
    commit_response = client.post(f"/api/design-threads/{thread_id}/worker-jobs/{job_id}/commit", json={})
    assert commit_response.status_code == 200
    committed = commit_response.json()["job"]
    assert committed["status"] == "committed"
    assert committed["commit_hash"]
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "?? unrelated.txt" in status
    assert "flow/part.py" not in status

    drift_runner = RecordingWorkerRunner(write_path="flow/part.py", write_text="value = 3\n")
    drift_client = _client(tmp_path, drift_runner)
    drift_thread = _create_thread(drift_client, "Drift thread")
    drift_job = _start_job(drift_client, drift_thread)
    _wait_for_status(drift_client, drift_thread, drift_job, "succeeded")
    (tmp_path / "flow" / "part.py").write_text("value = 4\n", encoding="utf-8")
    drift_response = drift_client.post(f"/api/design-threads/{drift_thread}/worker-jobs/{drift_job}/commit", json={})
    assert drift_response.status_code == 409
