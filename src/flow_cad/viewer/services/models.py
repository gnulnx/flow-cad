"""Content-addressed delivery of STEP authority and STL display artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import re
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from flow_cad.registry.db import connect_readonly, database_path


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class InvalidArtifactDigestError(ValueError):
    """The requested content identity is not a canonical SHA-256 digest."""


class ModelNotFoundError(LookupError):
    """No indexed STEP/STL artifact has the requested content identity."""


class ArtifactChangedError(RuntimeError):
    """The artifact bytes no longer match the registry's content identity."""


class UnsafeArtifactPathError(RuntimeError):
    """An indexed artifact path escapes its project root."""


@dataclass(frozen=True, slots=True)
class ResolvedModel:
    path: Path
    sha256: str
    byte_count: int
    kind: str
    media_type: str
    geometry_authority: str


class ContentAddressedModelService:
    """Resolve and verify model bytes through a bounded hashing queue.

    The service never imports or executes a project generator or CAD kernel.
    Hashing is done at most once for an unchanged filesystem identity and is
    bounded so simultaneous cold requests cannot create an unbounded I/O burst.
    """

    def __init__(self, project_root: Path, *, max_concurrent_verifications: int = 2):
        if max_concurrent_verifications < 1:
            raise ValueError("max_concurrent_verifications must be at least 1")
        self.project_root = project_root.resolve()
        self.index_path = database_path(self.project_root)
        self._verification_slots = asyncio.Semaphore(max_concurrent_verifications)
        self._verified: set[tuple[object, ...]] = set()

    async def resolve(self, artifact_sha256: str) -> ResolvedModel:
        digest = artifact_sha256.lower()
        if _SHA256_RE.fullmatch(digest) is None:
            raise InvalidArtifactDigestError(
                "artifact identity must contain 64 lowercase hexadecimal characters"
            )
        candidates = self._candidates(digest)
        if not candidates:
            raise ModelNotFoundError(f"content-addressed model artifact not found: {digest}")

        failures: list[Exception] = []
        for kind, relative_path, expected_byte_count in candidates:
            try:
                path = self._safe_path(relative_path)
                async with self._verification_slots:
                    byte_count = await asyncio.to_thread(
                        self._verify_bytes,
                        path,
                        digest,
                        expected_byte_count,
                    )
                return ResolvedModel(
                    path=path,
                    sha256=digest,
                    byte_count=byte_count,
                    kind=kind,
                    media_type="model/step" if kind == "step" else "model/stl",
                    geometry_authority="step_kernel" if kind == "step" else "mesh",
                )
            except (FileNotFoundError, ArtifactChangedError, UnsafeArtifactPathError) as exc:
                failures.append(exc)
        if failures:
            raise failures[0]
        raise ModelNotFoundError(f"content-addressed model artifact not found: {digest}")

    def _candidates(self, digest: str) -> tuple[tuple[str, str, int | None], ...]:
        with closing(connect_readonly(self.index_path)) as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT kind, relative_path, byte_count
                FROM artifacts
                WHERE kind IN ('step', 'stl') AND sha256 = ? AND state = 'indexed'
                ORDER BY CASE kind WHEN 'step' THEN 0 ELSE 1 END, relative_path
                """,
                (digest,),
            ).fetchall()
        return tuple(
            (
                str(row["kind"]),
                str(row["relative_path"]),
                int(row["byte_count"]) if row["byte_count"] is not None else None,
            )
            for row in rows
        )

    def _safe_path(self, relative_path: str) -> Path:
        candidate = (self.project_root / relative_path).resolve()
        try:
            candidate.relative_to(self.project_root)
        except ValueError as exc:
            raise UnsafeArtifactPathError(
                f"indexed artifact path escapes the project root: {relative_path}"
            ) from exc
        return candidate

    def _verify_bytes(
        self,
        path: Path,
        expected_digest: str,
        expected_byte_count: int | None,
    ) -> int:
        before = path.stat()
        if expected_byte_count is not None and before.st_size != expected_byte_count:
            raise ArtifactChangedError(
                f"artifact byte count changed for {path.name}: "
                f"expected {expected_byte_count}, found {before.st_size}"
            )
        identity = _filesystem_identity(path, before, expected_digest)
        if identity not in self._verified:
            actual_digest = _sha256_file(path)
            after = path.stat()
            if _filesystem_identity(path, after, expected_digest) != identity:
                raise ArtifactChangedError(f"artifact changed while verifying {path.name}")
            if actual_digest != expected_digest:
                raise ArtifactChangedError(
                    f"artifact SHA-256 changed for {path.name}: "
                    f"expected {expected_digest}, found {actual_digest}"
                )
            self._verified.add(identity)
        return before.st_size


def _filesystem_identity(path: Path, stat_result, expected_digest: str) -> tuple[object, ...]:
    return (
        path,
        expected_digest,
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
