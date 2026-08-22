"""Stable, project-importable contracts for Flow CAD projects."""

from .manifest import ManifestError, dump_manifest, load_manifest, loads_manifest
from .models import (
    ArtifactSpec,
    AssemblyOccurrence,
    AssemblySpec,
    ManifestPart,
    PartRole,
    PartStatus,
    ProjectManifest,
)

__all__ = [
    "ArtifactSpec",
    "AssemblyOccurrence",
    "AssemblySpec",
    "ManifestError",
    "ManifestPart",
    "PartRole",
    "PartStatus",
    "ProjectManifest",
    "dump_manifest",
    "load_manifest",
    "loads_manifest",
]
