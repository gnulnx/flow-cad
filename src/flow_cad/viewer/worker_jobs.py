from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from flow_cad.config import AgentProfile
from flow_cad.viewer.service import ViewerError, ViewerService
from flow_cad.viewer.threads import (
    DesignThreadService,
    ThreadValidationError,
    _append_jsonl,
    _as_mapping,
    _read_json,
    _read_jsonl,
    _safe_relative_path,
    _safe_thread_id,
    _utc_now,
    _write_json_atomic,
)


WORKER_JOB_SCHEMA_VERSION = 1
WORKER_JOB_EVENT_SCHEMA_VERSION = 1
WORKER_JOB_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled", "committed"}
TERMINAL_WORKER_JOB_STATUSES = {"succeeded", "failed", "cancelled", "committed"}
ORPHANED_WORKER_JOB_ERROR = (
    "Codex worker process is no longer attached to this viewer process. "
    "Start a new chat turn to continue."
)


class WorkerJobError(ViewerError):
    status_code = 400


class WorkerJobNotFoundError(WorkerJobError):
    status_code = 404


class WorkerJobConflictError(WorkerJobError):
    status_code = 409


@dataclass(frozen=True)
class WorkerRunResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    cancelled: bool = False


class CodexWorkerRunner(Protocol):
    def run(
        self,
        command: list[str],
        prompt: str,
        *,
        cwd: Path,
        job_dir: Path,
        cancel_event: threading.Event,
        on_event: Callable[[dict[str, Any]], None],
    ) -> WorkerRunResult:
        ...


class SubprocessCodexWorkerRunner:
    def run(
        self,
        command: list[str],
        prompt: str,
        *,
        cwd: Path,
        job_dir: Path,
        cancel_event: threading.Event,
        on_event: Callable[[dict[str, Any]], None],
    ) -> WorkerRunResult:
        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        except OSError as exc:
            return WorkerRunResult(returncode=127, stderr=str(exc))

        stdout_lines: list[str] = []
        stderr_lines: list[str] = []

        def read_stderr() -> None:
            if process.stderr is None:
                return
            for line in process.stderr:
                stderr_lines.append(line)

        def cancel_process() -> None:
            cancel_event.wait()
            if process.poll() is not None:
                return
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        cancel_thread = threading.Thread(target=cancel_process, daemon=True)
        stderr_thread.start()
        cancel_thread.start()

        if process.stdin is not None:
            try:
                process.stdin.write(prompt)
                process.stdin.close()
            except OSError:
                pass

        if process.stdout is not None:
            for line in process.stdout:
                stdout_lines.append(line)
                event = _json_object_from_line(line)
                if event is not None:
                    on_event(event)

        returncode = process.wait()
        stderr_thread.join(timeout=1)
        return WorkerRunResult(
            returncode=returncode,
            stdout="".join(stdout_lines),
            stderr="".join(stderr_lines),
            cancelled=cancel_event.is_set(),
        )


class CodexWorkerJobManager:
    def __init__(
        self,
        viewer_service: ViewerService,
        design_threads: DesignThreadService,
        *,
        agent_profile: AgentProfile | None = None,
        codex_command: str | None = None,
        model: str | None = None,
        runner: CodexWorkerRunner | None = None,
    ) -> None:
        self.viewer_service = viewer_service
        self.design_threads = design_threads
        self.project_root = viewer_service.project_root.resolve()
        self.threads_root = viewer_service.project.paths.local_state / "design-threads"
        local_state_relative = _safe_relative_path(
            str(viewer_service.project.paths.local_state.resolve()),
            base=self.project_root,
        )
        self._ignored_change_prefixes = [".flow"]
        if local_state_relative and local_state_relative not in self._ignored_change_prefixes:
            self._ignored_change_prefixes.append(local_state_relative)
        self.codex_command = codex_command or (agent_profile.command if agent_profile and agent_profile.command else "codex")
        self.model = model if model is not None else (agent_profile.model if agent_profile else None)
        self.runner = runner or SubprocessCodexWorkerRunner()
        self._cancel_events: dict[tuple[str, str], threading.Event] = {}
        self._lock = threading.RLock()

    def start_job(self, thread_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ThreadValidationError("worker job payload must be an object")

        prepared = self.design_threads.begin_chat_turn(thread_id, payload)
        thread_id = str(prepared["thread_id"])
        job_id = self._new_job_id(thread_id, payload.get("job_id"))
        job_dir = self._job_dir(thread_id, job_id)
        job_dir.mkdir(parents=True, exist_ok=False)

        resume_session_id = self._resume_session_id(thread_id, payload)
        prompt = self._build_prompt(thread_id, job_id, payload, prepared)
        prompt_path = job_dir / "prompt.md"
        prompt_path.write_text(prompt, encoding="utf-8")
        last_message_path = job_dir / "last-message.md"
        command = (
            self._resume_command(resume_session_id, last_message_path)
            if resume_session_id
            else self._initial_command(last_message_path)
        )
        now = _utc_now()
        record = {
            "schema_version": WORKER_JOB_SCHEMA_VERSION,
            "job_id": job_id,
            "thread_id": thread_id,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
            "committed_at": None,
            "commit_hash": None,
            "codex_session_id": resume_session_id,
            "resumed_from_session_id": resume_session_id,
            "command": command,
            "prompt_path": str(prompt_path.relative_to(job_dir)),
            "last_message_path": str(last_message_path.relative_to(job_dir)),
            "user_message_id": prepared["user_message"]["message_id"],
            "assistant_message_id": None,
            "context_snapshot_id": (
                prepared["context_snapshot"]["snapshot_id"]
                if isinstance(prepared.get("context_snapshot"), dict)
                else None
            ),
            "model": self.model,
            "pre_git_status": self._git_status_text(),
            "post_git_status": None,
            "changed_paths": [],
            "diff_summary": "",
            "diff_snapshot": None,
            "validation_evidence": [],
            "commit_ready": False,
            "exit_code": None,
            "error": None,
        }
        self._write_job(thread_id, job_id, record)
        self._append_event(thread_id, job_id, {"type": "queued", "job": record})
        start_message = self._append_progress_message(
            thread_id,
            job_id,
            record,
            "Starting Codex worker in the project workspace.",
            kind="status",
            details={"status": "starting"},
        )
        self._append_event(
            thread_id,
            job_id,
            {"type": "assistant_progress", "job": record, "message": start_message},
        )

        cancel_event = threading.Event()
        self._cancel_events[(thread_id, job_id)] = cancel_event
        worker = threading.Thread(
            target=self._run_job,
            args=(thread_id, job_id, command, prompt, job_dir, cancel_event),
            daemon=True,
        )
        worker.start()

        return {
            "ok": True,
            "thread_id": thread_id,
            "job": self.get_job(thread_id, job_id),
            "messages": [prepared["user_message"], start_message],
            "context_snapshot": prepared.get("context_snapshot"),
            "thread": self.design_threads.get_thread(thread_id),
        }

    def get_job(self, thread_id: str, job_id: str) -> dict[str, Any]:
        self.design_threads.get_thread(thread_id)
        safe_job_id = _safe_thread_id(job_id, fallback="job")
        record = _read_json(self._job_path(thread_id, safe_job_id))
        if record is None:
            raise WorkerJobNotFoundError(f"Worker job not found: {safe_job_id} in thread {thread_id}")
        record = self._sanitize_legacy_job_record(thread_id, safe_job_id, record)
        return self._mark_orphaned_job_failed(thread_id, safe_job_id, record)

    def stream_events(self, thread_id: str, job_id: str) -> Any:
        self.get_job(thread_id, job_id)
        events_path = self._job_events_path(thread_id, job_id)
        yielded = 0
        deadline = time.monotonic() + 60 * 60
        last_flush = time.monotonic()
        while time.monotonic() < deadline:
            events = _read_jsonl(events_path)
            for event in events[yielded:]:
                yielded += 1
                last_flush = time.monotonic()
                yield _sse(event)
            record = self.get_job(thread_id, job_id)
            if str(record.get("status")) in TERMINAL_WORKER_JOB_STATUSES:
                events = _read_jsonl(events_path)
                for event in events[yielded:]:
                    yielded += 1
                    last_flush = time.monotonic()
                    yield _sse(event)
                yield _sse({"done": True, "job": record, "thread": self.design_threads.get_thread(thread_id)})
                yield "data: [DONE]\n\n"
                return
            if time.monotonic() - last_flush >= 1:
                last_flush = time.monotonic()
                yield ": keepalive\n\n"
            time.sleep(0.05)
        yield _sse({"event": {"type": "error", "error": "Worker job stream timed out"}})
        yield "data: [DONE]\n\n"

    def cancel_job(self, thread_id: str, job_id: str) -> dict[str, Any]:
        record = self.get_job(thread_id, job_id)
        if str(record.get("status")) in TERMINAL_WORKER_JOB_STATUSES:
            return {"ok": True, "job": record, "thread": self.design_threads.get_thread(thread_id)}
        cancel_event = self._cancel_events.get((thread_id, _safe_thread_id(job_id, fallback="job")))
        if cancel_event is not None:
            cancel_event.set()
        now = _utc_now()
        record.update({"status": "cancelled", "updated_at": now, "completed_at": now, "error": "cancelled"})
        self._write_job(thread_id, job_id, record)
        message = self._append_terminal_message(thread_id, job_id, record, "Codex worker job cancelled.")
        record["assistant_message_id"] = message["message_id"]
        self._write_job(thread_id, job_id, record)
        self._append_event(thread_id, job_id, {"type": "cancelled", "job": record, "message": message})
        return {"ok": True, "job": record, "message": message, "thread": self.design_threads.get_thread(thread_id)}

    def commit_job(self, thread_id: str, job_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        record = self.get_job(thread_id, job_id)
        status = str(record.get("status") or "")
        if status != "succeeded":
            raise WorkerJobConflictError(f"Worker job must be succeeded before commit; current status is {status}")
        changed_paths = self._filter_commit_paths(_normalize_changed_paths(record.get("changed_paths"), base=self.project_root))
        if not changed_paths:
            raise WorkerJobConflictError("Worker job has no changed paths to commit")

        stored_snapshot = _as_mapping(record.get("diff_snapshot"))
        current_snapshot = self._git_change_snapshot(paths=changed_paths)
        if stored_snapshot.get("hash") != current_snapshot.get("hash"):
            raise WorkerJobConflictError("Worker job diff has drifted since completion")

        commit_message = self._commit_message(record, payload if isinstance(payload, dict) else {})
        self._run_git(["add", "--", *changed_paths])
        commit = self._run_git(["commit", "-m", commit_message, "--only", "--", *changed_paths], check=False)
        if commit.returncode != 0:
            raise WorkerJobConflictError((commit.stderr or commit.stdout or "git commit failed").strip())
        commit_hash = self._run_git(["rev-parse", "HEAD"]).stdout.strip()

        now = _utc_now()
        record.update(
            {
                "status": "committed",
                "updated_at": now,
                "committed_at": now,
                "commit_hash": commit_hash,
                "commit_ready": False,
            }
        )
        self._write_job(thread_id, job_id, record)
        message = self.design_threads.append_message(
            thread_id,
            {
                "type": "status",
                "role": "system",
                "content": {
                    "summary": f"Committed Codex worker job {job_id}",
                    "commit_hash": commit_hash,
                    "changed_paths": changed_paths,
                },
                "metadata": {
                    "worker_job_id": job_id,
                    "worker_job_status": "committed",
                    "commit_hash": commit_hash,
                    "changed_paths": changed_paths,
                },
            },
        )
        self._append_event(thread_id, job_id, {"type": "committed", "job": record, "message": message})
        return {"ok": True, "job": record, "message": message, "thread": self.design_threads.get_thread(thread_id)}

    def _run_job(
        self,
        thread_id: str,
        job_id: str,
        command: list[str],
        prompt: str,
        job_dir: Path,
        cancel_event: threading.Event,
    ) -> None:
        record = self.get_job(thread_id, job_id)
        if str(record.get("status")) == "cancelled":
            return
        record.update({"status": "running", "started_at": _utc_now(), "updated_at": _utc_now()})
        self._write_job(thread_id, job_id, record)
        self._append_event(thread_id, job_id, {"type": "running", "job": record})

        codex_events: list[dict[str, Any]] = []
        progress_message_keys: set[str] = set()

        def on_codex_event(event: dict[str, Any]) -> None:
            codex_events.append(event)
            session_id = _extract_codex_session_id(event)
            if session_id:
                with self._lock:
                    current = self.get_job(thread_id, job_id)
                    current["codex_session_id"] = session_id
                    current["updated_at"] = _utc_now()
                    self._write_job(thread_id, job_id, current)
            self._append_event(thread_id, job_id, {"type": "codex_event", "codex_event": event})
            event_type = str(event.get("type") or "")
            if event_type == "turn.started":
                self._append_codex_progress_once(
                    thread_id,
                    job_id,
                    progress_message_keys,
                    kind="status",
                    summary="Codex is thinking through the requested change.",
                    details={"status": "running"},
                )
            agent_text = _codex_agent_message_text(event)
            if agent_text:
                self._append_codex_progress_once(
                    thread_id,
                    job_id,
                    progress_message_keys,
                    kind="thinking",
                    summary=agent_text,
                )
            command_progress = _codex_command_progress(event)
            if command_progress:
                self._append_codex_progress_once(
                    thread_id,
                    job_id,
                    progress_message_keys,
                    kind="command",
                    summary=command_progress["summary"],
                    details=command_progress,
                )
            file_progress = _codex_file_progress(event)
            if file_progress:
                self._append_codex_progress_once(
                    thread_id,
                    job_id,
                    progress_message_keys,
                    kind="file_change",
                    summary=file_progress["summary"],
                    details=file_progress,
                )

        try:
            result = self.runner.run(
                command,
                prompt,
                cwd=self.project_root,
                job_dir=job_dir,
                cancel_event=cancel_event,
                on_event=on_codex_event,
            )
        except Exception as exc:  # pragma: no cover - defensive process boundary
            result = WorkerRunResult(returncode=1, stderr=str(exc))

        record = self.get_job(thread_id, job_id)
        last_message = _read_text(job_dir / "last-message.md").strip()
        if not last_message:
            last_message = _final_agent_text(result.stdout).strip()
        changed_snapshot = self._git_change_snapshot()
        validation_evidence = _extract_validation_evidence(last_message, codex_events)
        now = _utc_now()

        if cancel_event.is_set() or result.cancelled or str(record.get("status")) == "cancelled":
            status = "cancelled"
            error = "cancelled"
            content = "Codex worker job cancelled."
        elif result.returncode != 0:
            status = "failed"
            error = (result.stderr or result.stdout or f"Codex exited with status {result.returncode}").strip()
            content = f"Codex worker job failed.\n\n{error}"
        else:
            status = "succeeded"
            error = None
            content = last_message or "Codex worker job completed."

        record.update(
            {
                "status": status,
                "updated_at": now,
                "completed_at": now,
                "exit_code": result.returncode,
                "error": error,
                "post_git_status": self._git_status_text(),
                "changed_paths": changed_snapshot["paths"],
                "diff_summary": changed_snapshot["summary"],
                "diff_snapshot": changed_snapshot,
                "validation_evidence": validation_evidence,
                "commit_ready": status == "succeeded" and bool(changed_snapshot["paths"]),
            }
        )
        self._write_job(thread_id, job_id, record)
        if status == "cancelled" and record.get("assistant_message_id"):
            self._append_event(thread_id, job_id, {"type": status, "job": record, "thread": self.design_threads.get_thread(thread_id)})
        else:
            message = self._append_terminal_message(thread_id, job_id, record, content)
            record["assistant_message_id"] = message["message_id"]
            self._write_job(thread_id, job_id, record)
            self._append_event(thread_id, job_id, {"type": status, "job": record, "message": message, "thread": self.design_threads.get_thread(thread_id)})
        self._cancel_events.pop((thread_id, job_id), None)

    def _append_terminal_message(
        self,
        thread_id: str,
        job_id: str,
        record: dict[str, Any],
        content: str,
    ) -> dict[str, Any]:
        status = str(record.get("status") or "unknown")
        return self.design_threads.append_message(
            thread_id,
            {
                "type": "assistant_message",
                "role": "assistant",
                "content": content,
                "metadata": {
                    "runtime": "codex_worker",
                    "worker_job_id": job_id,
                    "worker_job_status": status,
                    "codex_session_id": record.get("codex_session_id"),
                    "changed_paths": record.get("changed_paths") or [],
                    "diff_summary": record.get("diff_summary") or "",
                    "validation_evidence": record.get("validation_evidence") or [],
                    "commit_ready": bool(record.get("commit_ready")),
                    **({"error": record.get("error")} if record.get("error") else {}),
                },
            },
        )

    def _initial_command(self, last_message_path: Path) -> list[str]:
        command = [
            self._codex_executable(),
            "exec",
            "--json",
            "--sandbox",
            "workspace-write",
            "--skip-git-repo-check",
            "-C",
            str(self.project_root),
            "-o",
            str(last_message_path),
        ]
        if self.model:
            command.extend(["-m", self.model])
        command.append("-")
        return command

    def _resume_command(self, session_id: str, last_message_path: Path) -> list[str]:
        command = [
            self._codex_executable(),
            "exec",
            "resume",
            "--json",
            session_id,
            "--skip-git-repo-check",
            "-o",
            str(last_message_path),
        ]
        if self.model:
            command.extend(["-m", self.model])
        command.append("-")
        return command

    def _build_prompt(
        self,
        thread_id: str,
        job_id: str,
        payload: dict[str, Any],
        prepared: dict[str, Any],
    ) -> str:
        context_packet = self.design_threads.assistant_context_packet(
            thread_id,
            context_snapshot=prepared.get("context_snapshot") if isinstance(prepared.get("context_snapshot"), dict) else None,
        )
        metadata = _as_mapping(payload.get("metadata"))
        prompt_payload = {
            "thread_id": thread_id,
            "worker_job_id": job_id,
            "user_message": prepared["message_text"],
            "context_packet": context_packet,
            "attachments": payload.get("attachments") if isinstance(payload.get("attachments"), list) else [],
            "metadata": metadata,
            "project_root": str(self.project_root),
        }
        return (
            "You are a Codex worker running inside the Flow CAD design-thread chat.\n"
            "Operate in the active Flow CAD project root with workspace-write permissions.\n"
            "You may inspect, reason about, and edit project Python/source/docs/tests. "
            "You may run shell commands needed for the task, including `flow cad build`, "
            "project validators, and focused tests.\n"
            "Do not commit changes. Leave a reviewable working-tree diff for the user.\n"
            "Prefer small source-level changes over generated-output edits. "
            "Do not hand-edit generated project outputs when a source or generator should be changed.\n"
            "If metadata.viewer_api_base is present, use it for viewer API checks and "
            "`flow reload --backend-url <metadata.viewer_api_base>` instead of guessing a port.\n"
            "At the end, report changed files, commands run, validation/build evidence, failures, "
            "and remaining risk.\n\n"
            f"FLOW_CAD_WORKER_CONTEXT={json.dumps(prompt_payload, ensure_ascii=False, sort_keys=True)}"
        )

    def _resume_session_id(self, thread_id: str, payload: dict[str, Any]) -> str | None:
        explicit = payload.get("codex_session_id") or payload.get("resume_session_id")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()
        for job in reversed(self._thread_jobs(thread_id)):
            session_id = job.get("codex_session_id")
            if isinstance(session_id, str) and session_id.strip():
                return session_id.strip()
        return None

    def _new_job_id(self, thread_id: str, requested: Any) -> str:
        if isinstance(requested, str) and requested.strip():
            base = _safe_thread_id(requested, fallback="job")
        else:
            base = f"job_{uuid.uuid4().hex[:12]}"
        job_id = base
        while self._job_path(thread_id, job_id).exists():
            job_id = f"{base}-{uuid.uuid4().hex[:6]}"
        return job_id

    def _thread_jobs(self, thread_id: str) -> list[dict[str, Any]]:
        jobs_dir = self._thread_jobs_dir(thread_id)
        return [
            _read_json(path) or {"job_id": path.parent.name, "status": "unknown"}
            for path in sorted(jobs_dir.glob("*/job.json"))
            if path.is_file()
        ]

    def _thread_jobs_dir(self, thread_id: str) -> Path:
        return self.threads_root / _safe_thread_id(thread_id, fallback="thread") / "worker-jobs"

    def _job_dir(self, thread_id: str, job_id: str) -> Path:
        return self._thread_jobs_dir(thread_id) / _safe_thread_id(job_id, fallback="job")

    def _job_path(self, thread_id: str, job_id: str) -> Path:
        return self._job_dir(thread_id, job_id) / "job.json"

    def _job_events_path(self, thread_id: str, job_id: str) -> Path:
        return self._job_dir(thread_id, job_id) / "events.jsonl"

    def _write_job(self, thread_id: str, job_id: str, record: dict[str, Any]) -> None:
        record["schema_version"] = WORKER_JOB_SCHEMA_VERSION
        _write_json_atomic(self._job_path(thread_id, job_id), record)

    def _sanitize_legacy_job_record(self, thread_id: str, job_id: str, record: dict[str, Any]) -> dict[str, Any]:
        sanitized = _sanitize_legacy_git_unavailable_job(record)
        if sanitized is not record:
            self._write_job(thread_id, job_id, sanitized)
        return sanitized

    def _mark_orphaned_job_failed(self, thread_id: str, job_id: str, record: dict[str, Any]) -> dict[str, Any]:
        status = str(record.get("status") or "")
        if status not in {"queued", "running"}:
            return record
        if (thread_id, _safe_thread_id(job_id, fallback="job")) in self._cancel_events:
            return record

        now = _utc_now()
        record.update(
            {
                "status": "failed",
                "updated_at": now,
                "completed_at": now,
                "exit_code": None,
                "error": ORPHANED_WORKER_JOB_ERROR,
                "post_git_status": record.get("post_git_status") or self._git_status_text(),
                "commit_ready": False,
            }
        )
        self._write_job(thread_id, job_id, record)
        if not record.get("assistant_message_id"):
            message = self._append_terminal_message(thread_id, job_id, record, f"Codex worker job failed.\n\n{ORPHANED_WORKER_JOB_ERROR}")
            record["assistant_message_id"] = message["message_id"]
            self._write_job(thread_id, job_id, record)
        else:
            message = None
        event: dict[str, Any] = {"type": "failed", "job": record, "thread": self.design_threads.get_thread(thread_id)}
        if message is not None:
            event["message"] = message
        self._append_event(thread_id, job_id, event)
        return record

    def _append_event(self, thread_id: str, job_id: str, payload: dict[str, Any]) -> None:
        event = {
            "schema_version": WORKER_JOB_EVENT_SCHEMA_VERSION,
            "thread_id": thread_id,
            "job_id": job_id,
            "created_at": _utc_now(),
            **payload,
        }
        _append_jsonl(self._job_events_path(thread_id, job_id), event)

    def _append_progress_message(
        self,
        thread_id: str,
        job_id: str,
        record: dict[str, Any],
        content: str,
        *,
        kind: str = "thinking",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        content_payload = {
            "kind": f"worker_{kind}",
            "summary": content,
            **(details or {}),
        }
        return self.design_threads.append_message(
            thread_id,
            {
                "type": "status",
                "role": "assistant",
                "content": content_payload,
                "metadata": {
                    "runtime": "codex_worker",
                    "worker_job_id": job_id,
                    "worker_job_status": str(record.get("status") or "running"),
                    "codex_session_id": record.get("codex_session_id"),
                    "worker_job_progress": True,
                    "worker_progress_kind": kind,
                },
            },
        )

    def _append_codex_progress_once(
        self,
        thread_id: str,
        job_id: str,
        progress_message_keys: set[str],
        *,
        kind: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        key_payload = {"kind": kind, "summary": summary, "details": details or {}}
        message_key = hashlib.sha256(json.dumps(key_payload, sort_keys=True).encode("utf-8")).hexdigest()
        if message_key in progress_message_keys:
            return
        progress_message_keys.add(message_key)
        with self._lock:
            current = self.get_job(thread_id, job_id)
            message = self._append_progress_message(
                thread_id,
                job_id,
                current,
                summary,
                kind=kind,
                details=details,
            )
        self._append_event(
            thread_id,
            job_id,
            {"type": "assistant_progress", "job": self.get_job(thread_id, job_id), "message": message},
        )

    def _codex_executable(self) -> str:
        return shutil.which(self.codex_command) or self.codex_command

    def _git_status_text(self, paths: list[str] | None = None) -> str:
        result = self._git_status_result(paths)
        if result.returncode == 0:
            return result.stdout
        error = (result.stderr or result.stdout).strip()
        return f"git status unavailable: {error}\n" if error else ""

    def _git_status_result(self, paths: list[str] | None = None) -> subprocess.CompletedProcess[str]:
        args = ["status", "--porcelain", "--untracked-files=all"]
        if paths:
            args.extend(["--", *paths])
        return self._run_git(args, check=False)

    def _git_change_snapshot(self, paths: list[str] | None = None) -> dict[str, Any]:
        scoped_paths = _normalize_changed_paths(paths, base=self.project_root) if paths is not None else None
        status_result = self._git_status_result(scoped_paths)
        if status_result.returncode != 0:
            payload = {
                "paths": [],
                "status": "",
                "summary": "",
                "entries": [],
                "git_error": (status_result.stderr or status_result.stdout).strip(),
            }
            payload["hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
            return payload

        status_text = status_result.stdout
        all_paths = _status_paths(status_text)
        changed_paths = self._filter_commit_paths(
            _normalize_changed_paths(scoped_paths if scoped_paths is not None else all_paths, base=self.project_root)
        )
        summary = ""
        if changed_paths:
            stat = self._run_git(["diff", "--stat", "--", *changed_paths], check=False)
            summary = stat.stdout.strip()
            untracked = [path for path in changed_paths if (self.project_root / path).exists() and f"?? {path}" in status_text]
            if untracked:
                untracked_summary = "\n".join(f"untracked: {path}" for path in untracked)
                summary = "\n".join(part for part in [summary, untracked_summary] if part)
        entries = []
        for path in changed_paths:
            full_path = (self.project_root / path).resolve()
            if full_path.is_file():
                digest = hashlib.sha256(full_path.read_bytes()).hexdigest()
                state = "file"
            elif full_path.exists():
                digest = "directory"
                state = "directory"
            else:
                digest = "missing"
                state = "missing"
            entries.append({"path": path, "state": state, "sha256": digest})
        filtered_status_text = _filter_status_text(status_text, changed_paths)
        payload = {
            "paths": changed_paths,
            "status": filtered_status_text,
            "summary": summary,
            "entries": entries,
        }
        payload["hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        return payload

    def _run_git(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", "-C", str(self.project_root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
        if check and result.returncode != 0:
            raise WorkerJobError((result.stderr or result.stdout or "git command failed").strip())
        return result

    def _commit_message(self, record: dict[str, Any], payload: dict[str, Any]) -> str:
        raw = payload.get("message")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        job_id = str(record.get("job_id") or "worker-job")
        return f"Apply Codex worker job {job_id}"

    def _filter_commit_paths(self, paths: list[str]) -> list[str]:
        return [
            path
            for path in paths
            if not any(path == prefix or path.startswith(f"{prefix}/") for prefix in self._ignored_change_prefixes)
        ]


def _json_object_from_line(line: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False, sort_keys=True)}\n\n"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _extract_codex_session_id(event: dict[str, Any]) -> str | None:
    for key in ("session_id", "conversation_id", "codex_session_id"):
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    item = event.get("item")
    if isinstance(item, dict):
        for key in ("session_id", "conversation_id", "codex_session_id"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if str(item.get("type") or "").startswith("session"):
            value = item.get("id")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _final_agent_text(stdout: str) -> str:
    last_text = ""
    for line in stdout.splitlines():
        event = _json_object_from_line(line)
        if not event:
            continue
        text = _codex_agent_message_text(event)
        if text:
            last_text = text
    return last_text


def _codex_agent_message_text(event: dict[str, Any]) -> str | None:
    item = event.get("item")
    candidate = item if isinstance(item, dict) else event
    item_type = str(candidate.get("type") or "")
    event_type = str(event.get("type") or "")
    role = str(candidate.get("role") or "")
    if item_type != "agent_message" and not (item_type == "message" and role == "assistant") and event_type != "agent_message":
        return None

    text = candidate.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()

    message = candidate.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()

    content = candidate.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str) and part.strip():
                parts.append(part.strip())
            elif isinstance(part, dict):
                part_text = part.get("text") or part.get("content")
                if isinstance(part_text, str) and part_text.strip():
                    parts.append(part_text.strip())
        if parts:
            return "\n".join(parts)
    return None


def _codex_command_progress(event: dict[str, Any]) -> dict[str, Any] | None:
    item = event.get("item")
    if not isinstance(item, dict) or item.get("type") != "command_execution":
        return None
    command = item.get("command")
    if not isinstance(command, str) or not command.strip():
        return None
    status = str(item.get("status") or "running")
    exit_code = item.get("exit_code")
    output = item.get("aggregated_output")
    if isinstance(output, str) and len(output) > 2000:
        output = output[-2000:]
    summary_status = {
        "in_progress": "Running",
        "completed": "Completed",
        "failed": "Failed",
    }.get(status, status.replace("_", " ").title())
    return {
        "summary": f"{summary_status}: {command}",
        "command": command,
        "status": status,
        "exit_code": exit_code if isinstance(exit_code, int) else None,
        **({"output": output} if isinstance(output, str) and output.strip() else {}),
    }


def _codex_file_progress(event: dict[str, Any]) -> dict[str, Any] | None:
    item = event.get("item")
    if not isinstance(item, dict) or item.get("type") != "file_change":
        return None
    changes = item.get("changes")
    if not isinstance(changes, list):
        return None
    paths: list[str] = []
    for change in changes:
        if not isinstance(change, dict):
            continue
        path = change.get("path")
        if isinstance(path, str) and path.strip():
            paths.append(path.strip())
    if not paths:
        return None
    status = str(item.get("status") or "running")
    summary_status = "Updated" if status == "completed" else "Editing"
    visible_paths = ", ".join(paths[:3])
    if len(paths) > 3:
        visible_paths = f"{visible_paths}, +{len(paths) - 3} more"
    return {
        "summary": f"{summary_status}: {visible_paths}",
        "status": status,
        "paths": paths,
    }


def _extract_validation_evidence(last_message: str, codex_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for line in last_message.splitlines():
        text = line.strip().strip("-* ")
        lower = text.lower()
        if not text:
            continue
        if any(token in lower for token in ("pytest", "flow cad build", "flow validate", "validator", "validation")):
            evidence.append({"source": "last_message", "summary": text})

    for event in codex_events:
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        command = item.get("command") or item.get("cmd")
        if isinstance(command, str) and any(token in command for token in ("pytest", "flow cad build", "flow validate")):
            evidence.append({"source": "codex_event", "command": command, "status": item.get("status")})

    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in evidence:
        key = json.dumps(item, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _status_paths(status_text: str) -> list[str]:
    paths: list[str] = []
    for line in status_text.splitlines():
        if not line.strip() or len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", maxsplit=1)[1].strip()
        if path:
            paths.append(path)
    return paths


def _filter_status_text(status_text: str, paths: list[str]) -> str:
    allowed = set(paths)
    lines: list[str] = []
    for line in status_text.splitlines():
        if not line.strip() or len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", maxsplit=1)[1].strip()
        if path in allowed:
            lines.append(line)
    return "\n".join(lines) + ("\n" if lines else "")


def _normalize_changed_paths(value: Any, *, base: Path) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        path = _safe_relative_path(str(item), base=base)
        if path == ".flow" or path.startswith(".flow/"):
            continue
        if path and path not in normalized:
            normalized.append(path)
    return normalized


def _sanitize_legacy_git_unavailable_job(record: dict[str, Any]) -> dict[str, Any]:
    if not _worker_job_has_git_unavailable_diff(record):
        return record
    sanitized = dict(record)
    sanitized["changed_paths"] = []
    sanitized["diff_summary"] = ""
    sanitized["commit_ready"] = False
    snapshot = sanitized.get("diff_snapshot")
    if isinstance(snapshot, dict):
        sanitized["diff_snapshot"] = {
            **snapshot,
            "paths": [],
            "status": "",
            "summary": "",
            "entries": [],
            "git_error": snapshot.get("git_error") or sanitized.get("post_git_status") or sanitized.get("pre_git_status") or "",
        }
    return sanitized


def _worker_job_has_git_unavailable_diff(record: dict[str, Any]) -> bool:
    if not record.get("commit_ready") and not record.get("changed_paths"):
        return False
    text_parts = [
        str(record.get("pre_git_status") or ""),
        str(record.get("post_git_status") or ""),
        str(record.get("diff_summary") or ""),
    ]
    for path in record.get("changed_paths") or []:
        text_parts.append(str(path))
    snapshot = record.get("diff_snapshot")
    if isinstance(snapshot, dict):
        text_parts.append(str(snapshot.get("status") or ""))
        text_parts.append(str(snapshot.get("git_error") or ""))
    return "not a git repository" in "\n".join(text_parts).lower()
