from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from flow_cad.core.metadata import PartDefinition
from flow_cad.project import FlowCadProject, load_project
from flow_cad.viewer.geometry_authority import (
    GeometryAuthorityError,
    cache_metadata_matches,
    display_mesh_cache_metadata,
    extract_step_snap_features,
    geometry_for_artifact,
    snap_feature_cache_metadata,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ViewerError(RuntimeError):
    """Base viewer service error with an HTTP-friendly status code."""

    status_code = 500


class ArtifactNotFoundError(ViewerError):
    status_code = 404


class ConversionUnavailableError(ViewerError):
    status_code = 503


@dataclass(frozen=True)
class Artifact:
    path: Path
    source_format: str
    direct_stl_path: Path | None = None


Converter = Callable[[Path, Path], Path]


def _relative_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def _as_float_tuple(values: tuple[float, float, float]) -> list[float]:
    return [float(values[0]), float(values[1]), float(values[2])]


def _source_file_for_callable(func: Callable[..., Any]) -> Path | None:
    source_file = inspect.getsourcefile(func)
    if source_file is None:
        return None
    return Path(source_file).resolve()


def _resolve_source_callable(
    factory: Callable[..., Any],
    *,
    wrapper_source_files: tuple[Path, ...] = (),
) -> Callable[..., Any]:
    source_file = _source_file_for_callable(factory)
    wrapper_files = {path.resolve() for path in wrapper_source_files}
    if getattr(factory, "__name__", "") != "<lambda>" and source_file not in wrapper_files:
        return factory

    code = getattr(factory, "__code__", None)
    globals_ = getattr(factory, "__globals__", {})
    if code is None:
        return factory

    for name in code.co_names:
        candidate = globals_.get(name)
        if callable(candidate):
            candidate_source_file = _source_file_for_callable(candidate)
            if candidate_source_file is not None and candidate_source_file not in wrapper_files:
                return candidate

    return factory


def convert_step_to_stl(step_path: Path, stl_path: Path) -> Path:
    """Convert a STEP file to STL through the local build123d/OCP stack."""
    try:
        from build123d import export_stl, import_step
    except Exception as exc:  # pragma: no cover - depends on local CAD install
        raise ConversionUnavailableError(
            "STEP conversion requires build123d/OCP. Install project dependencies or configure the CAD environment."
        ) from exc

    try:
        stl_path.parent.mkdir(parents=True, exist_ok=True)
        shape = import_step(step_path)
        ok = export_stl(shape, stl_path)
    except Exception as exc:  # pragma: no cover - exact parser errors vary
        raise ConversionUnavailableError(f"Could not convert STEP to STL: {step_path}: {exc}") from exc

    if not ok or not stl_path.exists():
        raise ConversionUnavailableError(f"STEP conversion did not produce an STL file: {stl_path}")
    return stl_path


class ViewerService:
    def __init__(
        self,
        project_root: Path | None = None,
        *,
        params: Any | None = None,
        project: FlowCadProject | None = None,
        converter: Converter = convert_step_to_stl,
    ):
        self.project = project or load_project(project_root or Path.cwd())
        self.project_root = self.project.root
        self.params = params or self.project.make_params()
        self.converter = converter
        self.revision = 0
        self.reloaded_at: datetime | None = None

    @property
    def exports_dir(self) -> Path:
        return self.project.paths.exports

    @property
    def viewer_cache_dir(self) -> Path:
        return self.project.paths.local_state / "viewer-cache"

    def reload(self) -> dict[str, Any]:
        self.project = load_project(self.project_root)
        self.project_root = self.project.root
        self.params = self.project.make_params()
        self.revision += 1
        self.reloaded_at = datetime.now(UTC)
        return {
            "ok": True,
            "revision": self.revision,
            "reloaded_at": self.reloaded_at.isoformat(),
        }

    def list_parts(self) -> dict[str, Any]:
        placement_map = self._placement_map()
        default_visible_ids = self._default_visible_part_keys()
        parts = [
            self._part_payload(
                definition,
                placement_map.get(definition.id, []),
                default_visible=definition.id in default_visible_ids,
            )
            for definition in self.project.iter_part_definitions()
        ]
        return {
            "project_id": self.project.project_id,
            "revision": self.revision,
            "parts": parts,
        }

    def model_path(self, component_id: str) -> tuple[Path, str]:
        artifact = self._require_artifact(component_id)
        if artifact.source_format == "stl":
            return artifact.path, artifact.source_format

        assert artifact.source_format == "step"
        cached_stl = self._cached_stl_path(artifact.path)
        metadata_path = self._cached_metadata_path(cached_stl)
        if self._display_cache_is_fresh(artifact.path, cached_stl, metadata_path):
            return cached_stl, artifact.source_format
        converted = self.converter(artifact.path, cached_stl)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(display_mesh_cache_metadata(artifact.path), indent=2, sort_keys=True))
        return converted, artifact.source_format

    def snap_features(self, component_id: str) -> dict[str, Any]:
        artifact = self._artifact(self._definition(component_id))
        if artifact is None:
            return self._empty_snap_features(component_id, None)
        if artifact.source_format != "step":
            return self._empty_snap_features(component_id, artifact.source_format)

        cache_path = self._cached_snap_features_path(artifact.path)
        cached = self._read_json_cache(cache_path)
        if cached is not None and cache_metadata_matches(cached, snap_feature_cache_metadata(artifact.path)):
            return cached

        try:
            payload = extract_step_snap_features(artifact.path)
        except GeometryAuthorityError as exc:
            raise ConversionUnavailableError(str(exc)) from exc
        payload.update(
            {
                "component_id": component_id,
                "artifact_path": _relative_path(artifact.path, self.project_root),
                "geometry_authority": geometry_for_artifact(artifact.source_format).geometry_authority,
                "capabilities": geometry_for_artifact(artifact.source_format).to_payload()["capabilities"],
            }
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return payload

    def source_context(self, component_id: str, *, context_lines: int = 16) -> dict[str, Any]:
        definition = self._definition(component_id)
        source_callable = _resolve_source_callable(
            definition.factory,
            wrapper_source_files=self.project.source_wrapper_files,
        )
        try:
            source_file = Path(inspect.getsourcefile(source_callable) or "").resolve()
            lines, first_line = inspect.getsourcelines(source_callable)
        except (OSError, TypeError) as exc:
            raise ArtifactNotFoundError(f"Source context not available for component: {component_id}") from exc

        _ = context_lines
        content = source_file.read_text()
        all_lines = content.splitlines()
        highlight_end_line = first_line + len(lines) - 1
        excerpt = "\n".join(
            f"{line_no:4d}: {line}"
            for line_no, line in enumerate(all_lines, start=1)
        )
        symbol = getattr(source_callable, "__name__", component_id)
        language = "python" if source_file.suffix == ".py" else source_file.suffix.removeprefix(".")

        return {
            "component_id": component_id,
            "symbol": symbol,
            "file_path": str(source_file),
            "relative_file_path": _relative_path(source_file, self.project_root),
            "start_line": 1,
            "end_line": len(all_lines),
            "highlight_start_line": first_line,
            "highlight_end_line": highlight_end_line,
            "language": language,
            "content": content,
            "excerpt": excerpt,
        }

    def _part_payload(self, definition: PartDefinition, occurrences: list[dict[str, Any]], *, default_visible: bool) -> dict[str, Any]:
        artifact = self._artifact(definition)
        source_format = artifact.source_format if artifact is not None else None
        artifact_path = _relative_path(artifact.path, self.project_root) if artifact is not None else None
        direct_stl_path = (
            _relative_path(artifact.direct_stl_path, self.project_root)
            if artifact is not None and artifact.direct_stl_path is not None
            else None
        )
        geometry = geometry_for_artifact(source_format).to_payload()
        return {
            "id": definition.id,
            "module_id": definition.module_id,
            "filename": definition.filename,
            "role": str(definition.role),
            "material": definition.material,
            "is_printable": definition.is_printable,
            "artifact_format": source_format,
            "artifact_path": artifact_path,
            "direct_stl_path": direct_stl_path,
            "source_kind": geometry["source_kind"],
            "geometry_authority": geometry["geometry_authority"],
            "quality_label": geometry["quality_label"],
            "capabilities": geometry["capabilities"],
            "warnings": geometry["warnings"],
            "model_url": f"/api/parts/{definition.id}/model",
            "source_url": f"/api/parts/{definition.id}/source",
            "snap_features_url": f"/api/parts/{definition.id}/snap-features",
            "occurrences": occurrences or [self._identity_occurrence(definition.id)],
            "in_assembly": bool(occurrences),
            "default_visible": default_visible,
        }

    def _artifact(self, definition: PartDefinition) -> Artifact | None:
        step_path = self.exports_dir / "step" / definition.module_id / definition.filename
        stl_path = self.exports_dir / "stl" / definition.module_id / f"{Path(definition.filename).stem}.stl"
        if step_path.exists():
            return Artifact(step_path, "step", direct_stl_path=stl_path if stl_path.exists() else None)
        if stl_path.exists():
            return Artifact(stl_path, "stl", direct_stl_path=stl_path)
        return None

    def _require_artifact(self, component_id: str) -> Artifact:
        artifact = self._artifact(self._definition(component_id))
        if artifact is None:
            raise ArtifactNotFoundError(f"No generated STEP or STL artifact found for component: {component_id}. Run `flow cad build` first.")
        return artifact

    def _definition(self, component_id: str) -> PartDefinition:
        for definition in self.project.iter_part_definitions():
            if definition.id == component_id:
                return definition
        raise ArtifactNotFoundError(f"Component is not registered: {component_id}")

    def _cached_stl_path(self, step_path: Path) -> Path:
        rel_step = step_path.relative_to(self.exports_dir / "step")
        return self.viewer_cache_dir / "stl-from-step" / rel_step.with_suffix(".stl")

    def _cached_snap_features_path(self, step_path: Path) -> Path:
        rel_step = step_path.relative_to(self.exports_dir / "step")
        return self.viewer_cache_dir / "snap-features" / rel_step.with_suffix(".json")

    @staticmethod
    def _cache_is_fresh(source_path: Path, cache_path: Path) -> bool:
        return cache_path.exists() and cache_path.stat().st_mtime >= source_path.stat().st_mtime

    @staticmethod
    def _cached_metadata_path(cache_path: Path) -> Path:
        return cache_path.with_suffix(f"{cache_path.suffix}.json")

    def _display_cache_is_fresh(self, source_path: Path, cache_path: Path, metadata_path: Path) -> bool:
        if not self._cache_is_fresh(source_path, cache_path):
            return False
        cached = self._read_json_cache(metadata_path)
        return cached is not None and cache_metadata_matches(cached, display_mesh_cache_metadata(source_path))

    @staticmethod
    def _read_json_cache(cache_path: Path) -> dict[str, Any] | None:
        try:
            cached = json.loads(cache_path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return cached if isinstance(cached, dict) else None

    @staticmethod
    def _empty_snap_features(component_id: str, source_format: str | None) -> dict[str, Any]:
        geometry = geometry_for_artifact(source_format).to_payload()
        return {
            "component_id": component_id,
            "artifact_path": None,
            "schema_version": 2,
            "source_format": source_format,
            "features": [],
            "warnings": geometry["warnings"] if source_format == "stl" else [],
            "geometry_authority": geometry["geometry_authority"],
            "capabilities": geometry["capabilities"],
        }

    def _placement_map(self) -> dict[str, list[dict[str, Any]]]:
        placement_map: dict[str, list[dict[str, Any]]] = {}
        for placement in self.project.get_assembly_placements(self.params, include_references=True):
            part_key = placement["part_key"]
            placement_map.setdefault(part_key, []).append(
                {
                    "name": placement["name"],
                    "location": _as_float_tuple(placement["location"]),
                    "rotation": _as_float_tuple(placement["rotation"]),
                }
            )
        return placement_map

    def _default_visible_part_keys(self) -> set[str]:
        return {
            placement["part_key"]
            for placement in self.project.get_assembly_placements(self.params, include_references=True)
        }

    @staticmethod
    def _identity_occurrence(component_id: str) -> dict[str, Any]:
        return {
            "name": component_id,
            "location": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
        }
