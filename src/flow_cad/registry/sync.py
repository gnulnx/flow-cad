"""Rebuild the disposable registry index from manifest metadata only."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from flow_cad.sdk import ProjectManifest, load_manifest

from .db import RegistryError, connect_readonly, connect_writable, database_path, initialize_database


PROJECT_MANIFEST = "flowcad.project.yaml"


@dataclass(frozen=True, slots=True)
class SyncResult:
    project_root: Path
    database_path: Path
    project_id: str
    revision: int
    part_count: int
    occurrence_count: int
    changed: bool
    elapsed_ms: float


def find_manifest(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        manifest_path = candidate / PROJECT_MANIFEST
        if manifest_path.is_file():
            return manifest_path
    raise RegistryError(f"no {PROJECT_MANIFEST} found from {current}")


def sync_project(project_root: Path, *, force: bool = False) -> SyncResult:
    started = time.perf_counter()
    root = project_root.resolve()
    manifest_path = root / PROJECT_MANIFEST
    manifest_bytes = manifest_path.read_bytes()
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    manifest = load_manifest(manifest_path)
    destination = database_path(root)
    previous_digest, previous_revision = _existing_state(destination)
    if not force and previous_digest == manifest_digest:
        return _result(
            root,
            destination,
            manifest,
            revision=previous_revision,
            changed=False,
            started=started,
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    temporary_path.unlink()
    revision = previous_revision + 1
    try:
        with closing(connect_writable(temporary_path)) as connection:
            initialize_database(connection)
            _populate(
                connection,
                root=root,
                manifest_path=manifest_path,
                manifest_digest=manifest_digest,
                manifest=manifest,
                revision=revision,
            )
            connection.commit()
        os.replace(temporary_path, destination)
        _fsync_directory(destination.parent)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise

    return _result(
        root,
        destination,
        manifest,
        revision=revision,
        changed=True,
        started=started,
    )


def _existing_state(path: Path) -> tuple[str | None, int]:
    if not path.is_file():
        return None, 0
    try:
        with closing(connect_readonly(path)) as connection:
            row = connection.execute(
                "SELECT manifest_sha256, revision FROM projects LIMIT 1"
            ).fetchone()
    except (sqlite3.DatabaseError, RegistryError):
        return None, 0
    if row is None:
        return None, 0
    return str(row["manifest_sha256"]), int(row["revision"])


def _populate(
    connection: sqlite3.Connection,
    *,
    root: Path,
    manifest_path: Path,
    manifest_digest: str,
    manifest: ProjectManifest,
    revision: int,
) -> None:
    connection.execute(
        """
        INSERT INTO projects(
            project_id, python_package, manifest_schema_version,
            manifest_path, manifest_sha256, revision
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            manifest.project_id,
            manifest.python_package,
            manifest.schema_version,
            manifest_path.relative_to(root).as_posix(),
            manifest_digest,
            revision,
        ),
    )

    for part in manifest.parts:
        part_uuid = str(part.uuid)
        connection.execute(
            """
            INSERT INTO parts(
                uuid, project_id, key, generator, role, status, material,
                family, version, compatible_versions_json,
                shell_count, infill_density, mass_kg, center_of_mass_mm_json,
                inertia_kg_m2_json, mass_source, metadata_status, metadata_notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                part_uuid,
                manifest.project_id,
                part.key,
                part.generator,
                part.role.value,
                part.status.value,
                part.material,
                part.family,
                part.version,
                json.dumps(part.compatible_versions),
                part.print.shell_count if part.print is not None else None,
                part.print.infill_density if part.print is not None else None,
                part.mass_properties.mass_kg if part.mass_properties is not None else None,
                json.dumps(part.mass_properties.center_of_mass_mm)
                if part.mass_properties is not None
                and part.mass_properties.center_of_mass_mm is not None
                else None,
                json.dumps(part.mass_properties.inertia_kg_m2)
                if part.mass_properties is not None
                and part.mass_properties.inertia_kg_m2 is not None
                else None,
                part.mass_properties.source if part.mass_properties is not None else None,
                part.mass_properties.status if part.mass_properties is not None else None,
                part.mass_properties.notes if part.mass_properties is not None else None,
            ),
        )
        module, separator, symbol = part.generator.partition(":")
        connection.execute(
            """
            INSERT INTO source_definitions(part_uuid, generator, module, symbol)
            VALUES (?, ?, ?, ?)
            """,
            (part_uuid, part.generator, module, symbol if separator else ""),
        )
        connection.executemany(
            "INSERT INTO part_aliases(project_id, alias, part_uuid) VALUES (?, ?, ?)",
            ((manifest.project_id, alias, part_uuid) for alias in part.aliases),
        )
        for artifact in part.artifacts:
            artifact_path = root / artifact.path
            if not artifact_path.is_file():
                state = "missing"
            elif artifact.sha256 is None:
                state = "unverified"
            else:
                state = "indexed"
            connection.execute(
                """
                INSERT INTO artifacts(part_uuid, kind, relative_path, sha256, byte_count, state)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    part_uuid,
                    artifact.kind,
                    artifact.path,
                    artifact.sha256,
                    artifact.byte_count,
                    state,
                ),
            )

    for assembly in manifest.assemblies:
        for occurrence in assembly.occurrences:
            connection.execute(
                """
                INSERT INTO assembly_occurrences(
                    project_id, assembly_key, occurrence_id, part_uuid,
                    translation_x_mm, translation_y_mm, translation_z_mm,
                    rotation_x_deg, rotation_y_deg, rotation_z_deg
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manifest.project_id,
                    assembly.key,
                    occurrence.id,
                    str(occurrence.part_uuid),
                    *occurrence.translation_mm,
                    *occurrence.rotation_deg,
                ),
            )


def _result(
    root: Path,
    path: Path,
    manifest: ProjectManifest,
    *,
    revision: int,
    changed: bool,
    started: float,
) -> SyncResult:
    return SyncResult(
        project_root=root,
        database_path=path,
        project_id=manifest.project_id,
        revision=revision,
        part_count=len(manifest.parts),
        occurrence_count=sum(len(assembly.occurrences) for assembly in manifest.assemblies),
        changed=changed,
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
