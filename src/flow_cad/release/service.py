"""Strict-manifest production release gate orchestration."""

from __future__ import annotations

import hashlib
import json
import os
import selectors
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from flow_cad.build import plan_scoped_part_build
from flow_cad.jobs import JobCancelled, JobContext, JobService, JobSubmission
from flow_cad.registry import sync_project
from flow_cad.registry.db import connect_readonly, database_path
from flow_cad.sdk import PartStatus, ProjectManifest, ReleaseHookKind, load_manifest
from flow_cad.validation.ownership import OwnershipScanConfig, scan_ownership
from flow_cad.viewer.services import InventoryService


TARGET_SECONDS = 120.0
HARD_TIMEOUT_SECONDS = 180.0
SCOPED_PART_HARD_SECONDS = 15.0
REPORT_RELATIVE_PATH = Path(".flow/release/latest.json")
ARTIFACT_MANIFEST_RELATIVE_PATH = Path(".flow/release/artifact-manifest.sha256")


class ReleaseGateError(RuntimeError):
    """A production release phase failed with attributed evidence."""


class ReleaseGateTimeoutError(ReleaseGateError):
    """The hard gate or one explicitly bounded phase exceeded its deadline."""


@dataclass(frozen=True, slots=True)
class ProcessResult:
    messages: tuple[dict[str, Any], ...]
    output: tuple[str, ...]
    elapsed_seconds: float


class ReleaseGateService:
    """Submit idempotent release gates through a project's shared job service."""

    def __init__(self, project_root: Path, jobs: JobService) -> None:
        self.project_root = project_root.resolve()
        if jobs.store.project_root != self.project_root:
            raise ValueError("job service and release service must use the same project root")
        self.jobs = jobs

    def submit(self, *, request_id: str) -> JobSubmission:
        manifest = load_manifest(self.project_root / "flowcad.project.yaml")
        return self.jobs.submit(
            request_id=request_id,
            kind="release-gate",
            payload={
                "project_id": manifest.project_id,
                "target_seconds": TARGET_SECONDS,
                "hard_timeout_seconds": HARD_TIMEOUT_SECONDS,
            },
            work=_release_gate_work(self.project_root),
        )


def _release_gate_work(project_root: Path):
    def work(context: JobContext) -> Mapping[str, Any]:
        return _run_release_gate(project_root.resolve(), context)

    return work


def _run_release_gate(project_root: Path, context: JobContext) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + HARD_TIMEOUT_SECONDS
    report_path = project_root / REPORT_RELATIVE_PATH
    phases: list[dict[str, Any]] = []
    current_phase = "manifest"
    manifest: ProjectManifest | None = None
    build_results: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "project_root": str(project_root),
        "target_seconds": TARGET_SECONDS,
        "hard_timeout_seconds": HARD_TIMEOUT_SECONDS,
        "scoped_part_hard_seconds": SCOPED_PART_HARD_SECONDS,
        "started_at": datetime.now(UTC).isoformat(),
        "phases": phases,
    }

    def run_phase(
        key: str,
        progress: float,
        message: str,
        action: Callable[[], Any],
    ) -> Any:
        nonlocal current_phase
        current_phase = key
        _check_deadline(context, deadline, key)
        context.report(key, progress, message)
        phase_started = time.monotonic()
        try:
            details = action()
        except BaseException as error:
            phases.append(
                {
                    "key": key,
                    "status": "failed",
                    "elapsed_seconds": time.monotonic() - phase_started,
                    "error": f"{type(error).__name__}: {error}",
                }
            )
            raise
        phases.append(
            {
                "key": key,
                "status": "passed",
                "elapsed_seconds": time.monotonic() - phase_started,
                "details": details,
            }
        )
        return details

    try:
        def manifest_phase() -> dict[str, Any]:
            nonlocal manifest
            manifest = load_manifest(project_root / "flowcad.project.yaml")
            if manifest.parameter_provider is None:
                raise ReleaseGateError("strict manifest must declare parameter_provider")
            active = tuple(part for part in manifest.parts if part.status is PartStatus.ACTIVE)
            if not active:
                raise ReleaseGateError("release gate requires at least one active part")
            for part in active:
                plan_scoped_part_build(project_root, manifest, part)
            for hook in manifest.release_hooks:
                _validate_project_reference(
                    hook.provider,
                    manifest.python_package,
                    f"release hook {hook.key!r}",
                )
            sync = sync_project(project_root)
            with closing(connect_readonly(database_path(project_root))) as connection:
                foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
                indexed_parts = int(connection.execute("SELECT COUNT(*) FROM parts").fetchone()[0])
                indexed_occurrences = int(
                    connection.execute("SELECT COUNT(*) FROM assembly_occurrences").fetchone()[0]
                )
            if foreign_key_issues:
                raise ReleaseGateError(
                    f"registry foreign-key check reported {len(foreign_key_issues)} issue(s)"
                )
            expected_occurrences = sum(
                len(assembly.occurrences) for assembly in manifest.assemblies
            )
            if indexed_parts != len(manifest.parts) or indexed_occurrences != expected_occurrences:
                raise ReleaseGateError("registry counts do not match the strict manifest")
            report["project_id"] = manifest.project_id
            report["active_part_count"] = len(active)
            return {
                "manifest_schema_version": manifest.schema_version,
                "registry_revision": sync.revision,
                "part_count": indexed_parts,
                "active_part_count": len(active),
                "occurrence_count": indexed_occurrences,
            }

        run_phase("manifest_registry", 0.02, "Validating manifest and registry", manifest_phase)
        assert manifest is not None

        def ownership_phase() -> dict[str, Any]:
            package_root = project_root.joinpath(*manifest.python_package.split("."))
            if not package_root.is_dir():
                raise ReleaseGateError(f"project package not found: {package_root}")
            runtime_root = Path(__file__).resolve().parents[1]
            result = scan_ownership(
                OwnershipScanConfig(
                    downstream_root=package_root,
                    runtime_python_files=tuple(sorted(runtime_root.rglob("*.py"))),
                )
            )
            if not result.ok:
                first = result.issues[0]
                raise ReleaseGateError(
                    f"ownership/dependency boundary failed: {first.path}: {first.message}"
                )
            return {"file_count": result.file_count, "issue_count": 0}

        run_phase("ownership", 0.08, "Checking downstream dependency ownership", ownership_phase)

        symbols_result = run_phase(
            "symbols",
            0.12,
            "Import-checking project providers",
            lambda: _symbol_phase(project_root, context, deadline),
        )
        report["symbol_count"] = symbols_result["count"]

        def build_phase() -> dict[str, Any]:
            process_result = _run_process(
                [
                    sys.executable,
                    "-m",
                    "flow_cad.release.subprocess_runner",
                    "build-active",
                    "--project-root",
                    str(project_root),
                ],
                project_root=project_root,
                context=context,
                deadline=deadline,
                phase="build_active",
                progress_handler=lambda message: _report_build_progress(
                    context,
                    message,
                    start=0.16,
                    span=0.44,
                ),
            )
            complete = _last_event(process_result.messages, "build_complete")
            raw_results = complete.get("results")
            if not isinstance(raw_results, list):
                raise ReleaseGateError("build subprocess returned no part results")
            build_results.extend(
                result for result in raw_results if isinstance(result, dict)
            )
            if len(build_results) != report["active_part_count"]:
                raise ReleaseGateError("not every active part produced a build result")
            return {
                "part_count": len(build_results),
                "elapsed_seconds": process_result.elapsed_seconds,
                "viewer_revisions": [result.get("viewer_revision") for result in build_results],
            }

        run_phase("build_active", 0.16, "Building all active parts", build_phase)

        consistency = run_phase(
            "viewer_index",
            0.62,
            "Verifying fresh viewer and index identities",
            lambda: _verify_viewer_index(project_root, manifest),
        )
        artifacts.extend(consistency["artifacts"])
        report["viewer_revision"] = consistency["revision"]

        artifact_manifest = run_phase(
            "artifact_manifest",
            0.69,
            "Writing complete fresh artifact manifest",
            lambda: _write_artifact_manifest(project_root, artifacts),
        )
        report["artifact_manifest_path"] = artifact_manifest["path"]
        report["artifacts"] = artifacts

        hook_context_path = _write_hook_context(
            project_root,
            manifest,
            artifacts,
            artifact_manifest["path"],
        )
        hook_results: list[dict[str, Any]] = []
        hook_start = 0.74
        hook_span = 0.14
        hook_count = max(1, len(manifest.release_hooks))
        for index, hook in enumerate(manifest.release_hooks):
            hook_progress = hook_start + hook_span * index / hook_count
            result = run_phase(
                f"hook:{hook.kind.value}:{hook.key}",
                hook_progress,
                f"Running {hook.kind.value} hook {hook.key}",
                lambda hook=hook: _run_hook_phase(
                    project_root,
                    hook.provider,
                    hook_context_path,
                    hook.timeout_seconds,
                    context,
                    deadline,
                    f"hook:{hook.kind.value}:{hook.key}",
                ),
            )
            hook_results.append(
                {"key": hook.key, "kind": hook.kind.value, "result": result}
            )
        registered_kinds = {hook.kind for hook in manifest.release_hooks}
        for kind in (ReleaseHookKind.INTERFERENCE, ReleaseHookKind.PRINT_MANIFEST):
            if kind not in registered_kinds:
                phases.append(
                    {
                        "key": f"hook:{kind.value}",
                        "status": "skipped",
                        "elapsed_seconds": 0.0,
                        "details": {"reason": "not_registered"},
                    }
                )
        report["hooks"] = hook_results

        tests_result = run_phase(
            "project_tests",
            0.89,
            "Running project tests",
            lambda: _run_project_tests(project_root, context, deadline),
        )
        report["project_tests"] = tests_result

        def benchmark_phase() -> dict[str, Any]:
            slow_parts = [
                {
                    "part_key": result.get("part_key"),
                    "elapsed_seconds": float(result.get("elapsed_ms", 0.0)) / 1000.0,
                }
                for result in build_results
                if float(result.get("elapsed_ms", 0.0)) / 1000.0
                > SCOPED_PART_HARD_SECONDS
            ]
            if slow_parts:
                raise ReleaseGateError(
                    f"{len(slow_parts)} scoped part build(s) exceeded "
                    f"{SCOPED_PART_HARD_SECONDS:.0f}s"
                )
            return {
                "scoped_part_hard_seconds": SCOPED_PART_HARD_SECONDS,
                "slow_parts": slow_parts,
                "elapsed_seconds_so_far": time.monotonic() - started,
            }

        report["benchmarks"] = run_phase(
            "benchmarks",
            0.94,
            "Checking release performance thresholds",
            benchmark_phase,
        )

        report["git"] = run_phase(
            "git_clean",
            0.97,
            "Verifying clean project Git status",
            lambda: _verify_clean_git(project_root, context, deadline),
        )
        _check_deadline(context, deadline, "complete")
        elapsed = time.monotonic() - started
        report.update(
            {
                "status": "passed",
                "elapsed_seconds": elapsed,
                "over_target": elapsed > TARGET_SECONDS,
                "completed_at": datetime.now(UTC).isoformat(),
            }
        )
        _write_json_atomic(report_path, report)
        context.report("report", 0.995, f"Wrote release report {REPORT_RELATIVE_PATH}")
        return {
            "status": "passed",
            "project_id": manifest.project_id,
            "elapsed_seconds": elapsed,
            "over_target": elapsed > TARGET_SECONDS,
            "viewer_revision": report["viewer_revision"],
            "artifact_count": len(artifacts),
            "artifact_manifest_path": ARTIFACT_MANIFEST_RELATIVE_PATH.as_posix(),
            "report_path": REPORT_RELATIVE_PATH.as_posix(),
        }
    except BaseException as error:
        elapsed = time.monotonic() - started
        report.update(
            {
                "status": "cancelled" if context.cancellation_requested else "failed",
                "failed_phase": current_phase,
                "error": f"{type(error).__name__}: {error}",
                "elapsed_seconds": elapsed,
                "over_target": elapsed > TARGET_SECONDS,
                "completed_at": datetime.now(UTC).isoformat(),
            }
        )
        _write_json_atomic(report_path, report)
        if isinstance(error, JobCancelled):
            raise
        raise ReleaseGateError(
            f"release phase {current_phase!r} failed: {error}; "
            f"report={REPORT_RELATIVE_PATH.as_posix()}"
        ) from error


def _symbol_phase(
    project_root: Path,
    context: JobContext,
    deadline: float,
) -> dict[str, Any]:
    result = _run_process(
        [
            sys.executable,
            "-m",
            "flow_cad.release.subprocess_runner",
            "symbols",
            "--project-root",
            str(project_root),
        ],
        project_root=project_root,
        context=context,
        deadline=deadline,
        phase="symbols",
        phase_timeout=30.0,
    )
    payload = _last_event(result.messages, "symbols")
    return {"count": int(payload["count"]), "elapsed_seconds": result.elapsed_seconds}


def _report_build_progress(
    context: JobContext,
    message: dict[str, Any],
    *,
    start: float,
    span: float,
) -> None:
    if message.get("event") != "progress":
        return
    part_count = max(1, int(message.get("part_count", 1)))
    part_index = int(message.get("part_index", 0))
    part_progress = float(message.get("progress", 0.0))
    progress = start + span * (part_index + part_progress) / part_count
    context.report(
        f"build:{message.get('part_key')}:{message.get('phase')}",
        min(start + span, progress),
        str(message.get("message") or "Building active part"),
    )


def _verify_viewer_index(
    project_root: Path,
    manifest: ProjectManifest,
) -> dict[str, Any]:
    active = {str(part.uuid): part for part in manifest.parts if part.status is PartStatus.ACTIVE}
    expected = {
        (str(part.uuid), artifact.kind, artifact.path): part
        for part in active.values()
        for artifact in part.artifacts
        if artifact.kind in {"step", "stl"}
    }
    with closing(connect_readonly(database_path(project_root))) as connection:
        project = connection.execute("SELECT revision FROM projects LIMIT 1").fetchone()
        rows = connection.execute(
            """
            SELECT a.part_uuid, p.key AS part_key, a.kind, a.relative_path,
                   a.sha256, a.byte_count, a.state
            FROM artifacts a JOIN parts p ON p.uuid = a.part_uuid
            WHERE p.status = 'active' AND a.kind IN ('step', 'stl')
            ORDER BY p.key, a.kind
            """
        ).fetchall()
    if project is None:
        raise ReleaseGateError("registry index contains no project revision")
    if len(rows) != len(expected):
        raise ReleaseGateError("active artifact count does not match the strict manifest")
    identities: list[dict[str, Any]] = []
    for row in rows:
        identity = (str(row["part_uuid"]), str(row["kind"]), str(row["relative_path"]))
        if identity not in expected:
            raise ReleaseGateError(f"unexpected active artifact row: {identity}")
        if row["state"] != "indexed" or row["sha256"] is None or row["byte_count"] is None:
            raise ReleaseGateError(f"active artifact is not freshly indexed: {identity}")
        path = (project_root / str(row["relative_path"])).resolve()
        try:
            path.relative_to(project_root)
        except ValueError as exc:
            raise ReleaseGateError(f"artifact escapes project root: {row['relative_path']}") from exc
        digest, byte_count = _hash_file(path)
        if digest != row["sha256"] or byte_count != row["byte_count"]:
            raise ReleaseGateError(f"viewer/index identity mismatch: {row['relative_path']}")
        identities.append(
            {
                "part_uuid": str(row["part_uuid"]),
                "part_key": str(row["part_key"]),
                "kind": str(row["kind"]),
                "path": str(row["relative_path"]),
                "sha256": digest,
                "byte_count": byte_count,
            }
        )
    inventory = InventoryService(project_root).inventory(include_retired=False)
    inventory_hashes = {
        (str(part["uuid"]), str(artifact["kind"])): artifact["sha256"]
        for part in inventory["parts"]
        for artifact in part["artifacts"]
        if artifact["kind"] in {"step", "stl"}
    }
    for identity in identities:
        if inventory_hashes[(identity["part_uuid"], identity["kind"])] != identity["sha256"]:
            raise ReleaseGateError(f"viewer inventory hash mismatch: {identity['path']}")
    return {
        "revision": int(project["revision"]),
        "artifact_count": len(identities),
        "artifacts": identities,
    }


def _write_artifact_manifest(
    project_root: Path,
    artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    path = project_root / ARTIFACT_MANIFEST_RELATIVE_PATH
    text = "".join(
        f"{artifact['sha256']}  {artifact['path']}\n"
        for artifact in sorted(artifacts, key=lambda item: str(item["path"]))
    )
    _write_text_atomic(path, text)
    return {
        "path": ARTIFACT_MANIFEST_RELATIVE_PATH.as_posix(),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "artifact_count": len(artifacts),
    }


def _write_hook_context(
    project_root: Path,
    manifest: ProjectManifest,
    artifacts: list[dict[str, Any]],
    artifact_manifest_path: str,
) -> Path:
    path = project_root / ".flow/release/hook-context.json"
    _write_json_atomic(
        path,
        {
            "project_id": manifest.project_id,
            "project_root": str(project_root),
            "artifact_manifest_path": artifact_manifest_path,
            "artifacts": artifacts,
        },
    )
    return path


def _run_hook_phase(
    project_root: Path,
    provider: str,
    context_path: Path,
    timeout_seconds: float,
    context: JobContext,
    deadline: float,
    phase: str,
) -> dict[str, Any]:
    process = _run_process(
        [
            sys.executable,
            "-m",
            "flow_cad.release.subprocess_runner",
            "hook",
            "--project-root",
            str(project_root),
            "--provider",
            provider,
            "--context",
            str(context_path),
        ],
        project_root=project_root,
        context=context,
        deadline=deadline,
        phase=phase,
        phase_timeout=timeout_seconds,
    )
    result = _last_event(process.messages, "hook_result").get("result")
    if not isinstance(result, dict):
        raise ReleaseGateError(f"{phase} returned no structured hook result")
    if not result.get("ok"):
        raise ReleaseGateError(f"{phase} failed: {result.get('summary', 'hook failed')}")
    return result


def _run_project_tests(
    project_root: Path,
    context: JobContext,
    deadline: float,
) -> dict[str, Any]:
    tests_root = project_root / "tests"
    test_files = tuple(tests_root.rglob("test_*.py")) if tests_root.is_dir() else ()
    if not test_files:
        raise ReleaseGateError("release gate requires project tests")
    result = _run_process(
        [sys.executable, "-m", "pytest", "-q", str(tests_root)],
        project_root=project_root,
        context=context,
        deadline=deadline,
        phase="project_tests",
    )
    return {
        "test_file_count": len(test_files),
        "elapsed_seconds": result.elapsed_seconds,
        "output_tail": list(result.output[-10:]),
    }


def _verify_clean_git(
    project_root: Path,
    context: JobContext,
    deadline: float,
) -> dict[str, Any]:
    result = _run_process(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        project_root=project_root,
        context=context,
        deadline=deadline,
        phase="git_clean",
        phase_timeout=10.0,
    )
    dirty = [line for line in result.output if line.strip()]
    if dirty:
        raise ReleaseGateError(f"project Git worktree is dirty: {dirty[0]}")
    return {"clean": True, "elapsed_seconds": result.elapsed_seconds}


def _run_process(
    command: list[str],
    *,
    project_root: Path,
    context: JobContext,
    deadline: float,
    phase: str,
    phase_timeout: float | None = None,
    progress_handler: Callable[[dict[str, Any]], None] | None = None,
) -> ProcessResult:
    started = time.monotonic()
    phase_deadline = deadline
    if phase_timeout is not None:
        phase_deadline = min(phase_deadline, started + phase_timeout)
    environment = dict(os.environ)
    source_root = Path(__file__).resolve().parents[2]
    existing_python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        os.fspath(source_root)
        if not existing_python_path
        else os.pathsep.join((os.fspath(source_root), existing_python_path))
    )
    environment["PYTHONUNBUFFERED"] = "1"
    process = subprocess.Popen(
        command,
        cwd=project_root,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=os.name != "nt",
    )
    assert process.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    messages: list[dict[str, Any]] = []
    output: list[str] = []
    try:
        while True:
            if context.cancellation_requested:
                _terminate_process(process)
                context.checkpoint()
            if time.monotonic() >= phase_deadline:
                _terminate_process(process)
                limit = phase_timeout if phase_timeout is not None else HARD_TIMEOUT_SECONDS
                raise ReleaseGateTimeoutError(
                    f"phase {phase!r} exceeded {limit:.1f}s timeout"
                )
            for key, _ in selector.select(timeout=0.1):
                line = key.fileobj.readline()
                if line:
                    _collect_process_line(line, messages, output, progress_handler)
            if process.poll() is not None:
                for line in process.stdout:
                    _collect_process_line(line, messages, output, progress_handler)
                break
        if process.returncode != 0:
            tail = " | ".join(output[-5:]) or f"exit code {process.returncode}"
            raise ReleaseGateError(f"phase {phase!r} subprocess failed: {tail}")
    finally:
        selector.close()
        if process.poll() is None:
            _terminate_process(process)
    return ProcessResult(
        messages=tuple(messages),
        output=tuple(output),
        elapsed_seconds=time.monotonic() - started,
    )


def _collect_process_line(
    line: str,
    messages: list[dict[str, Any]],
    output: list[str],
    progress_handler: Callable[[dict[str, Any]], None] | None,
) -> None:
    text = line.rstrip("\r\n")
    if not text:
        return
    output.append(text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return
    if isinstance(payload, dict):
        messages.append(payload)
        if progress_handler is not None:
            progress_handler(payload)


def _last_event(messages: tuple[dict[str, Any], ...], event: str) -> dict[str, Any]:
    for message in reversed(messages):
        if message.get("event") == event:
            return message
    raise ReleaseGateError(f"subprocess did not emit required {event!r} event")


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            process.terminate()
        else:
            os.killpg(process.pid, 15)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2.0)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, 9)
        except ProcessLookupError:
            return
        process.wait(timeout=2.0)


def _check_deadline(context: JobContext, deadline: float, phase: str) -> None:
    context.checkpoint()
    if time.monotonic() >= deadline:
        raise ReleaseGateTimeoutError(
            f"release gate exceeded {HARD_TIMEOUT_SECONDS:.0f}s during {phase}"
        )


def _validate_project_reference(reference: str, python_package: str, label: str) -> None:
    module, separator, symbol = reference.partition(":")
    if not separator or not module or not symbol:
        raise ReleaseGateError(f"{label} must be an importable module:symbol reference")
    if module != python_package and not module.startswith(f"{python_package}."):
        raise ReleaseGateError(
            f"{label} must belong to project package {python_package!r}: {reference}"
        )


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            byte_count += len(chunk)
    return digest.hexdigest(), byte_count


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    _write_text_atomic(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
