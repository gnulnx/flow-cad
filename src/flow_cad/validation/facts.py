from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flow_cad.core.cache import get_component_cache, latest_build_metadata, params_as_json
from flow_cad.core.metadata import definition_export_subdir
from flow_cad.draft_geometry import DraftGeometryError, DraftGeometryStore
from flow_cad.project import FlowCadProject
from flow_cad.validation.contracts import GeometryAuthority, ValidatorIssue, error, warning
from flow_cad.viewer.geometry_authority import GeometryAuthorityError, extract_step_snap_features


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def _resolve_project_path(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _bbox_payload_from_shape(shape: Any) -> dict[str, Any]:
    bbox = shape.bounding_box()
    min_point = [float(bbox.min.X), float(bbox.min.Y), float(bbox.min.Z)]
    max_point = [float(bbox.max.X), float(bbox.max.Y), float(bbox.max.Z)]
    size = [max_point[index] - min_point[index] for index in range(3)]
    center = [(min_point[index] + max_point[index]) / 2.0 for index in range(3)]
    return {
        "units": "mm",
        "min": min_point,
        "max": max_point,
        "size": size,
        "center": center,
    }


def _bbox_payload_from_size(size: tuple[float, float, float]) -> dict[str, Any]:
    half = [value / 2.0 for value in size]
    return {
        "units": "mm",
        "min": [-half[0], -half[1], -half[2]],
        "max": [half[0], half[1], half[2]],
        "size": [float(size[0]), float(size[1]), float(size[2])],
        "center": [0.0, 0.0, 0.0],
    }


def _source_file_for_callable(func: Any) -> Path | None:
    try:
        source = inspect.getsourcefile(func)
    except TypeError:
        return None
    return Path(source).resolve() if source else None


def _definition_source_paths(definition: Any, project: FlowCadProject) -> tuple[Path, ...]:
    sources: list[Path] = []
    source = _source_file_for_callable(getattr(definition, "factory", None))
    if source is not None:
        sources.append(source)
    for wrapper in getattr(project, "source_wrapper_files", ()):
        sources.append(Path(wrapper).resolve())
    return tuple(sorted({path for path in sources if path.exists()}))


@dataclass(frozen=True)
class FactResult:
    facts: dict[str, Any] | None
    issues: tuple[ValidatorIssue, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.facts is not None and not any(issue.severity == "error" for issue in self.issues)


class ValidationFactProvider:
    """Read-only fact access for focused validators."""

    def __init__(self, project: FlowCadProject, *, params: Any | None = None):
        self.project = project
        self.params = params if params is not None else project.make_params()

    def definitions(self) -> list[dict[str, Any]]:
        return [self._definition_payload(definition) for definition in self.project.iter_part_definitions()]

    def definition(self, part_id: str) -> FactResult:
        definition = self._find_definition(part_id)
        if definition is None:
            return FactResult(
                None,
                (
                    error(
                        "definition_missing",
                        f"Part {part_id!r} is not registered in the active project.",
                        part_id=part_id,
                        geometry_authority=GeometryAuthority.UNKNOWN,
                        remediation="Check the project registry or run from the intended Flow CAD project root.",
                    ),
                ),
            )
        return FactResult(self._definition_payload(definition))

    def active_cache_row(
        self,
        part_id: str,
        *,
        required: bool = True,
        require_fresh: bool = True,
    ) -> FactResult:
        cache_path = self.project.paths.cache
        if not cache_path.exists():
            issue = error(
                "cache_missing",
                f"Active cache is missing: {_relative_path(cache_path, self.project.root)}.",
                part_id=part_id,
                artifact_path=_relative_path(cache_path, self.project.root),
                geometry_authority=GeometryAuthority.CACHE,
                remediation="Run `flow cad build` with cache enabled before requesting cache-backed facts.",
            )
            return FactResult(None, (issue,) if required else ())

        row = get_component_cache(cache_path, part_id)
        if row is None:
            issue = error(
                "cache_row_missing",
                f"Active cache has no row for part {part_id!r}.",
                part_id=part_id,
                artifact_path=_relative_path(cache_path, self.project.root),
                geometry_authority=GeometryAuthority.CACHE,
                remediation="Build the part or check the part id in the project registry.",
            )
            return FactResult(None, (issue,) if required else ())

        step_path = _resolve_project_path(self.project.root, row.step_path)
        payload = {
            "part_id": row.id,
            "module_id": row.module_id,
            "role": row.role,
            "metadata_status": row.metadata_status,
            "metadata_notes": row.metadata_notes,
            "step_path": str(step_path),
            "step_relative_path": _relative_path(step_path, self.project.root),
            "volume_mm3": float(row.volume_mm3),
            "bounding_box": _bbox_payload_from_size((float(row.bbox_x), float(row.bbox_y), float(row.bbox_z))),
            "compiled_at": row.compiled_at.isoformat(),
            "build_id": row.build_id,
            "geometry_authority": GeometryAuthority.CACHE,
        }
        issues: list[ValidatorIssue] = []
        if require_fresh:
            issues.extend(self._cache_freshness_issues(part_id, step_path, row.compiled_at.timestamp()))
        return FactResult(payload, tuple(issues))

    def step_artifact(self, part_id: str, *, required: bool = True) -> FactResult:
        definition = self._find_definition(part_id)
        if definition is None:
            return self.definition(part_id)

        step_path = self.project.paths.exports / "step" / definition_export_subdir(definition) / definition.filename
        if not step_path.exists():
            issue = error(
                "step_artifact_missing",
                f"STEP artifact is missing for part {part_id!r}: {_relative_path(step_path, self.project.root)}.",
                part_id=part_id,
                artifact_path=_relative_path(step_path, self.project.root),
                geometry_authority=GeometryAuthority.STEP,
                remediation="Run `flow cad build --part {}` or the appropriate build profile.".format(part_id),
            )
            return FactResult(None, (issue,) if required else ())
        return FactResult(
            {
                "part_id": part_id,
                "artifact_path": str(step_path),
                "artifact_relative_path": _relative_path(step_path, self.project.root),
                "geometry_authority": GeometryAuthority.STEP,
            }
        )

    def step_bounding_box(self, part_id: str) -> FactResult:
        artifact = self.step_artifact(part_id)
        if artifact.facts is None:
            return artifact
        step_path = Path(str(artifact.facts["artifact_path"]))
        try:
            from build123d import import_step

            shape = import_step(step_path)
            bbox = _bbox_payload_from_shape(shape)
        except Exception as exc:
            return FactResult(
                None,
                (
                    error(
                        "step_bbox_unavailable",
                        f"Could not read STEP bounding box for part {part_id!r}: {exc}",
                        part_id=part_id,
                        artifact_path=_relative_path(step_path, self.project.root),
                        geometry_authority=GeometryAuthority.STEP,
                        remediation="Regenerate the STEP artifact and confirm build123d/OCP can import it.",
                    ),
                ),
            )
        return FactResult(
            {
                **artifact.facts,
                "bounding_box": bbox,
                "geometry_authority": GeometryAuthority.STEP,
            }
        )

    def step_snap_features(self, part_id: str) -> FactResult:
        artifact = self.step_artifact(part_id)
        if artifact.facts is None:
            return artifact
        step_path = Path(str(artifact.facts["artifact_path"]))
        try:
            payload = extract_step_snap_features(step_path)
        except GeometryAuthorityError as exc:
            return FactResult(
                None,
                (
                    error(
                        "step_snap_unavailable",
                        str(exc),
                        part_id=part_id,
                        artifact_path=_relative_path(step_path, self.project.root),
                        geometry_authority=GeometryAuthority.STEP,
                    ),
                ),
            )
        payload.update(
            {
                "part_id": part_id,
                "artifact_path": str(step_path),
                "artifact_relative_path": _relative_path(step_path, self.project.root),
                "geometry_authority": GeometryAuthority.STEP,
            }
        )
        return FactResult(payload)

    def draft_facts(self, draft_token: str) -> FactResult:
        try:
            payload = DraftGeometryStore(self.project).measure_part(draft_token)
        except DraftGeometryError as exc:
            return FactResult(
                None,
                (
                    error(
                        "draft_missing",
                        str(exc),
                        geometry_authority=GeometryAuthority.DRAFT,
                        remediation="Check the draft token or recreate the draft in this project root.",
                    ),
                ),
            )
        payload["geometry_authority"] = GeometryAuthority.DRAFT
        return FactResult(payload)

    def draft_transaction_facts(self, transaction_token: str) -> FactResult:
        try:
            payload = DraftGeometryStore(self.project).transaction_measure(transaction_token)
        except DraftGeometryError as exc:
            return FactResult(
                None,
                (
                    error(
                        "draft_transaction_missing",
                        str(exc),
                        geometry_authority=GeometryAuthority.DRAFT,
                        remediation="Check the transaction token or recreate the draft transaction in this project root.",
                    ),
                ),
            )
        payload["geometry_authority"] = GeometryAuthority.DRAFT
        if isinstance(payload.get("draft"), dict):
            payload["draft"]["geometry_authority"] = GeometryAuthority.DRAFT
        return FactResult(payload)

    def viewer_placements(self, *, part_id: str | None = None) -> FactResult:
        placements: list[dict[str, Any]] = []
        for assembly_id in self._assembly_ids_for_viewer():
            try:
                raw_placements = list(
                    self.project.get_assembly_placements(
                        self.params,
                        include_references=True,
                        assembly_id=assembly_id,
                    )
                )
            except ValueError:
                continue
            for placement in raw_placements:
                part_key = str(placement["part_key"])
                if part_id and part_key != part_id:
                    continue
                payload = {
                    "name": str(placement["name"]),
                    "part_id": part_key,
                    "location": [float(value) for value in placement.get("location", (0.0, 0.0, 0.0))],
                    "rotation": [float(value) for value in placement.get("rotation", (0.0, 0.0, 0.0))],
                    "geometry_authority": GeometryAuthority.UNKNOWN,
                }
                if assembly_id:
                    payload["assembly_id"] = assembly_id
                placements.append(payload)
        if part_id and not placements:
            return FactResult(
                {"placements": [], "geometry_authority": GeometryAuthority.UNKNOWN},
                (
                    warning(
                        "placement_missing",
                        f"No viewer placement was found for part {part_id!r}.",
                        part_id=part_id,
                        geometry_authority=GeometryAuthority.UNKNOWN,
                        remediation="Check get_assembly_placements() or the expected assembly id.",
                    ),
                ),
            )
        return FactResult({"placements": placements, "geometry_authority": GeometryAuthority.UNKNOWN})

    def _definition_payload(self, definition: Any) -> dict[str, Any]:
        source_paths = [_relative_path(path, self.project.root) for path in _definition_source_paths(definition, self.project)]
        return {
            "id": str(getattr(definition, "id", "")),
            "module_id": str(getattr(definition, "module_id", "")),
            "filename": str(getattr(definition, "filename", "")),
            "role": str(getattr(definition, "role", "")),
            "family": str(getattr(definition, "family", "") or getattr(definition, "module_id", "")),
            "version": str(getattr(definition, "version", "") or ""),
            "source_files": source_paths,
            "geometry_authority": GeometryAuthority.UNKNOWN,
        }

    def _find_definition(self, part_id: str) -> Any | None:
        for definition in self.project.iter_part_definitions():
            if getattr(definition, "id", None) == part_id:
                return definition
        return None

    def _cache_freshness_issues(self, part_id: str, step_path: Path, compiled_at: float) -> list[ValidatorIssue]:
        issues: list[ValidatorIssue] = []
        if not step_path.exists():
            issues.append(
                error(
                    "cache_artifact_missing",
                    f"Cached STEP artifact is missing: {_relative_path(step_path, self.project.root)}.",
                    part_id=part_id,
                    artifact_path=_relative_path(step_path, self.project.root),
                    geometry_authority=GeometryAuthority.CACHE,
                    remediation="Run `flow cad build` to refresh cache and exports.",
                )
            )

        definition = self._find_definition(part_id)
        if definition is not None:
            stale_sources = [
                _relative_path(path, self.project.root)
                for path in _definition_source_paths(definition, self.project)
                if path.stat().st_mtime > compiled_at
            ]
            if stale_sources:
                issues.append(
                    error(
                        "cache_source_stale",
                        f"Active cache for part {part_id!r} is older than source files.",
                        part_id=part_id,
                        expected="cache compiled after source changes",
                        actual=stale_sources,
                        geometry_authority=GeometryAuthority.CACHE,
                        remediation="Run `flow cad build --changed` or rebuild the part before using cache-backed facts.",
                    )
                )

        latest = latest_build_metadata(self.project.paths.cache)
        if latest is not None:
            try:
                current_params = params_as_json(self.params)
                cached_params = latest.parameters_json
            except Exception:
                current_params = ""
                cached_params = ""
            if current_params and cached_params and current_params != cached_params:
                issues.append(
                    error(
                        "cache_params_stale",
                        "Active cache parameter snapshot does not match current project parameters.",
                        part_id=part_id,
                        expected=json.loads(current_params),
                        actual=json.loads(cached_params),
                        geometry_authority=GeometryAuthority.CACHE,
                        remediation="Run `flow cad build --changed` after parameter edits.",
                    )
                )
        return issues

    def _assembly_ids_for_viewer(self) -> list[str | None]:
        assembly_ids = [
            str(assembly_id)
            for definition in self.project.iter_part_definitions()
            for assembly_id in tuple(getattr(definition, "assembly_ids", ()) or ())
            if assembly_id
        ]
        active_ids = tuple(getattr(self.project.assembly_definition, "assembly_ids", ()) or ())
        active = str(active_ids[0]) if active_ids else None
        ordered: list[str | None] = []
        if active:
            ordered.append(active)
        for assembly_id in sorted(set(assembly_ids)):
            if assembly_id not in ordered:
                ordered.append(assembly_id)
        return ordered or [None]
