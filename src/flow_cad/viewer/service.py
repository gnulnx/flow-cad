from __future__ import annotations

import inspect
import json
import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from flow_cad.core.metadata import PartDefinition, definition_export_subdir
from flow_cad.draft_geometry import DraftGeometryError, DraftGeometryStore
from flow_cad.draft_operations import draft_operation_payloads
from flow_cad.preview_commands import PreviewCommandContext, parse_panel_command
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


class InvalidViewerImportError(ViewerError):
    status_code = 400


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


def _file_identity(path: Path, project_root: Path) -> dict[str, Any]:
    stat = path.stat()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "artifact_path": _relative_path(path, project_root),
        "artifact_mtime_ns": stat.st_mtime_ns,
        "artifact_size": stat.st_size,
        "artifact_hash": digest,
        "artifact_identity": f"{stat.st_mtime_ns}-{stat.st_size}-{digest[:16]}",
    }


def _cache_busted_url(path: str, identity: dict[str, Any] | None) -> str:
    token = (identity.get("artifact_hash") or identity.get("artifact_identity")) if identity else None
    return f"{path}?v={token}" if token else path


def _as_float_tuple(values: tuple[float, float, float]) -> list[float]:
    return [float(values[0]), float(values[1]), float(values[2])]


def _maybe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        self.drafts = DraftGeometryStore(self.project)
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
        self.drafts = DraftGeometryStore(self.project)
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
        active_version = self._active_version(default_visible_ids)
        active_assembly_id = self._active_assembly_id()
        parts = [
            self._part_payload(
                definition,
                placement_map.get(definition.id, []),
                default_visible=definition.id in default_visible_ids,
            )
            for definition in self.project.iter_part_definitions()
        ]
        versions = self._versions(parts, active_version)
        return {
            "project_id": self.project.project_id,
            "project_name": self.project.name,
            "revision": self.revision,
            "active_version": active_version,
            "active_assembly_id": active_assembly_id,
            "versions": versions,
            "parts": parts,
        }

    def get_part_payload(self, component_id: str) -> dict[str, Any]:
        definition = self._definition(component_id)
        return self._part_payload(
            definition,
            self._placement_map().get(definition.id, []),
            default_visible=definition.id in self._default_visible_part_keys(),
        )

    def part_source_context(self, component_id: str) -> dict[str, Any]:
        definition = self._definition(component_id)
        return self._part_source_context_payload(definition)

    def runtime_context(self) -> dict[str, Any]:
        return {
            "project_id": self.project.project_id,
            "project_name": self.project.name,
            "active_assembly_id": self._active_assembly_id(),
            "active_version": self._active_version(self._default_visible_part_keys()),
            "revision": self.revision,
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

    def part_artifact_identity(self, component_id: str) -> dict[str, Any]:
        definition = self._definition(component_id)
        artifact = self._require_artifact(component_id)
        return self._artifact_identity_payload(definition, artifact)

    def refresh(self, *, part_id: str | None = None, force_model_refetch: bool = False) -> dict[str, Any]:
        reload_payload = self.reload()
        parts_payload = self.list_parts()
        parts = parts_payload["parts"]
        selected_part = None
        if part_id:
            selected_part = next((part for part in parts if part["id"] == part_id), None)
            if selected_part is None:
                raise ArtifactNotFoundError(f"Component is not registered: {part_id}")
        rendered_artifacts = [
            self._rendered_artifact_summary(part)
            for part in parts
            if not part_id or part["id"] == part_id
        ]
        return {
            "ok": True,
            "project_root": str(self.project_root),
            "revision": reload_payload["revision"],
            "reloaded_at": reload_payload["reloaded_at"],
            "force_model_refetch": force_model_refetch,
            "part_id": part_id,
            "part_refetched": bool(part_id and selected_part is not None),
            "rendered_artifacts": rendered_artifacts,
            "part": selected_part,
        }

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

    def import_step_file(self, filename: str, content: bytes) -> dict[str, Any]:
        source_filename = _safe_import_filename(filename)
        if source_filename.suffix.lower() not in {".step", ".stp"}:
            raise InvalidViewerImportError("Flow CAD viewer imports currently accept .step and .stp files.")
        if not content:
            raise InvalidViewerImportError("Imported STEP file is empty.")

        import_id = hashlib.sha256(source_filename.name.encode("utf-8") + b"\0" + content).hexdigest()[:16]
        import_dir = self.viewer_cache_dir / "imports" / import_id
        source_path = import_dir / source_filename.name
        display_stl_path = import_dir / f"{source_filename.stem}.stl"
        metadata_path = import_dir / "import.json"

        import_dir.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(content)
        converted = self.converter(source_path, display_stl_path)

        geometry = geometry_for_artifact("step").to_payload()
        geometry["source_kind"] = "step"
        warnings = list(geometry.get("warnings", []))
        snap_features: list[dict[str, Any]] = []
        try:
            snap_payload = extract_step_snap_features(source_path)
            features = snap_payload.get("features")
            if isinstance(features, list):
                snap_features = features
            snap_warnings = snap_payload.get("warnings")
            if isinstance(snap_warnings, list):
                warnings.extend(str(warning) for warning in snap_warnings)
        except GeometryAuthorityError as exc:
            warnings.append(f"STEP snap features unavailable: {exc}")

        metadata = {
            "import_id": import_id,
            "filename": source_filename.name,
            "source_path": str(source_path),
            "display_stl_path": str(converted),
            "source_format": "step",
            "created_at": datetime.now(UTC).isoformat(),
            "geometry": geometry,
            "warnings": warnings,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True))

        source_identity = _file_identity(source_path, self.project_root)
        return {
            "import_id": import_id,
            "part_id": f"file:{source_filename.name}",
            "name": source_filename.name,
            "filename": source_filename.name,
            "source_format": "step",
            "model_url": _cache_busted_url(f"/api/imports/{import_id}/model", source_identity),
            **{
                f"source_{key}" if key == "artifact_path" else key: value
                for key, value in source_identity.items()
            },
            "display_stl_cache_path": _relative_path(converted, self.project_root),
            "snap_features": snap_features,
            **geometry,
            "warnings": warnings,
        }

    def imported_model_path(self, import_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{16}", import_id):
            raise ArtifactNotFoundError(f"Imported model not found: {import_id}")
        metadata_path = self.viewer_cache_dir / "imports" / import_id / "import.json"
        if not metadata_path.exists():
            raise ArtifactNotFoundError(f"Imported model not found: {import_id}")
        metadata = json.loads(metadata_path.read_text())
        display_stl_path = metadata.get("display_stl_path")
        if not isinstance(display_stl_path, str):
            raise ArtifactNotFoundError(f"Imported model has no display mesh: {import_id}")
        path = Path(display_stl_path).resolve()
        import_dir = (self.viewer_cache_dir / "imports" / import_id).resolve()
        if import_dir not in path.parents:
            raise ArtifactNotFoundError(f"Imported model display mesh not found: {import_id}")
        if not path.exists():
            raise ArtifactNotFoundError(f"Imported model display mesh not found: {import_id}")
        return path

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

    def preview_context(self, component_id: str) -> dict[str, Any]:
        definition = self._definition(component_id)
        placement_map = self._placement_map()
        default_visible_ids = self._default_visible_part_keys()

        part_payload = self._part_payload(
            definition,
            placement_map.get(definition.id, []),
            default_visible=definition.id in default_visible_ids,
        )

        context_payload = self._part_source_context_payload(definition)
        snap_summary = self._preview_snap_feature_summary(component_id)
        bounds_payload = self._preview_bounds_payload(component_id)
        source_context_available = bool(context_payload.get("available"))

        return {
            **part_payload,
            "component_id": definition.id,
            "active_assembly_id": self._active_assembly_id(),
            "source_context": context_payload,
            "source_context_available": source_context_available,
            "source_url": part_payload["source_url"] if source_context_available else None,
            "snap_feature_summary": snap_summary,
            "preview_bounds": bounds_payload,
            "source_measurements": self._measurement_summary(
                bounds_payload,
                str(part_payload["geometry_authority"]),
                "part",
            ),
            "project_frame": self._project_frame_payload(),
            "local_frame": self._local_frame_payload(part_payload["occurrences"]),
            "mating_contracts": self._mating_contracts_payload(),
        }

    def preview_command_proposal(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = str(payload.get("command") or "")
        component_id = payload.get("part_id") or payload.get("component_id")
        transaction_token = payload.get("transaction_token")
        context = None
        if isinstance(transaction_token, str) and transaction_token:
            try:
                context = self._preview_command_context_for_transaction(transaction_token)
            except (DraftGeometryError, ViewerError, KeyError, ValueError):
                context = None
        if context is None and isinstance(component_id, str) and component_id:
            context = self._preview_command_context(component_id)
        parsed = parse_panel_command(command, context=context)
        result = parsed.to_payload()
        result["part_id"] = context.part_id if context and context.part_id else component_id
        if isinstance(transaction_token, str) and transaction_token:
            result["transaction_token"] = transaction_token
        return result

    def draft_operation_registry(self) -> dict[str, Any]:
        operations = draft_operation_payloads()
        return {
            "ok": True,
            "operations": operations,
            "count": len(operations),
            "source": "flow_cad.draft_operations",
        }

    def draft_transaction_from_panel_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = str(payload.get("command") or "")
        selected_part_id = payload.get("selected_part_id") or payload.get("component_id")
        requested_transaction_token = payload.get("transaction_token")
        transaction_token = requested_transaction_token if isinstance(requested_transaction_token, str) and requested_transaction_token else None
        context = None
        if transaction_token:
            try:
                context = self._preview_command_context_for_transaction(transaction_token)
            except (DraftGeometryError, ViewerError, KeyError, ValueError):
                context = None
        if context is None and isinstance(selected_part_id, str) and selected_part_id:
            try:
                context = self._preview_command_context(selected_part_id)
            except ViewerError:
                context = None

        parsed = parse_panel_command(command, context=context)
        if not parsed.ok:
            return {
                "ok": False,
                "command": command,
                "proposal": parsed.to_payload(),
                "errors": list(parsed.errors),
                "warnings": list(parsed.warnings),
                "assumptions": list(parsed.assumptions),
            }

        if transaction_token:
            status = self.draft_transaction_status(transaction_token)
            part_id = str(status.get("part_id") or context.part_id if context else self._draft_chat_part_id(payload, command))
        else:
            part_id = self._draft_chat_part_id(payload, command)
            transaction = self.draft_begin_transaction({"part_id": part_id})
            transaction_token = str(transaction["transaction_token"])
        applied_operations: list[dict[str, Any]] = []
        for operation in parsed.operations:
            applied_operations.append(self._apply_preview_operation(transaction_token, operation, part_id))

        preview_model = self.draft_transaction_preview_model(transaction_token)
        return {
            "ok": True,
            "command": command,
            "part_id": part_id,
            "selected_part_id": selected_part_id if isinstance(selected_part_id, str) else None,
            "transaction_token": transaction_token,
            "proposal": parsed.to_payload(),
            "applied_operations": applied_operations,
            "preview_model": preview_model,
            "warnings": list(parsed.warnings),
            "assumptions": list(parsed.assumptions),
            "source_loop_commands": preview_model.get("source_loop_commands", []),
        }

    def draft_transaction_from_annotated_walls(self, payload: dict[str, Any]) -> dict[str, Any]:
        command = str(payload.get("command") or "")
        lowered = command.lower()
        if not any(term in lowered for term in ("raised wall", "wall", "raised pad", "pad", "raise up")):
            return {"ok": False, "command": command, "errors": ["Command does not ask for raised wall geometry."]}

        transaction_token = payload.get("transaction_token")
        if not isinstance(transaction_token, str) or not transaction_token.strip():
            return {"ok": False, "command": command, "errors": ["No active draft transaction was provided."]}
        transaction_token = transaction_token.strip()

        annotations = payload.get("annotations")
        rectangles = self._annotation_rectangles(annotations if isinstance(annotations, list) else [])
        if not rectangles:
            return {"ok": False, "command": command, "errors": ["No usable annotation rectangles were provided."]}

        heights = self._requested_wall_heights(command, len(rectangles))
        if len(heights) != len(rectangles):
            return {
                "ok": False,
                "command": command,
                "errors": [
                    f"Expected {len(rectangles)} wall heights, but found {len(heights)} usable numeric values."
                ],
            }

        status = self.draft_transaction_status(transaction_token)
        draft = status.get("draft") if isinstance(status.get("draft"), dict) else {}
        dimensions = draft.get("dimensions") if isinstance(draft.get("dimensions"), dict) else {}
        try:
            length = float(dimensions["length"])
            width = float(dimensions["width"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ViewerError(f"Active draft transaction has no measurable top face: {transaction_token}") from exc

        applied_operations: list[dict[str, Any]] = []
        for rectangle, height in zip(rectangles, heights, strict=True):
            min_x, max_x, min_y, max_y = rectangle
            parameters = {
                "face": "top",
                "x": ((min_x + max_x) / 2.0) * length,
                "y": ((min_y + max_y) / 2.0) * width,
                "length": max((max_x - min_x) * length, 1.0),
                "width": max((max_y - min_y) * width, 1.0),
                "height": height,
            }
            result = self.draft_transaction_add_raised_wall(transaction_token, parameters)
            applied_operations.append(
                {
                    "name": "add_raised_wall",
                    "endpoint": "raised-walls",
                    "parameters": parameters,
                    "result": result,
                }
            )

        preview_model = self.draft_transaction_preview_model(transaction_token)
        part_id = str(status.get("part_id") or preview_model.get("part_id") or "")
        assumptions = [
            "Mapped saved freehand annotation bounding boxes from normalized viewport coordinates onto the draft top face.",
            "Applied requested wall heights in annotation order.",
        ]
        return {
            "ok": True,
            "command": command,
            "part_id": part_id,
            "transaction_token": transaction_token,
            "applied_operations": applied_operations,
            "preview_model": preview_model,
            "warnings": [],
            "assumptions": assumptions,
            "source_loop_commands": preview_model.get("source_loop_commands", []),
        }

    def draft_transaction_preview_model(self, transaction_token: str) -> dict[str, Any]:
        preview_payload, _, display_stl_path = self._prepare_draft_preview_model(transaction_token)
        geometry = geometry_for_artifact("step").to_payload()
        step_path = Path(preview_payload["preview_step_path"]) if isinstance(preview_payload.get("preview_step_path"), str) else None
        preview_step_path = str(step_path) if step_path is not None else None
        draft_payload = preview_payload.get("draft") if isinstance(preview_payload.get("draft"), dict) else {}
        dimensions = draft_payload.get("dimensions") if isinstance(draft_payload, dict) else None
        feature_list = draft_payload.get("feature_list", []) if isinstance(draft_payload, dict) else []
        feature_count = len(feature_list) if isinstance(feature_list, list) else 0
        part_id = str(preview_payload.get("part_id") or draft_payload.get("part_id") or "")

        return {
            "ok": True,
            "transaction_token": transaction_token,
            "part_id": part_id,
            "model_url": _cache_busted_url(
                f"/api/draft-transactions/{transaction_token}/model",
                _file_identity(step_path, self.project_root) if step_path is not None and step_path.exists() else None,
            ),
            "draft": draft_payload or preview_payload.get("draft"),
            "preview_step_path": preview_step_path,
            "preview_step_relative_path": _relative_path(step_path, self.project_root) if step_path is not None else None,
            "source_step_path": preview_step_path,
            "display_stl_path": str(display_stl_path),
            "display_stl_relative_path": _relative_path(display_stl_path, self.project_root),
            "display_stl_cache_path": _relative_path(display_stl_path, self.project_root),
            **(
                _file_identity(step_path, self.project_root)
                if step_path is not None and step_path.exists()
                else {}
            ),
            "geometry_authority": geometry["geometry_authority"],
            "quality_label": geometry["quality_label"],
            "source_format": "step",
            "capabilities": geometry["capabilities"],
            "warnings": geometry["warnings"],
            "facts": self._draft_preview_facts(dimensions, feature_count),
            "dimensions": self._draft_dimension_summary(dimensions),
            "source_loop_commands": self._source_loop_commands(preview_payload),
            **{
                key: preview_payload.get(key)
                for key in (
                    "status",
                    "generated_source_path",
                    "generated_source_relative_path",
                    "validator_stub_path",
                    "validator_stub_relative_path",
                    "source_patch_path",
                    "source_patch_relative_path",
                    "acceptance_manifest_path",
                    "acceptance_manifest_relative_path",
                )
                if key in preview_payload
            },
        }

    def _draft_chat_part_id(self, payload: dict[str, Any], command: str) -> str:
        explicit = payload.get("part_id")
        if isinstance(explicit, str) and explicit.strip():
            return self._safe_part_id(explicit)

        lowered = command.lower()
        if "base plate" in lowered or "baseplate" in lowered:
            return "base_plate"
        if "plate" in lowered:
            return "draft_plate"
        if "panel" in lowered:
            return "draft_panel"

        selected = payload.get("selected_part_id") or payload.get("component_id")
        if isinstance(selected, str) and selected.strip():
            return self._safe_part_id(selected)
        return "draft_panel"

    @staticmethod
    def _requested_wall_heights(command: str, count: int) -> list[float]:
        values = [
            float(match.group(0))
            for match in re.finditer(r"(?<![A-Za-z])\b\d+(?:\.\d+)?", command)
        ]
        if len(values) < count:
            return []
        return values[-count:]

    @staticmethod
    def _annotation_rectangles(annotations: list[Any]) -> list[tuple[float, float, float, float]]:
        rectangles: list[tuple[float, float, float, float]] = []
        for annotation in annotations:
            if not isinstance(annotation, dict):
                continue
            points = annotation.get("points")
            if not isinstance(points, list) or len(points) < 3:
                continue
            xs: list[float] = []
            ys: list[float] = []
            for point in points:
                if not isinstance(point, dict):
                    continue
                x = _maybe_float(point.get("x"))
                y = _maybe_float(point.get("y"))
                if x is None or y is None:
                    continue
                xs.append(min(max(x, 0.0), 1.0))
                ys.append(min(max(y, 0.0), 1.0))
            if len(xs) < 3 or len(ys) < 3:
                continue
            min_x = min(xs)
            max_x = max(xs)
            min_y = min(ys)
            max_y = max(ys)
            if max_x - min_x < 0.005 or max_y - min_y < 0.005:
                continue
            rectangles.append((min_x, max_x, min_y, max_y))
        return rectangles

    def _preview_command_context_for_transaction(self, transaction_token: str) -> PreviewCommandContext:
        status = self.draft_transaction_status(transaction_token)
        draft = status.get("draft") if isinstance(status.get("draft"), dict) else {}
        dimensions = draft.get("dimensions") if isinstance(draft.get("dimensions"), dict) else {}
        part_id = status.get("part_id")
        return PreviewCommandContext(
            part_id=str(part_id) if isinstance(part_id, str) and part_id else None,
            length=_maybe_float(dimensions.get("length")),
            width=_maybe_float(dimensions.get("width")),
            thickness=_maybe_float(dimensions.get("height")),
        )

    @staticmethod
    def _safe_part_id(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower()).strip("_")
        return slug or "draft_panel"

    def _apply_preview_operation(self, transaction_token: str, operation: Any, part_id: str) -> dict[str, Any]:
        payload = dict(operation.parameters)
        if operation.name == "create_box":
            payload.setdefault("part_id", part_id)
            result = self.draft_transaction_create_box(transaction_token, payload)
            endpoint = "box"
        elif operation.name in {"create_profile", "create_sketch_profile", "create_extruded_profile"}:
            payload.setdefault("part_id", part_id)
            result = self.draft_transaction_create_profile(transaction_token, payload)
            endpoint = "profile"
        elif operation.name == "set_panel_thickness":
            result = self.draft_transaction_set_panel_thickness(transaction_token, payload)
            endpoint = "thickness"
        elif operation.name == "add_hole":
            result = self.draft_transaction_add_hole(transaction_token, payload)
            endpoint = "holes"
        elif operation.name == "add_counterbore":
            result = self.draft_transaction_add_counterbore(transaction_token, payload)
            endpoint = "counterbores"
        elif operation.name == "add_slot":
            result = self.draft_transaction_add_slot(transaction_token, payload)
            endpoint = "slots"
        elif operation.name == "add_raised_wall":
            result = self.draft_transaction_add_raised_wall(transaction_token, payload)
            endpoint = "raised-walls"
        elif operation.name == "add_louver_pattern":
            result = self.draft_transaction_add_louver_pattern(transaction_token, payload)
            endpoint = "louver-patterns"
        elif operation.name == "mirror_features":
            result = self.draft_transaction_mirror_features(transaction_token, payload)
            endpoint = "mirror-features"
        else:
            raise ViewerError(f"Unsupported preview operation: {operation.name}")

        return {
            "name": operation.name,
            "endpoint": endpoint,
            "parameters": payload,
            "result": result,
        }

    def draft_transaction_model(self, transaction_token: str) -> Path:
        _, _, display_stl_path = self._prepare_draft_preview_model(transaction_token)
        return display_stl_path

    def draft_transaction_status(self, transaction_token: str) -> dict[str, Any]:
        payload = self.drafts.transaction_measure(transaction_token)
        return self._with_source_loop_metadata(payload)

    def _prepare_draft_preview_model(self, transaction_token: str) -> tuple[dict[str, Any], Path, Path]:
        status_payload = self.drafts.transaction_measure(transaction_token)
        preview_step_path = status_payload.get("preview_step_path")

        # Refresh draft step only when preview has never been generated for the
        # current operation sequence.
        status = str(status_payload.get("status") or "")
        operations = status_payload.get("operations", []) or []
        if (
            not isinstance(preview_step_path, str)
            or (status == "open" and operations and operations[-1].get("name") != "preview")
        ):
            status_payload = self.drafts.transaction_preview(transaction_token)
            preview_step_path = status_payload.get("preview_step_path")

        if not isinstance(preview_step_path, str):
            raise ArtifactNotFoundError(f"Draft transaction preview has no STEP artifact yet: {transaction_token}")

        step_path = Path(preview_step_path)
        display_stl_path = self._transaction_preview_stl_path(transaction_token)
        metadata_path = self._cached_metadata_path(display_stl_path)
        if not self._display_cache_is_fresh(step_path, display_stl_path, metadata_path):
            converted = self.converter(step_path, display_stl_path)
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            metadata_path.write_text(json.dumps(display_mesh_cache_metadata(step_path), indent=2, sort_keys=True))
            display_stl_path = converted
        return status_payload, step_path, display_stl_path

    def draft_create_box(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.create_box_part(
            id=payload.get("id"),
            part_id=payload.get("part_id"),
            length=payload["length"],
            width=payload["width"],
            height=payload["height"],
            material=payload.get("material", "draft"),
            role=payload.get("role", "draft"),
        )

    def draft_create_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.create_profile_part(
            id=payload.get("id"),
            part_id=payload.get("part_id"),
            length=payload["length"],
            width=payload["width"],
            height=payload["height"],
            profile_points=payload["profile_points"],
            material=payload.get("material", "draft"),
            role=payload.get("role", "draft"),
        )

    def draft_set_panel_thickness(self, draft_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.set_panel_thickness(draft_token, thickness=payload["thickness"])

    def draft_add_hole(self, draft_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.add_hole(
            draft_token,
            face=payload["face"],
            x=payload["x"],
            y=payload["y"],
            diameter=payload["diameter"],
            through=payload.get("through", True),
        )

    def draft_add_counterbore(self, draft_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.add_counterbore(
            draft_token,
            face=payload["face"],
            x=payload["x"],
            y=payload["y"],
            diameter=payload["diameter"],
            depth=payload["depth"],
        )

    def draft_add_slot(self, draft_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.add_slot(
            draft_token,
            face=payload["face"],
            x=payload["x"],
            y=payload["y"],
            length=payload["length"],
            width=payload["width"],
            angle=payload.get("angle", 0.0),
        )

    def draft_add_raised_wall(self, draft_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.add_raised_wall(
            draft_token,
            face=payload["face"],
            x=payload["x"],
            y=payload["y"],
            length=payload["length"],
            width=payload["width"],
            height=payload["height"],
        )

    def draft_add_louver_pattern(self, draft_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.add_louver_pattern(
            draft_token,
            face=payload["face"],
            count=payload["count"],
            pitch=payload["pitch"],
            x=payload["x"],
            y=payload["y"],
            width=payload["width"],
            height=payload["height"],
            angle=payload.get("angle", 0.0),
        )

    def draft_mirror_features(self, draft_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.mirror_features(
            draft_token,
            source_face=payload["source_face"],
            target_face=payload["target_face"],
        )

    def draft_measure(self, draft_token: str) -> dict[str, Any]:
        return self.drafts.measure_part(draft_token)

    def draft_export_step(self, draft_token: str) -> dict[str, Any]:
        return self.drafts.export_draft_step(draft_token)

    def draft_discard(self, draft_token: str) -> dict[str, Any]:
        return self.drafts.discard(draft_token)

    def draft_begin_transaction(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.begin_transaction(part_id=payload.get("part_id"))

    def draft_transaction_create_box(self, transaction_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.transaction_create_box(
            transaction_token,
            part_id=payload.get("part_id"),
            length=payload["length"],
            width=payload["width"],
            height=payload["height"],
            material=payload.get("material", "draft"),
            role=payload.get("role", "draft"),
        )

    def draft_transaction_create_profile(self, transaction_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.transaction_create_profile(
            transaction_token,
            part_id=payload.get("part_id"),
            length=payload["length"],
            width=payload["width"],
            height=payload["height"],
            profile_points=payload["profile_points"],
            material=payload.get("material", "draft"),
            role=payload.get("role", "draft"),
        )

    def draft_transaction_set_panel_thickness(self, transaction_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.transaction_set_panel_thickness(transaction_token, thickness=payload["thickness"])

    def draft_transaction_add_hole(self, transaction_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.transaction_add_hole(
            transaction_token,
            face=payload["face"],
            x=payload["x"],
            y=payload["y"],
            diameter=payload["diameter"],
            through=payload.get("through", True),
        )

    def draft_transaction_add_counterbore(self, transaction_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.transaction_add_counterbore(
            transaction_token,
            face=payload["face"],
            x=payload["x"],
            y=payload["y"],
            diameter=payload["diameter"],
            depth=payload["depth"],
        )

    def draft_transaction_add_slot(self, transaction_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.transaction_add_slot(
            transaction_token,
            face=payload["face"],
            x=payload["x"],
            y=payload["y"],
            length=payload["length"],
            width=payload["width"],
            angle=payload.get("angle", 0.0),
        )

    def draft_transaction_add_raised_wall(self, transaction_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.transaction_add_raised_wall(
            transaction_token,
            face=payload["face"],
            x=payload["x"],
            y=payload["y"],
            length=payload["length"],
            width=payload["width"],
            height=payload["height"],
        )

    def draft_transaction_add_louver_pattern(self, transaction_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.transaction_add_louver_pattern(
            transaction_token,
            face=payload["face"],
            count=payload["count"],
            pitch=payload["pitch"],
            x=payload["x"],
            y=payload["y"],
            width=payload["width"],
            height=payload["height"],
            angle=payload.get("angle", 0.0),
        )

    def draft_transaction_mirror_features(self, transaction_token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.drafts.transaction_mirror_features(
            transaction_token,
            source_face=payload["source_face"],
            target_face=payload["target_face"],
        )

    def draft_transaction_measure(self, transaction_token: str) -> dict[str, Any]:
        return self.drafts.transaction_measure(transaction_token)

    def draft_transaction_preview(self, transaction_token: str) -> dict[str, Any]:
        return self.drafts.transaction_preview(transaction_token)

    def draft_transaction_accept(self, transaction_token: str) -> dict[str, Any]:
        payload = self.drafts.accept_transaction(transaction_token)
        return self._with_source_loop_metadata(payload)

    def draft_transaction_discard(self, transaction_token: str) -> dict[str, Any]:
        return self.drafts.discard_transaction(transaction_token)

    def _part_payload(self, definition: PartDefinition, occurrences: list[dict[str, Any]], *, default_visible: bool) -> dict[str, Any]:
        artifact = self._artifact(definition)
        source_format = artifact.source_format if artifact is not None else None
        artifact_identity = self._artifact_identity_payload(definition, artifact) if artifact is not None else {}
        artifact_path = artifact_identity.get("artifact_path")
        direct_stl_path = (
            _relative_path(artifact.direct_stl_path, self.project_root)
            if artifact is not None and artifact.direct_stl_path is not None
            else None
        )
        geometry = geometry_for_artifact(source_format).to_payload()
        return {
            "id": definition.id,
            "module_id": definition.module_id,
            "version": getattr(definition, "version", ""),
            "family": getattr(definition, "family", "") or definition.module_id,
            "assembly_ids": list(getattr(definition, "assembly_ids", ())),
            "compatible_versions": list(getattr(definition, "compatible_versions", ())),
            "filename": definition.filename,
            "role": str(definition.role),
            "material": definition.material,
            "mass_kg": getattr(definition, "mass_kg", None),
            "center_of_mass_mm": getattr(definition, "center_of_mass_mm", None),
            "inertia_kg_m2": getattr(definition, "inertia_kg_m2", None),
            "mass_source": getattr(definition, "mass_source", "unset"),
            "metadata_status": str(getattr(definition, "metadata_status", "todo")),
            "metadata_notes": getattr(definition, "metadata_notes", ""),
            "is_printable": definition.is_printable,
            "artifact_format": source_format,
            "artifact_path": artifact_path,
            "source_step_path": artifact_identity.get("source_step_path"),
            "display_stl_cache_path": artifact_identity.get("display_stl_cache_path"),
            "artifact_mtime_ns": artifact_identity.get("artifact_mtime_ns"),
            "artifact_size": artifact_identity.get("artifact_size"),
            "artifact_hash": artifact_identity.get("artifact_hash"),
            "artifact_identity": artifact_identity.get("artifact_identity"),
            "direct_stl_path": direct_stl_path,
            "source_kind": geometry["source_kind"],
            "geometry_authority": geometry["geometry_authority"],
            "quality_label": geometry["quality_label"],
            "capabilities": geometry["capabilities"],
            "warnings": geometry["warnings"],
            "model_url": _cache_busted_url(f"/api/parts/{definition.id}/model", artifact_identity),
            "source_url": f"/api/parts/{definition.id}/source",
            "snap_features_url": _cache_busted_url(f"/api/parts/{definition.id}/snap-features", artifact_identity),
            "occurrences": occurrences or [self._identity_occurrence(definition.id)],
            "in_assembly": bool(occurrences),
            "default_visible": default_visible,
        }

    def _artifact_identity_payload(self, definition: PartDefinition, artifact: Artifact) -> dict[str, Any]:
        identity = _file_identity(artifact.path, self.project_root)
        display_path: Path | None = None
        if artifact.source_format == "step":
            display_path = self._cached_stl_path(artifact.path)
        elif artifact.source_format == "stl":
            display_path = artifact.path
        identity.update(
            {
                "source_step_path": _relative_path(artifact.path, self.project_root) if artifact.source_format == "step" else None,
                "display_stl_cache_path": _relative_path(display_path, self.project_root) if display_path is not None else None,
                "component_id": definition.id,
                "source_format": artifact.source_format,
            }
        )
        return identity

    @staticmethod
    def _rendered_artifact_summary(part: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "id",
            "artifact_format",
            "artifact_path",
            "source_step_path",
            "display_stl_cache_path",
            "artifact_mtime_ns",
            "artifact_size",
            "artifact_hash",
            "artifact_identity",
            "model_url",
            "snap_features_url",
        )
        return {key: part.get(key) for key in keys}

    def _part_source_context_payload(self, definition: PartDefinition) -> dict[str, Any]:
        try:
            context = self.source_context(definition.id)
        except ArtifactNotFoundError:
            return {
                "available": False,
            }

        return {
            "available": True,
            "symbol": context["symbol"],
            "file_path": context["file_path"],
            "relative_file_path": context["relative_file_path"],
        }

    def _preview_command_context(self, component_id: str) -> PreviewCommandContext:
        context = self.preview_context(component_id)
        dimensions = context.get("source_measurements")
        if not isinstance(dimensions, dict):
            dimensions = {}
        return PreviewCommandContext(
            part_id=component_id,
            length=_maybe_float(dimensions.get("length_mm")),
            width=_maybe_float(dimensions.get("width_mm")),
            thickness=_maybe_float(dimensions.get("height_mm")),
        )

    def _preview_snap_feature_summary(self, component_id: str) -> dict[str, Any]:
        payload = self.snap_features(component_id)
        return {
            "available": True,
            "source_format": payload.get("source_format"),
            "count": len(payload.get("features", [])),
            "warnings": payload.get("warnings", []),
            "feature_quality": payload.get("geometry_authority"),
        }

    def _preview_bounds_payload(self, component_id: str) -> dict[str, Any] | None:
        artifact = self._artifact(self._definition(component_id))
        if artifact is None:
            return None

        display_path, _source_format = self.model_path(component_id)
        bounds = self._mesh_bounds(display_path)
        if bounds is None:
            return None

        return {
            "artifact_path": _relative_path(display_path, self.project_root),
            "source_format": "stl",
            **bounds,
        }

    def _measurement_summary(
        self,
        bounds_payload: dict[str, Any] | None,
        authority: str,
        source: str,
    ) -> dict[str, Any] | None:
        if bounds_payload is None:
            return None
        size = bounds_payload.get("size")
        if not isinstance(size, list) or len(size) != 3:
            return None
        return {
            "length_mm": float(size[0]),
            "width_mm": float(size[1]),
            "height_mm": float(size[2]),
            "authority": authority,
            "source": source,
        }

    def _project_frame_payload(self) -> dict[str, Any]:
        return {
            "units": "mm",
            "origin_mm": [0.0, 0.0, 0.0],
            "axes": {
                "x_positive": "right",
                "y_positive": "front",
                "z_positive": "top",
            },
        }

    def _local_frame_payload(self, occurrences: Any) -> dict[str, Any]:
        occurrence = occurrences[0] if isinstance(occurrences, list) and occurrences else {}
        return {
            "units": "mm",
            "origin_mm": occurrence.get("location", [0.0, 0.0, 0.0]) if isinstance(occurrence, dict) else [0.0, 0.0, 0.0],
            "rotation_deg": occurrence.get("rotation", [0.0, 0.0, 0.0]) if isinstance(occurrence, dict) else [0.0, 0.0, 0.0],
            "axes": {
                "x_positive": "part-local +X",
                "y_positive": "part-local +Y",
                "z_positive": "part-local +Z",
            },
        }

    def _mating_contracts_payload(self) -> dict[str, Any]:
        path = self.project.docs.part_interfaces
        return {
            "available": path.exists(),
            "relative_path": _relative_path(path, self.project_root),
            "summary": "Project mating-interface contracts live in the project part-interfaces document.",
        }

    def _draft_dimension_summary(self, dimensions: Any) -> dict[str, Any] | None:
        if not isinstance(dimensions, dict):
            return None
        try:
            length = float(dimensions["length"])
            width = float(dimensions["width"])
            height = float(dimensions["height"])
        except (KeyError, TypeError, ValueError):
            return None
        return {
            "length_mm": length,
            "width_mm": width,
            "height_mm": height,
            "authority": "step_kernel",
            "source": "preview",
        }

    def _draft_preview_facts(self, dimensions: Any, feature_count: int) -> list[str]:
        facts: list[str] = []
        summary = self._draft_dimension_summary(dimensions)
        if summary is not None:
            facts.append(
                "Draft dimensions: "
                f"{summary['length_mm']:g} x {summary['width_mm']:g} x {summary['height_mm']:g} mm"
            )
        facts.append(f"Draft features: {feature_count}")
        return facts

    def _mesh_bounds(self, mesh_path: Path) -> dict[str, Any] | None:
        if mesh_path.suffix.lower() != ".stl":
            return None

        try:
            from build123d import import_stl
        except Exception as exc:  # pragma: no cover - depends on local CAD install
            raise ConversionUnavailableError(
                "Mesh bounds require build123d/OCP. Install project dependencies or configure the CAD environment."
            ) from exc

        try:
            shape = import_stl(mesh_path)
            bbox = shape.bounding_box()
        except Exception:
            return None

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

    def _transaction_preview_stl_path(self, transaction_token: str) -> Path:
        return self.viewer_cache_dir / "draft-transactions" / transaction_token / "preview.stl"

    def _source_loop_commands(self, transaction_payload: dict[str, Any]) -> list[str]:
        token = transaction_payload.get("transaction_token", "")
        part_id = str(transaction_payload.get("part_id") or transaction_payload.get("draft", {}).get("part_id") or "")
        commands = [f"flow validate run panel-basic --draft-transaction {token}"]
        if token and part_id:
            commands.extend(
                [
                    f"flow cad build --part {part_id}",
                    f"flow validate run panel-basic --part {part_id} --draft-transaction {token}",
                ]
            )
        return commands

    def _with_source_loop_metadata(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload["source_loop_commands"] = self._source_loop_commands(payload)
        source_patch_path = payload.get("source_patch_path")
        if isinstance(source_patch_path, str):
            patch_path = Path(source_patch_path)
            if patch_path.exists() and patch_path.is_relative_to(self.project.paths.local_state):
                payload["source_patch_preview"] = patch_path.read_text(encoding="utf-8")[:4000]
        return payload

    def _artifact(self, definition: PartDefinition) -> Artifact | None:
        export_subdir = definition_export_subdir(definition)
        step_path = self.exports_dir / "step" / export_subdir / definition.filename
        stl_path = self.exports_dir / "stl" / export_subdir / f"{Path(definition.filename).stem}.stl"
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
        assembly_ids = self._viewer_assembly_ids()
        if not self._assembly_supports_assembly_id():
            assembly_ids = [None]

        seen: set[tuple[str, str | None, str]] = set()
        for assembly_id in assembly_ids:
            try:
                placements = self.project.get_assembly_placements(
                    self.params,
                    include_references=True,
                    assembly_id=assembly_id,
                )
            except ValueError:
                continue
            for placement in placements:
                part_key = placement["part_key"]
                occurrence_name = placement["name"]
                dedupe_key = (part_key, assembly_id, occurrence_name)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                payload = {
                    "name": f"{assembly_id}:{occurrence_name}" if assembly_id else occurrence_name,
                    "location": _as_float_tuple(placement["location"]),
                    "rotation": _as_float_tuple(placement["rotation"]),
                }
                if assembly_id:
                    payload["assembly_id"] = assembly_id
                placement_map.setdefault(part_key, []).append(payload)
        return placement_map

    def _default_visible_part_keys(self) -> set[str]:
        return {
            placement["part_key"]
            for placement in self.project.get_assembly_placements(
                self.params,
                include_references=False,
                assembly_id=self._active_assembly_id(),
            )
        }

    def _viewer_assembly_ids(self) -> list[str | None]:
        active_assembly_id = self._active_assembly_id()
        assembly_ids = [
            str(assembly_id)
            for definition in self.project.iter_part_definitions()
            for assembly_id in tuple(getattr(definition, "assembly_ids", ()) or ())
            if assembly_id
        ]
        ordered: list[str | None] = []
        if active_assembly_id:
            ordered.append(active_assembly_id)
        for assembly_id in sorted(set(assembly_ids)):
            if assembly_id not in ordered:
                ordered.append(assembly_id)
        return ordered or [None]

    def _assembly_supports_assembly_id(self) -> bool:
        signature = inspect.signature(self.project.assembly_placements)
        return (
            "assembly_id" in signature.parameters
            or any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
        )

    def _active_version(self, default_visible_ids: set[str]) -> str | None:
        assembly_version = str(getattr(self.project.assembly_definition, "version", "") or "")
        if assembly_version:
            return assembly_version

        definitions = list(self.project.iter_part_definitions())
        for definition in definitions:
            if definition.id in default_visible_ids:
                version = str(getattr(definition, "version", "") or "")
                if version:
                    return version
        for definition in definitions:
            version = str(getattr(definition, "version", "") or "")
            if version:
                return version
        return None

    def _active_assembly_id(self) -> str | None:
        assembly_ids = tuple(getattr(self.project.assembly_definition, "assembly_ids", ()) or ())
        return str(assembly_ids[0]) if assembly_ids else None

    @staticmethod
    def _versions(parts: list[dict[str, Any]], active_version: str | None) -> list[str]:
        versions = sorted({str(part.get("version") or "") for part in parts if part.get("version")})
        if active_version and active_version in versions:
            versions.remove(active_version)
            return [active_version, *versions]
        return versions

    @staticmethod
    def _identity_occurrence(component_id: str) -> dict[str, Any]:
        return {
            "name": component_id,
            "location": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
        }


def _safe_import_filename(filename: str) -> Path:
    name = Path(filename or "import.step").name.strip()
    if not name:
        name = "import.step"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    if name in {".", ".."}:
        name = "import.step"
    return Path(name)
