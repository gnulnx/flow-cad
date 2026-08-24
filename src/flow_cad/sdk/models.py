"""Typed, geometry-free models for the public Flow CAD manifest contract."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
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

    PRESERVED_ONLY = "preserved-only"
    ACTIVE = "active"
    REFERENCE = "reference"
    INSPECTION = "inspection"
    RETIRED = "retired"
    SUPERSEDED = "superseded"


class ReleaseHookKind(StrEnum):
    """A project-owned release extension with an explicit runtime phase."""

    VALIDATOR = "validator"
    INTERFERENCE = "interference"
    PRINT_MANIFEST = "print_manifest"


@dataclass(frozen=True, slots=True)
class ArtifactSpec:
    """One declared artifact without any loaded CAD geometry."""

    kind: str
    path: str
    sha256: str | None = None
    byte_count: int | None = None
    linear_tolerance: float | None = None
    angular_tolerance: float | None = None


@dataclass(frozen=True, slots=True)
class PrintSpec:
    """Project-owned manufacturing intent for a printable part."""

    shell_count: int
    infill_density: float


@dataclass(frozen=True, slots=True)
class MassProperties:
    """Optional measured or estimated rigid-body metadata in SI units."""

    mass_kg: float | None = None
    center_of_mass_mm: Vector3 | None = None
    inertia_kg_m2: tuple[float, float, float, float, float, float] | None = None
    source: str = "unset"
    status: str = "todo"
    notes: str = ""


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
    family: str | None = None
    version: str | None = None
    compatible_versions: tuple[str, ...] = ()
    print: PrintSpec | None = None
    mass_properties: MassProperties | None = None


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
    artifacts: tuple[ArtifactSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class ReleaseHookSpec:
    """Declarative reference to one project-owned release check."""

    key: str
    kind: ReleaseHookKind
    provider: str
    timeout_seconds: float = 30.0


@dataclass(frozen=True, slots=True)
class ReleaseArtifactIdentity:
    """Fresh built artifact identity supplied to project release hooks."""

    part_uuid: UUID
    part_key: str
    kind: str
    path: str
    sha256: str
    byte_count: int


@dataclass(frozen=True, slots=True)
class ReleaseHookContext:
    """Public, runtime-independent input to a project release hook."""

    project_id: str
    project_root: str
    artifact_manifest_path: str
    artifacts: tuple[ReleaseArtifactIdentity, ...]


@dataclass(frozen=True, slots=True)
class ReleaseHookResult:
    """Structured project release-hook result."""

    ok: bool
    summary: str
    details: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ProjectManifest:
    """Versioned project authority consumed by metadata-only runtime services."""

    schema_version: int
    project_id: str
    python_package: str
    parts: tuple[ManifestPart, ...]
    assemblies: tuple[AssemblySpec, ...]
    parameter_provider: str | None = None
    release_hooks: tuple[ReleaseHookSpec, ...] = ()
