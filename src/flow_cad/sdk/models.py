"""Typed, geometry-free models for the public Flow CAD manifest contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


Vector3 = tuple[float, float, float]


class PartRole(StrEnum):
    """A part's product role, independent of its build state."""

    PRINTABLE = "printable"
    REFERENCE = "reference"
    INSPECTION = "inspection"
    LEGACY = "legacy"


class PartStatus(StrEnum):
    """Lifecycle status for a manifest part."""

    ACTIVE = "active"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    """One declared artifact without any loaded CAD geometry."""

    kind: str
    path: str
    sha256: str | None = None
    byte_count: int | None = None


@dataclass(frozen=True, slots=True)
class ManifestPart:
    """A lifecycle record whose UUID remains stable when its key changes."""

    uuid: UUID
    key: str
    aliases: tuple[str, ...]
    generator: str
    role: PartRole
    status: PartStatus
    artifacts: tuple[ArtifactSpec, ...]
    material: str | None = None


@dataclass(frozen=True, slots=True)
class AssemblyOccurrence:
    """A UUID-based placement of one part in an assembly."""

    id: str
    part_uuid: UUID
    translation_mm: Vector3
    rotation_deg: Vector3


@dataclass(frozen=True, slots=True)
class AssemblySpec:
    """A named collection of placed part occurrences."""

    key: str
    occurrences: tuple[AssemblyOccurrence, ...]


@dataclass(frozen=True, slots=True)
class ProjectManifest:
    """Versioned project authority consumed by metadata-only runtime services."""

    schema_version: int
    project_id: str
    python_package: str
    parts: tuple[ManifestPart, ...]
    assemblies: tuple[AssemblySpec, ...]
