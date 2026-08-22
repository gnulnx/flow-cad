"""Revision-bound exact-feature lookup, verification, and disposable cache."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from flow_cad.registry.db import connect_readonly, database_path

from .extractor import (
    EXACT_FEATURE_EXTRACTOR_VERSION,
    EXACT_FEATURE_SCHEMA_VERSION,
    extract_step_features,
)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_CACHE_DIRECTORY = "exact-features"
_JOB_KIND = "exact-feature-extraction"


class ExactFeatureServiceError(RuntimeError):
    """Base error for exact-feature authority operations."""


class PartNotFoundError(ExactFeatureServiceError):
    """The registry contains no part with the requested immutable UUID."""


class ExactGeometryUnavailableError(ExactFeatureServiceError):
    """The part has no indexed, content-addressed STEP authority."""


class InvalidArtifactRevisionError(ValueError):
    """The caller supplied a non-canonical artifact revision."""


class ArtifactRevisionMismatchError(ExactFeatureServiceError):
    """The caller's geometry revision is stale relative to the registry."""

    def __init__(self, requested_revision: str, current_revision: str) -> None:
        self.requested_revision = requested_revision
        self.current_revision = current_revision
        super().__init__(
            "artifact revision mismatch: "
            f"requested {requested_revision}, current {current_revision}"
        )


class ArtifactBytesChangedError(ExactFeatureServiceError):
    """The mutable path no longer contains the indexed STEP bytes."""


@dataclass(frozen=True, slots=True)
class ExactFeatureBinding:
    part_uuid: str
    artifact_revision: str
    relative_path: str
    byte_count: int | None


@dataclass(frozen=True, slots=True)
class ExactFeatureLookup:
    binding: ExactFeatureBinding
    payload: dict[str, Any] | None

    @property
    def ready(self) -> bool:
        return self.payload is not None


ProgressReporter = Callable[[str, float, str], None]
CancellationCheckpoint = Callable[[], None]


class ExactFeatureService:
    """Serve exact STEP facts without putting derived data beside artifacts."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.index_path = database_path(self.project_root)
        self.cache_root = (
            self.project_root
            / ".flow"
            / "cache"
            / _CACHE_DIRECTORY
            / f"v{EXACT_FEATURE_SCHEMA_VERSION}"
        )

    def lookup(self, part_uuid: str, artifact_revision: str) -> ExactFeatureLookup:
        binding = self.resolve_binding(part_uuid, artifact_revision)
        return ExactFeatureLookup(binding=binding, payload=self._read_cache(binding))

    def resolve_binding(
        self,
        part_uuid: str,
        artifact_revision: str,
    ) -> ExactFeatureBinding:
        requested_revision = artifact_revision.lower()
        if _SHA256_RE.fullmatch(requested_revision) is None:
            raise InvalidArtifactRevisionError(
                "artifact_revision must contain 64 lowercase hexadecimal characters"
            )
        with closing(connect_readonly(self.index_path)) as connection:
            part = connection.execute(
                "SELECT uuid FROM parts WHERE uuid = ?",
                (part_uuid,),
            ).fetchone()
            if part is None:
                raise PartNotFoundError(f"part UUID not found: {part_uuid}")
            artifact = connection.execute(
                """
                SELECT relative_path, sha256, byte_count, state
                FROM artifacts
                WHERE part_uuid = ? AND kind = 'step'
                """,
                (part_uuid,),
            ).fetchone()
        if (
            artifact is None
            or artifact["sha256"] is None
            or str(artifact["state"]) != "indexed"
        ):
            raise ExactGeometryUnavailableError(
                f"part {part_uuid} has no indexed content-addressed STEP artifact"
            )
        current_revision = str(artifact["sha256"])
        if requested_revision != current_revision:
            raise ArtifactRevisionMismatchError(requested_revision, current_revision)
        return ExactFeatureBinding(
            part_uuid=part_uuid,
            artifact_revision=current_revision,
            relative_path=str(artifact["relative_path"]),
            byte_count=(
                int(artifact["byte_count"])
                if artifact["byte_count"] is not None
                else None
            ),
        )

    def job_contract(self, binding: ExactFeatureBinding) -> dict[str, Any]:
        return {
            "kind": _JOB_KIND,
            "part_uuid": binding.part_uuid,
            "artifact_revision": binding.artifact_revision,
            "schema_version": EXACT_FEATURE_SCHEMA_VERSION,
            "extractor_version": EXACT_FEATURE_EXTRACTOR_VERSION,
        }

    def extract_and_cache(
        self,
        part_uuid: str,
        artifact_revision: str,
        *,
        report: ProgressReporter | None = None,
        checkpoint: CancellationCheckpoint | None = None,
    ) -> dict[str, Any]:
        """Worker entrypoint; never call this from inventory or query handlers."""

        binding = self.resolve_binding(part_uuid, artifact_revision)
        notify = report or (lambda _phase, _progress, _message: None)
        check = checkpoint or (lambda: None)
        check()
        notify("verify_step", 0.10, "Verifying indexed STEP bytes")
        step_path, _source_identity = self._verified_artifact(binding)
        check()
        notify("extract_topology", 0.25, "Extracting exact STEP topology")
        payload = extract_step_features(
            step_path,
            part_uuid=binding.part_uuid,
            artifact_revision=binding.artifact_revision,
        )
        check()
        notify("verify_revision", 0.85, "Checking STEP revision after extraction")
        _step_path, source_identity = self._verified_artifact(binding)
        payload["source_file_identity"] = source_identity
        check()
        notify("write_cache", 0.95, "Publishing exact feature cache")
        self._write_cache(binding, payload)
        return {
            "part_uuid": binding.part_uuid,
            "artifact_revision": binding.artifact_revision,
            "feature_count": len(payload["features"]),
            "feature_counts": payload["feature_counts"],
            "cache_path": self._cache_path(binding).relative_to(self.project_root).as_posix(),
        }

    def _verified_artifact(
        self,
        binding: ExactFeatureBinding,
    ) -> tuple[Path, dict[str, int]]:
        path = self._safe_artifact_path(binding)
        try:
            before = path.stat()
        except FileNotFoundError as exc:
            raise ArtifactBytesChangedError(
                f"indexed STEP artifact is missing: {binding.relative_path}"
            ) from exc
        if binding.byte_count is not None and before.st_size != binding.byte_count:
            raise ArtifactBytesChangedError(
                f"STEP byte count changed: expected {binding.byte_count}, found {before.st_size}"
            )
        digest = _sha256_file(path)
        after = path.stat()
        if _filesystem_identity(before) != _filesystem_identity(after):
            raise ArtifactBytesChangedError("STEP artifact changed while its revision was verified")
        if digest != binding.artifact_revision:
            raise ArtifactBytesChangedError(
                "STEP SHA-256 no longer matches indexed artifact revision: "
                f"expected {binding.artifact_revision}, found {digest}"
            )
        return path, _filesystem_identity_payload(after)

    def _safe_artifact_path(self, binding: ExactFeatureBinding) -> Path:
        path = (self.project_root / binding.relative_path).resolve()
        try:
            path.relative_to(self.project_root)
        except ValueError as exc:
            raise ArtifactBytesChangedError(
                f"indexed STEP path escapes project root: {binding.relative_path}"
            ) from exc
        return path

    def _cache_path(self, binding: ExactFeatureBinding) -> Path:
        return self.cache_root / binding.part_uuid / f"{binding.artifact_revision}.json"

    def _read_cache(self, binding: ExactFeatureBinding) -> dict[str, Any] | None:
        path = self._cache_path(binding)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        expected = {
            "schema_version": EXACT_FEATURE_SCHEMA_VERSION,
            "extractor_version": EXACT_FEATURE_EXTRACTOR_VERSION,
            "part_uuid": binding.part_uuid,
            "artifact_revision": binding.artifact_revision,
            "geometry_authority": "step_kernel",
            "quality": "exact",
        }
        if any(payload.get(key) != value for key, value in expected.items()):
            return None
        if not isinstance(payload.get("features"), list):
            return None
        try:
            current_identity = _filesystem_identity_payload(self._safe_artifact_path(binding).stat())
        except OSError:
            return None
        if payload.get("source_file_identity") != current_identity:
            return None
        return payload

    def _write_cache(
        self,
        binding: ExactFeatureBinding,
        payload: dict[str, Any],
    ) -> None:
        destination = self._cache_path(binding)
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as target:
                json.dump(payload, target, indent=2, sort_keys=True)
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary_path, destination)
        except BaseException:
            temporary_path.unlink(missing_ok=True)
            raise


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _filesystem_identity(stat_result: os.stat_result) -> tuple[int, ...]:
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
        stat_result.st_ctime_ns,
    )


def _filesystem_identity_payload(stat_result: os.stat_result) -> dict[str, int]:
    return {
        "device": stat_result.st_dev,
        "inode": stat_result.st_ino,
        "byte_count": stat_result.st_size,
        "mtime_ns": stat_result.st_mtime_ns,
        "ctime_ns": stat_result.st_ctime_ns,
    }
