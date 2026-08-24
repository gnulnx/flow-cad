"""Killable child-process phases for strict-manifest release gates."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import signal
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from flow_cad.build import plan_scoped_part_build
from flow_cad.build.worker import run_scoped_part_build
from flow_cad.sdk import (
    PartStatus,
    ReleaseArtifactIdentity,
    ReleaseHookContext,
    ReleaseHookResult,
    load_manifest,
)


def _terminate_from_signal(_signal_number: int, _frame: object) -> None:
    raise SystemExit(143)


class _StandaloneBuildContext:
    def __init__(self, part_key: str, part_index: int, part_count: int) -> None:
        self.job_id = f"release-{part_index}-{part_key}"
        self.part_key = part_key
        self.part_index = part_index
        self.part_count = part_count

    @property
    def cancellation_requested(self) -> bool:
        return False

    def checkpoint(self) -> None:
        return None

    def report(self, phase: str, progress: float, message: str | None = None) -> None:
        _emit(
            {
                "event": "progress",
                "part_key": self.part_key,
                "part_index": self.part_index,
                "part_count": self.part_count,
                "phase": phase,
                "progress": progress,
                "message": message,
            }
        )


def main(argv: list[str] | None = None) -> int:
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _terminate_from_signal)
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("symbols", "build-active"):
        command = subparsers.add_parser(name)
        command.add_argument("--project-root", required=True, type=Path)
    hook = subparsers.add_parser("hook")
    hook.add_argument("--project-root", required=True, type=Path)
    hook.add_argument("--provider", required=True)
    hook.add_argument("--context", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "symbols":
            return _validate_symbols(args.project_root)
        if args.command == "build-active":
            return _build_active(args.project_root)
        return _run_hook(args.project_root, args.provider, args.context)
    except BaseException as error:
        _emit(
            {
                "event": "error",
                "error": f"{type(error).__name__}: {error}",
            }
        )
        return 1


def _validate_symbols(project_root: Path) -> int:
    root = project_root.resolve()
    manifest = load_manifest(root / "flowcad.project.yaml")
    references = []
    if manifest.parameter_provider is not None:
        references.append(("parameter_provider", manifest.parameter_provider))
    references.extend(
        (f"part:{part.key}", part.generator)
        for part in manifest.parts
        if part.status is PartStatus.ACTIVE
    )
    references.extend((f"hook:{hook.key}", hook.provider) for hook in manifest.release_hooks)
    imported = []
    with _project_import_path(root):
        for label, reference in references:
            value = _import_symbol(reference)
            if not callable(value):
                raise TypeError(f"{label} is not callable: {reference}")
            imported.append({"label": label, "reference": reference})
    _emit({"event": "symbols", "symbols": imported, "count": len(imported)})
    return 0


def _build_active(project_root: Path) -> int:
    root = project_root.resolve()
    manifest = load_manifest(root / "flowcad.project.yaml")
    active = tuple(part for part in manifest.parts if part.status is PartStatus.ACTIVE)
    if not active:
        raise RuntimeError("release gate requires at least one active part")
    results = []
    for index, part in enumerate(active):
        plan = plan_scoped_part_build(root, manifest, part)
        context = _StandaloneBuildContext(part.key, index, len(active))
        result = run_scoped_part_build(plan, context)
        results.append(result)
        _emit(
            {
                "event": "part_complete",
                "part_key": part.key,
                "part_index": index,
                "part_count": len(active),
                "result": result,
            }
        )
    _emit({"event": "build_complete", "results": results, "count": len(results)})
    return 0


def _run_hook(project_root: Path, provider: str, context_path: Path) -> int:
    root = project_root.resolve()
    payload = json.loads(context_path.read_text(encoding="utf-8"))
    context = ReleaseHookContext(
        project_id=str(payload["project_id"]),
        project_root=str(payload["project_root"]),
        artifact_manifest_path=str(payload["artifact_manifest_path"]),
        artifacts=tuple(
            ReleaseArtifactIdentity(
                part_uuid=UUID(str(artifact["part_uuid"])),
                part_key=str(artifact["part_key"]),
                kind=str(artifact["kind"]),
                path=str(artifact["path"]),
                sha256=str(artifact["sha256"]),
                byte_count=int(artifact["byte_count"]),
            )
            for artifact in payload["artifacts"]
        ),
    )
    with _project_import_path(root):
        hook = _import_symbol(provider)
        if not callable(hook):
            raise TypeError(f"release hook is not callable: {provider}")
        raw_result = hook(context)
    result = _coerce_hook_result(raw_result)
    response = {
        "ok": result.ok,
        "summary": result.summary,
        "details": dict(result.details) if result.details is not None else {},
    }
    json.dumps(response)
    _emit({"event": "hook_result", "result": response})
    return 0


def _coerce_hook_result(value: Any) -> ReleaseHookResult:
    if isinstance(value, ReleaseHookResult):
        return value
    if isinstance(value, bool):
        return ReleaseHookResult(ok=value, summary="passed" if value else "failed")
    if isinstance(value, Mapping):
        if "ok" not in value:
            raise TypeError("release hook mapping result must contain 'ok'")
        return ReleaseHookResult(
            ok=bool(value["ok"]),
            summary=str(value.get("summary", "passed" if value["ok"] else "failed")),
            details=value.get("details") if isinstance(value.get("details"), Mapping) else None,
        )
    raise TypeError(
        "release hook must return ReleaseHookResult, a mapping with 'ok', or bool"
    )


class _project_import_path:
    def __init__(self, project_root: Path) -> None:
        self.project_root = os.fspath(project_root)

    def __enter__(self) -> None:
        sys.path.insert(0, self.project_root)
        importlib.invalidate_caches()

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        try:
            sys.path.remove(self.project_root)
        except ValueError:
            pass


def _import_symbol(reference: str) -> Any:
    module_name, separator, symbol_path = reference.partition(":")
    if separator != ":" or not module_name or not symbol_path:
        raise ValueError(f"expected module:symbol reference: {reference}")
    value: Any = importlib.import_module(module_name)
    for segment in symbol_path.split("."):
        value = getattr(value, segment)
    return value


def _emit(payload: Mapping[str, object]) -> None:
    print(json.dumps(dict(payload), sort_keys=True, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
