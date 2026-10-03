"""Fast, recoverable removal of a registered part and its declared references."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from flow_cad.sdk import dump_manifest, loads_manifest

from .db import connect_writable, database_path
from .lifecycle import LifecycleError, _write_atomic
from .sync import PROJECT_MANIFEST, sync_project


class PartDeleteNotFound(LifecycleError):
    pass


def delete_part(project_root: Path, identity: str) -> dict:
    """Remove metadata and unshared generated exports; retain source and audit history.

    Files are moved, never unlinked. The pre-delete manifest and moved files live
    in .flow/trash/parts. Shared exports and immutable input assets are retained.
    No CAD imports, tessellation or full artifact rehash is needed.
    """
    started = time.perf_counter()
    root = project_root.resolve()
    manifest_path = root / PROJECT_MANIFEST
    original = manifest_path.read_bytes()
    manifest = loads_manifest(original.decode(), source=manifest_path)
    part = next((p for p in manifest.parts if identity in (str(p.uuid), p.key, *p.aliases)), None)
    if part is None:
        raise PartDeleteNotFound(f"part not found: {identity}")
    # A running publisher must not recreate a deleted export after this command.
    jobs = root / ".flow/jobs.sqlite3"
    if jobs.is_file():
        with closing(sqlite3.connect(f"file:{jobs}?mode=ro", uri=True)) as connection:
            if connection.execute(
                "SELECT 1 FROM jobs WHERE state IN ('queued', 'running') "
                "AND kind IN ('part-build', 'project-build', 'release-gate') LIMIT 1"
            ).fetchone():
                raise LifecycleError("Wait for the current CAD job to finish or cancel it before deleting a part.")
    sync_project(root)
    affected = tuple(a for a in manifest.assemblies if any(o.part_uuid == part.uuid for o in a.occurrences))
    affected_keys = {a.key for a in affected}
    updated = replace(
        manifest,
        parts=tuple(p for p in manifest.parts if p.uuid != part.uuid),
        assemblies=tuple(replace(a, occurrences=tuple(o for o in a.occurrences if o.part_uuid != part.uuid),
                                 artifacts=()) if a.key in affected_keys else a for a in manifest.assemblies),
    )
    encoded = dump_manifest(updated).encode()
    loads_manifest(encoded.decode(), source=manifest_path)
    retained = {artifact.path for owner in (*updated.parts, *updated.assemblies) for artifact in owner.artifacts}
    # An export may also be an explicitly pinned dependency of a surviving part.
    with closing(connect_writable(database_path(root))) as connection:
        retained.update(row[0] for row in connection.execute(
            "SELECT dependency_path FROM artifact_dependencies WHERE part_uuid != ?", (str(part.uuid),)))
    retained_paths = {(root / path).resolve() for path in retained}
    candidates = {a.path for owner in (part, *affected) for a in owner.artifacts}
    paths = []
    for relative in sorted(candidates):
        path = root / relative
        resolved = path.resolve()
        if (relative not in retained and resolved not in retained_paths
                and resolved.is_relative_to(root / "exports") and path.is_file() and not path.is_symlink()):
            paths.append(path)
    preview = root / ".flow/workbench/preview-placement.json"
    if preview.is_file():
        placement = json.loads(preview.read_text())
        if str(part.uuid) in (placement.get("preview_part_uuid"), placement.get("target_part_uuid")):
            paths.append(preview)
    trash = root / ".flow/trash/parts" / f"{part.uuid}-{uuid4().hex}"
    trash.mkdir(parents=True)
    (trash / PROJECT_MANIFEST).write_bytes(original)
    moved: list[tuple[Path, Path]] = []
    try:
        with closing(connect_writable(database_path(root))) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                if manifest_path.read_bytes() != original:
                    raise LifecycleError("Project changed during deletion; retry using the refreshed parts list.")
                for path in paths:
                    destination = trash / "files" / path.relative_to(root)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    path.rename(destination)
                    moved.append((path, destination))
                connection.execute("DELETE FROM assembly_occurrences WHERE part_uuid = ?", (str(part.uuid),))
                connection.execute("DELETE FROM build_jobs WHERE part_uuid = ?", (str(part.uuid),))
                connection.execute("DELETE FROM parts WHERE uuid = ?", (str(part.uuid),))
                for key in affected_keys:
                    connection.execute("DELETE FROM assembly_artifacts WHERE assembly_key = ?", (key,))
                connection.execute("UPDATE projects SET manifest_sha256 = ?, revision = revision + 1",
                                   (hashlib.sha256(encoded).hexdigest(),))
                revision = connection.execute("SELECT revision FROM projects LIMIT 1").fetchone()[0]
                _write_atomic(manifest_path, encoded)
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
    except BaseException:
        for path, destination in reversed(moved):
            destination.rename(path)
        if manifest_path.read_bytes() == encoded:
            _write_atomic(manifest_path, original)
        raise
    return {"ok": True, "part_uuid": str(part.uuid), "key": part.key, "revision": revision,
            "removed_occurrences": sum(o.part_uuid == part.uuid for a in affected for o in a.occurrences),
            "removed_files": [str(path.relative_to(root)) for path, _ in moved],
            "recovery_path": str(trash.relative_to(root)),
            "elapsed_ms": (time.perf_counter() - started) * 1000}
