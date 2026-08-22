"""Geometry-free planning and job submission for one-part builds."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable
from uuid import UUID

from flow_cad.jobs import JobService, JobSubmission
from flow_cad.sdk import ManifestPart, PartStatus, ProjectManifest, load_manifest


PROJECT_MANIFEST = "flowcad.project.yaml"
_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_SYMBOL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_BUILDABLE_STATUSES = {
    PartStatus.ACTIVE,
    PartStatus.REFERENCE,
    PartStatus.INSPECTION,
}


class BuildContractError(RuntimeError):
    """The manifest does not describe a safe isolated replacement build."""


class PartNotFoundError(BuildContractError):
    """The requested part identity is absent from the manifest."""


class PartNotBuildableError(BuildContractError):
    """The selected lifecycle record cannot create fresh replacement outputs."""


@dataclass(frozen=True, slots=True)
class BuildArtifactTarget:
    """One fresh artifact target owned exclusively by a selected part."""

    kind: str
    relative_path: str
    destination: Path


@dataclass(frozen=True, slots=True)
class ScopedPartBuildPlan:
    """Validated metadata passed into the CAD-importing build worker."""

    project_root: Path
    project_id: str
    python_package: str
    part_uuid: UUID
    part_key: str
    generator: str
    parameter_provider: str
    artifacts: tuple[BuildArtifactTarget, ...]

    def payload(self) -> dict[str, object]:
        return {
            "project_id": self.project_id,
            "part_uuid": str(self.part_uuid),
            "part_key": self.part_key,
            "generator": self.generator,
            "parameter_provider": self.parameter_provider,
            "artifacts": [
                {"kind": artifact.kind, "path": artifact.relative_path}
                for artifact in self.artifacts
            ],
        }


class PartBuildService:
    """Submit bounded, idempotent builds through the shared project job runner."""

    def __init__(self, project_root: Path, jobs: JobService) -> None:
        self.project_root = project_root.resolve()
        if jobs.store.project_root != self.project_root:
            raise ValueError("job service and build service must use the same project root")
        self.jobs = jobs

    def plan(self, part_key_or_uuid: str) -> ScopedPartBuildPlan:
        manifest = load_manifest(self.project_root / PROJECT_MANIFEST)
        part = _resolve_part(manifest.parts, part_key_or_uuid)
        return plan_scoped_part_build(self.project_root, manifest, part)

    def submit(self, *, request_id: str, part_key_or_uuid: str) -> JobSubmission:
        plan = self.plan(part_key_or_uuid)
        from .worker import scoped_part_build_work

        return self.jobs.submit(
            request_id=request_id,
            kind="part-build",
            payload=plan.payload(),
            work=scoped_part_build_work(plan),
        )


def plan_scoped_part_build(
    project_root: Path,
    manifest: ProjectManifest,
    part: ManifestPart,
) -> ScopedPartBuildPlan:
    """Validate a one-part output plan without importing project or CAD modules."""

    root = project_root.resolve()
    if part not in manifest.parts:
        raise PartNotFoundError(f"part is not declared by project {manifest.project_id}: {part.key}")
    if part.status not in _BUILDABLE_STATUSES:
        raise PartNotBuildableError(
            f"part {part.key!r} has non-buildable lifecycle status {part.status.value!r}"
        )
    provider = manifest.parameter_provider
    if provider is None:
        raise PartNotBuildableError(
            "manifest must declare parameter_provider: module:symbol before building parts"
        )
    _validate_project_symbol(provider, manifest.python_package, "parameter_provider")
    _validate_project_symbol(part.generator, manifest.python_package, f"part {part.key} generator")

    selected = _selected_artifacts(part)
    _validate_output_ownership(manifest.parts, part, selected)
    targets = tuple(_artifact_target(root, kind, path) for kind, path in selected)
    return ScopedPartBuildPlan(
        project_root=root,
        project_id=manifest.project_id,
        python_package=manifest.python_package,
        part_uuid=part.uuid,
        part_key=part.key,
        generator=part.generator,
        parameter_provider=provider,
        artifacts=targets,
    )


def _resolve_part(parts: Iterable[ManifestPart], key_or_uuid: str) -> ManifestPart:
    needle = key_or_uuid.strip()
    if not needle:
        raise PartNotFoundError("part key or UUID may not be empty")
    for part in parts:
        if needle in {part.key, str(part.uuid), *part.aliases}:
            return part
    raise PartNotFoundError(f"part not found: {needle}")


def _selected_artifacts(part: ManifestPart) -> tuple[tuple[str, str], ...]:
    by_kind: dict[str, str] = {}
    for artifact in part.artifacts:
        if artifact.kind not in {"step", "stl"}:
            continue
        if artifact.kind in by_kind:
            raise PartNotBuildableError(
                f"part {part.key!r} declares duplicate {artifact.kind!r} artifacts"
            )
        by_kind[artifact.kind] = artifact.path
    if "step" not in by_kind:
        raise PartNotBuildableError(
            f"part {part.key!r} must declare one STEP artifact for a scoped build"
        )
    ordered = [("step", by_kind["step"])]
    if "stl" in by_kind:
        ordered.append(("stl", by_kind["stl"]))
    return tuple(ordered)


def _validate_output_ownership(
    parts: Iterable[ManifestPart],
    selected_part: ManifestPart,
    selected: tuple[tuple[str, str], ...],
) -> None:
    owners: dict[str, tuple[UUID, str]] = {}
    for part in parts:
        for artifact in part.artifacts:
            if artifact.kind not in {"step", "stl"}:
                continue
            previous = owners.get(artifact.path)
            if previous is not None and previous[0] != part.uuid:
                raise PartNotBuildableError(
                    f"artifact output {artifact.path!r} is shared by parts "
                    f"{previous[0]} and {part.uuid}"
                )
            owners[artifact.path] = (part.uuid, artifact.kind)
    for kind, path in selected:
        owner = owners.get(path)
        if owner != (selected_part.uuid, kind):
            raise PartNotBuildableError(
                f"artifact output {path!r} is not isolated to part {selected_part.key!r}"
            )


def _artifact_target(root: Path, kind: str, relative_path: str) -> BuildArtifactTarget:
    pure_path = PurePosixPath(relative_path)
    if not pure_path.parts or pure_path.parts[0] != "exports":
        raise PartNotBuildableError(
            f"fresh {kind.upper()} output must be under project exports/: {relative_path}"
        )
    expected_suffixes = {"step": {".step", ".stp"}, "stl": {".stl"}}[kind]
    if pure_path.suffix.lower() not in expected_suffixes:
        suffixes = ", ".join(sorted(expected_suffixes))
        raise PartNotBuildableError(
            f"{kind.upper()} output must use one of {suffixes}: {relative_path}"
        )
    destination = (root / relative_path).resolve()
    try:
        destination.relative_to(root)
    except ValueError as exc:
        raise PartNotBuildableError(
            f"artifact output resolves outside the project: {relative_path}"
        ) from exc
    return BuildArtifactTarget(
        kind=kind,
        relative_path=relative_path,
        destination=destination,
    )


def _validate_project_symbol(reference: str, python_package: str, label: str) -> None:
    module, separator, symbol = reference.partition(":")
    if (
        separator != ":"
        or _MODULE_RE.fullmatch(module) is None
        or _SYMBOL_RE.fullmatch(symbol) is None
    ):
        raise PartNotBuildableError(f"{label} must be an importable module:symbol reference")
    if module != python_package and not module.startswith(f"{python_package}."):
        raise PartNotBuildableError(
            f"{label} must belong to project package {python_package!r}: {reference}"
        )
