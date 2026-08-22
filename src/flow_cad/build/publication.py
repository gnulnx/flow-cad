"""Publish completed scoped-build identities into the disposable runtime index."""

from __future__ import annotations

import re
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping
from uuid import UUID

from flow_cad.registry.db import connect_writable, database_path


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class BuildPublication:
    revision: int
    artifact_count: int
    changed: bool


class BuildPublicationError(RuntimeError):
    """Fresh files could not be represented by the current registry index."""


def publish_part_build(
    project_root: Path,
    *,
    part_uuid: UUID,
    artifacts: Iterable[Mapping[str, object]],
) -> BuildPublication:
    """Atomically index fresh hashes and advance the viewer-facing revision."""

    root = project_root.resolve()
    rows = tuple(_validated_artifact(root, artifact) for artifact in artifacts)
    if not rows:
        raise BuildPublicationError("completed build contains no artifacts")
    index_path = database_path(root)
    if not index_path.is_file():
        raise BuildPublicationError(f"registry index not found: {index_path}; run `flow sync`")

    with closing(connect_writable(index_path)) as connection:
        connection.execute("BEGIN IMMEDIATE")
        project = connection.execute("SELECT revision FROM projects LIMIT 1").fetchone()
        if project is None:
            raise BuildPublicationError("registry index contains no project row")
        part = connection.execute(
            "SELECT 1 FROM parts WHERE uuid = ?",
            (str(part_uuid),),
        ).fetchone()
        if part is None:
            raise BuildPublicationError(f"part is absent from registry index: {part_uuid}")
        changed = False
        for kind, relative_path, digest, byte_count in rows:
            current = connection.execute(
                """
                SELECT sha256, byte_count, state
                FROM artifacts
                WHERE part_uuid = ? AND kind = ? AND relative_path = ?
                """,
                (str(part_uuid), kind, relative_path),
            ).fetchone()
            if current is None:
                raise BuildPublicationError(
                    f"artifact is absent from registry index: {kind} {relative_path}"
                )
            artifact_changed = (
                current["sha256"] != digest
                or current["byte_count"] != byte_count
                or current["state"] != "indexed"
            )
            if not artifact_changed:
                continue
            connection.execute(
                """
                UPDATE artifacts
                SET sha256 = ?, byte_count = ?, state = 'indexed'
                WHERE part_uuid = ? AND kind = ? AND relative_path = ?
                """,
                (digest, byte_count, str(part_uuid), kind, relative_path),
            )
            changed = True
        if changed:
            connection.execute("UPDATE projects SET revision = revision + 1")
        revision = int(
            connection.execute("SELECT revision FROM projects LIMIT 1").fetchone()[0]
        )
        connection.commit()
    return BuildPublication(
        revision=revision,
        artifact_count=len(rows),
        changed=changed,
    )


def _validated_artifact(
    project_root: Path,
    artifact: Mapping[str, object],
) -> tuple[str, str, str, int]:
    kind = artifact.get("kind")
    relative_path = artifact.get("path")
    digest = artifact.get("sha256")
    byte_count = artifact.get("byte_count")
    if kind not in {"step", "stl"}:
        raise BuildPublicationError(f"unsupported built artifact kind: {kind!r}")
    if not isinstance(relative_path, str) or not relative_path:
        raise BuildPublicationError("built artifact path must be a non-empty string")
    if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
        raise BuildPublicationError(f"invalid built artifact SHA-256: {digest!r}")
    if type(byte_count) is not int or byte_count <= 0:
        raise BuildPublicationError(f"invalid built artifact byte count: {byte_count!r}")
    output = (project_root / relative_path).resolve()
    try:
        output.relative_to(project_root)
    except ValueError as exc:
        raise BuildPublicationError(
            f"built artifact resolves outside the project: {relative_path}"
        ) from exc
    try:
        actual_size = output.stat().st_size
    except OSError as exc:
        raise BuildPublicationError(f"built artifact is missing: {relative_path}") from exc
    if actual_size != byte_count:
        raise BuildPublicationError(
            f"built artifact byte count changed for {relative_path}: "
            f"expected {byte_count}, found {actual_size}"
        )
    return kind, relative_path, digest, byte_count
