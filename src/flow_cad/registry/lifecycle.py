"""Atomic manifest-first part lifecycle operations."""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from flow_cad.sdk import ManifestPart, PartStatus, ProjectManifest, dump_manifest, loads_manifest

from .sync import PROJECT_MANIFEST, SyncResult, sync_project


class LifecycleError(RuntimeError):
    """Raised when a lifecycle transaction cannot complete or roll back."""


@dataclass(frozen=True, slots=True)
class LifecycleResult:
    operation: str
    part_uuid: str
    old_key: str
    new_key: str
    status: str
    revision: int
    changed: bool
    elapsed_ms: float


def rename_part(project_root: Path, key_or_alias: str, new_key: str) -> LifecycleResult:
    started = time.perf_counter()

    def update(manifest: ProjectManifest) -> tuple[ProjectManifest, ManifestPart, ManifestPart, bool]:
        index, current = _find_part(manifest, key_or_alias)
        if current.key == new_key:
            return manifest, current, current, False
        _require_available_name(manifest, new_key, current.uuid)
        aliases = tuple(sorted(({*current.aliases, current.key}) - {new_key}))
        updated = replace(current, key=new_key, aliases=aliases)
        parts = list(manifest.parts)
        parts[index] = updated
        return replace(manifest, parts=tuple(parts)), current, updated, True

    return _transact(project_root, "rename", update, started)


def retire_part(project_root: Path, key_or_alias: str) -> LifecycleResult:
    started = time.perf_counter()

    def update(manifest: ProjectManifest) -> tuple[ProjectManifest, ManifestPart, ManifestPart, bool]:
        index, current = _find_part(manifest, key_or_alias)
        if current.status is PartStatus.RETIRED:
            return manifest, current, current, False
        updated = replace(current, status=PartStatus.RETIRED)
        parts = list(manifest.parts)
        parts[index] = updated
        return replace(manifest, parts=tuple(parts)), current, updated, True

    return _transact(project_root, "retire", update, started)


def _transact(
    project_root: Path,
    operation: str,
    update: Callable[
        [ProjectManifest], tuple[ProjectManifest, ManifestPart, ManifestPart, bool]
    ],
    started: float,
) -> LifecycleResult:
    root = project_root.resolve()
    manifest_path = root / PROJECT_MANIFEST
    original_bytes = manifest_path.read_bytes()
    original = loads_manifest(original_bytes.decode("utf-8"), source=manifest_path)
    updated_manifest, before, after, changed = update(original)
    if changed:
        updated_text = dump_manifest(updated_manifest)
        loads_manifest(updated_text, source=manifest_path)
        _write_atomic(manifest_path, updated_text.encode("utf-8"))
        try:
            sync_result = sync_project(root, force=True)
        except BaseException as error:
            _write_atomic(manifest_path, original_bytes)
            rollback_error: BaseException | None = None
            try:
                sync_project(root, force=True)
            except BaseException as restore_error:
                rollback_error = restore_error
            if rollback_error is not None:
                raise LifecycleError(
                    f"{operation} failed; manifest was restored but index restoration failed: "
                    f"{rollback_error}"
                ) from error
            raise LifecycleError(
                f"{operation} failed and manifest/index were restored: {error}"
            ) from error
    else:
        sync_result = sync_project(root)
    return _lifecycle_result(operation, before, after, changed, sync_result, started)


def _find_part(manifest: ProjectManifest, key_or_alias: str) -> tuple[int, ManifestPart]:
    for index, part in enumerate(manifest.parts):
        if part.key == key_or_alias or key_or_alias in part.aliases:
            return index, part
    raise LifecycleError(f"part not found: {key_or_alias}")


def _require_available_name(manifest: ProjectManifest, name: str, current_uuid: object) -> None:
    if not name or any(character.isspace() for character in name):
        raise LifecycleError("part key must be non-empty and contain no whitespace")
    for part in manifest.parts:
        if part.uuid != current_uuid and (part.key == name or name in part.aliases):
            raise LifecycleError(f"part key or alias already exists: {name}")


def _write_atomic(path: Path, content: bytes) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _lifecycle_result(
    operation: str,
    before: ManifestPart,
    after: ManifestPart,
    changed: bool,
    sync_result: SyncResult,
    started: float,
) -> LifecycleResult:
    return LifecycleResult(
        operation=operation,
        part_uuid=str(after.uuid),
        old_key=before.key,
        new_key=after.key,
        status=after.status.value,
        revision=sync_result.revision,
        changed=changed,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )
