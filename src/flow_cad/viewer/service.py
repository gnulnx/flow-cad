from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from flow_cad.core.assembly import get_assembly_placements
from flow_cad.params import ChassisParams
from flow_cad.registry import PartDefinition, iter_part_definitions


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
        params: ChassisParams | None = None,
        converter: Converter = convert_step_to_stl,
    ):
        self.project_root = (project_root or PROJECT_ROOT).resolve()
        self.params = params or ChassisParams()
        self.converter = converter
        self.revision = 0
        self.reloaded_at: datetime | None = None

    @property
    def exports_dir(self) -> Path:
        return self.project_root / self.params.project_id / "exports"

    @property
    def viewer_cache_dir(self) -> Path:
        return self.project_root / self.params.project_id / "viewer-cache"

    def reload(self) -> dict[str, Any]:
        self.revision += 1
        self.reloaded_at = datetime.now(UTC)
        return {
            "ok": True,
            "revision": self.revision,
            "reloaded_at": self.reloaded_at.isoformat(),
        }

    def list_parts(self) -> dict[str, Any]:
        placement_map = self._placement_map()
        parts = [self._part_payload(definition, placement_map.get(definition.id, [])) for definition in iter_part_definitions()]
        return {
            "project_id": self.params.project_id,
            "revision": self.revision,
            "parts": parts,
        }

    def model_path(self, component_id: str) -> tuple[Path, str]:
        artifact = self._require_artifact(component_id)
        if artifact.source_format == "stl":
            return artifact.path, artifact.source_format

        assert artifact.source_format == "step"
        cached_stl = self._cached_stl_path(artifact.path)
        if self._cache_is_fresh(artifact.path, cached_stl):
            return cached_stl, artifact.source_format
        return self.converter(artifact.path, cached_stl), artifact.source_format

    def source_context(self, component_id: str, *, context_lines: int = 16) -> dict[str, Any]:
        definition = self._definition(component_id)
        factory = definition.factory
        try:
            source_file = Path(inspect.getsourcefile(factory) or "").resolve()
            lines, first_line = inspect.getsourcelines(factory)
        except (OSError, TypeError) as exc:
            raise ArtifactNotFoundError(f"Source context not available for component: {component_id}") from exc

        start_line = max(first_line - context_lines, 1)
        end_line = first_line + len(lines) + context_lines - 1
        all_lines = source_file.read_text().splitlines()
        excerpt = "\n".join(
            f"{line_no:4d}: {line}"
            for line_no, line in enumerate(all_lines[start_line - 1 : end_line], start=start_line)
        )
        symbol = getattr(factory, "__name__", component_id)

        return {
            "component_id": component_id,
            "symbol": symbol,
            "file_path": str(source_file),
            "relative_file_path": _relative_path(source_file, self.project_root),
            "start_line": start_line,
            "end_line": min(end_line, len(all_lines)),
            "excerpt": excerpt,
        }

    def _part_payload(self, definition: PartDefinition, occurrences: list[dict[str, Any]]) -> dict[str, Any]:
        artifact = self._artifact(definition)
        source_format = artifact.source_format if artifact is not None else None
        artifact_path = _relative_path(artifact.path, self.project_root) if artifact is not None else None
        direct_stl_path = (
            _relative_path(artifact.direct_stl_path, self.project_root)
            if artifact is not None and artifact.direct_stl_path is not None
            else None
        )
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
            "model_url": f"/api/parts/{definition.id}/model",
            "source_url": f"/api/parts/{definition.id}/source",
            "occurrences": occurrences or [self._identity_occurrence(definition.id)],
            "in_assembly": bool(occurrences),
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
        for definition in iter_part_definitions():
            if definition.id == component_id:
                return definition
        raise ArtifactNotFoundError(f"Component is not registered: {component_id}")

    def _cached_stl_path(self, step_path: Path) -> Path:
        rel_step = step_path.relative_to(self.exports_dir / "step")
        return self.viewer_cache_dir / "stl-from-step" / rel_step.with_suffix(".stl")

    @staticmethod
    def _cache_is_fresh(source_path: Path, cache_path: Path) -> bool:
        return cache_path.exists() and cache_path.stat().st_mtime >= source_path.stat().st_mtime

    def _placement_map(self) -> dict[str, list[dict[str, Any]]]:
        placement_map: dict[str, list[dict[str, Any]]] = {}
        for placement in get_assembly_placements(self.params, include_references=True):
            part_key = placement["part_key"]
            placement_map.setdefault(part_key, []).append(
                {
                    "name": placement["name"],
                    "location": _as_float_tuple(placement["location"]),
                    "rotation": _as_float_tuple(placement["rotation"]),
                }
            )
        return placement_map

    @staticmethod
    def _identity_occurrence(component_id: str) -> dict[str, Any]:
        return {
            "name": component_id,
            "location": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
        }
