from __future__ import annotations

import importlib
import inspect
import shutil
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from build123d import Box
from build123d import Compound, Location

from flow_cad.core.metadata import PartDefinition, PartRole, definition_export_subdir


PROJECT_MANIFEST = "flowcad.project.yaml"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_SKILLS_DIR = PROJECT_ROOT / "skills"


class ProjectError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProjectPaths:
    exports: Path
    reports: Path
    local_state: Path
    cache: Path


@dataclass(frozen=True)
class ProjectDocs:
    print_manifest: Path
    part_interfaces: Path


@dataclass(frozen=True)
class FlowCadProject:
    root: Path
    project_id: str
    name: str
    params_factory: Callable[[], Any]
    part_definitions: Callable[..., Iterable[Any]]
    assembly_placements: Callable[..., Iterable[dict[str, Any]]]
    paths: ProjectPaths
    docs: ProjectDocs
    validators: dict[str, Callable[..., Any]]
    assembly_definition_factory: Callable[[], Any] | None = None
    source_wrapper_files: tuple[Path, ...] = ()

    def make_params(self) -> Any:
        return self.params_factory()

    def iter_part_definitions(self, *, include_references: bool = True) -> Iterable[Any]:
        return _call_with_supported_kwargs(self.part_definitions, include_references=include_references)

    def build_parts(self, params: Any) -> dict[str, object]:
        return {definition.id: definition.factory(params) for definition in self.iter_part_definitions()}

    def get_assembly_placements(
        self,
        params: Any,
        *,
        include_references: bool = False,
        assembly_id: str | None = None,
    ) -> Iterable[dict[str, Any]]:
        return _call_with_supported_kwargs(
            self.assembly_placements,
            params,
            include_references=include_references,
            assembly_id=assembly_id,
        )

    def get_assembly_occurrences(
        self,
        params: Any,
        parts: dict[str, object],
        *,
        include_references: bool = False,
        assembly_id: str | None = None,
    ) -> list[dict[str, Any]]:
        occurrences: list[dict[str, Any]] = []
        for placement in self.get_assembly_placements(
            params,
            include_references=include_references,
            assembly_id=assembly_id,
        ):
            name = placement["name"]
            part_key = placement["part_key"]
            location = placement["location"]
            rotation = placement.get("rotation", (0.0, 0.0, 0.0))
            occurrences.append(
                {
                    "name": name,
                    "part_key": part_key,
                    "location": location,
                    "rotation": rotation,
                    "shape": parts[part_key].moved(Location(location, rotation)),
                }
            )
        return occurrences

    def make_assembly(
        self,
        params: Any,
        parts: dict[str, object],
        *,
        include_references: bool = True,
        assembly_id: str | None = None,
    ) -> object:
        children = [
            occurrence["shape"]
            for occurrence in self.get_assembly_occurrences(
                params,
                parts,
                include_references=include_references,
                assembly_id=assembly_id,
            )
        ]
        return Compound(children=children, label=f"{self.project_id}_assembly")

    @property
    def assembly_definition(self) -> Any:
        if self.assembly_definition_factory is not None:
            return self.assembly_definition_factory()
        return PartDefinition(
            "assembly",
            "assembly",
            f"{self.project_id}_assembly.step",
            lambda _params: None,
            role=PartRole.INSPECTION,
            material="",
        )

    def expected_printable_export_relative_paths(self) -> set[Path]:
        paths: set[Path] = set()
        for definition in self.iter_part_definitions(include_references=False):
            if not definition.is_printable:
                continue
            stem = Path(definition.filename).stem
            export_subdir = definition_export_subdir(definition)
            paths.add(Path("step") / export_subdir / definition.filename)
            paths.add(Path("stl") / export_subdir / f"{stem}.stl")
            for view in ("front", "side", "top"):
                paths.add(Path("snapshots") / export_subdir / f"{stem}_{view}.svg")
        return paths

    def iter_validators(self) -> Iterable[tuple[str, Callable[..., Any]]]:
        yield from self.validators.items()


class ExampleParams:
    project_id = "flow_example"


def _make_example_block(_params: ExampleParams):
    return Box(20.0, 20.0, 10.0)


def _iter_example_part_definitions(*, include_references: bool = True) -> Iterable[PartDefinition]:
    _ = include_references
    yield PartDefinition("example_block", "example", "example_block.step", _make_example_block)


def _get_example_assembly_placements(_params: ExampleParams, *, include_references: bool = False) -> list[dict[str, Any]]:
    _ = include_references
    return [
        {
            "name": "example_block",
            "part_key": "example_block",
            "location": (0.0, 0.0, 0.0),
            "rotation": (0.0, 0.0, 0.0),
        }
    ]


def bundled_example_project(project_root: Path | None = None) -> FlowCadProject:
    root = (project_root or PROJECT_ROOT).resolve()
    return FlowCadProject(
        root=root,
        project_id="flow_example",
        name="Bundled Flow CAD Example",
        params_factory=ExampleParams,
        part_definitions=_iter_example_part_definitions,
        assembly_placements=_get_example_assembly_placements,
        assembly_definition_factory=None,
        paths=ProjectPaths(
            exports=root / "example" / "exports",
            reports=root / "example" / "reports",
            local_state=root / "example",
            cache=root / "example" / "registry.db",
        ),
        docs=ProjectDocs(
            print_manifest=root / "docs" / "PRINT_MANIFEST.md",
            part_interfaces=root / "docs" / "PART_INTERFACES.md",
        ),
        validators={},
    )


def find_project_manifest(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        manifest = candidate / PROJECT_MANIFEST
        if manifest.exists():
            return manifest
    return None


def load_project(start: Path | None = None, *, fallback_to_bundled: bool = True) -> FlowCadProject:
    manifest = find_project_manifest(start)
    if manifest is None:
        if fallback_to_bundled:
            return bundled_example_project(start or PROJECT_ROOT)
        raise ProjectError(f"No {PROJECT_MANIFEST} found from {start or Path.cwd()}")
    return load_project_manifest(manifest)


def load_project_manifest(path: Path) -> FlowCadProject:
    manifest = _read_simple_yaml(path)
    root = path.resolve().parent
    _require_manifest_key(manifest, "project_id", path)
    python_section = _section(manifest, "python")
    outputs = _section(manifest, "outputs")
    validators_section = manifest.get("validators", {})
    if not isinstance(validators_section, dict):
        raise ProjectError(f"`validators` section must be a mapping in {path}")

    source_root = root / str(python_section.get("source_root", "flow"))
    if source_root.exists():
        _ensure_sys_path(root)
        _clear_project_modules(source_root.name)

    params_factory = _load_symbol(_required_section_value(python_section, "params", path))
    part_definitions = _load_symbol(_required_section_value(python_section, "registry", path))
    assembly_placements = _load_symbol(_required_section_value(python_section, "assembly", path))
    assembly_definition_factory = (
        _load_symbol(str(python_section["assembly_definition"]))
        if python_section.get("assembly_definition")
        else None
    )
    validators = {
        name: _load_symbol(str(spec))
        for name, spec in validators_section.items()
    }
    local_state = root / str(outputs.get("local_state", ".flow"))
    registry_source = inspect.getsourcefile(part_definitions)

    return FlowCadProject(
        root=root,
        project_id=str(manifest["project_id"]),
        name=str(manifest.get("name", manifest["project_id"])),
        params_factory=params_factory,
        part_definitions=part_definitions,
        assembly_placements=assembly_placements,
        assembly_definition_factory=assembly_definition_factory,
        paths=ProjectPaths(
            exports=root / str(outputs.get("exports", "exports")),
            reports=root / str(outputs.get("reports", "reports")),
            local_state=local_state,
            cache=root / str(outputs.get("cache", local_state / "registry.db")),
        ),
        docs=_docs_from_manifest(root, manifest),
        validators=validators,
        source_wrapper_files=(Path(registry_source).resolve(),) if registry_source else (),
    )


def init_project(project_root: Path, *, force: bool = False) -> list[Path]:
    root = project_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    created_or_updated: list[Path] = []

    manifest = root / PROJECT_MANIFEST
    if not manifest.exists():
        _write_file(manifest, _default_manifest(root.name), created_or_updated)

    flow_dir = root / "flow"
    for directory in (
        flow_dir,
        flow_dir / "parts",
        flow_dir / "assemblies",
        flow_dir / "validators",
        root / "skills",
        root / ".flow",
        root / "docs",
        root / "exports",
        root / "reports",
        root / "tests",
    ):
        if not directory.exists():
            directory.mkdir(parents=True)
            created_or_updated.append(directory)

    starter_files = {
        flow_dir / "__init__.py": "",
        flow_dir / "parts" / "__init__.py": "",
        flow_dir / "assemblies" / "__init__.py": "",
        flow_dir / "validators" / "__init__.py": "",
        flow_dir / "params.py": _starter_params(root.name.replace(" ", "_").lower() or "flow_project"),
        flow_dir / "parts" / "example.py": _starter_part(),
        flow_dir / "assemblies" / "robot.py": _starter_assembly(),
        flow_dir / "validators" / "project.py": _starter_validator(),
        root / "docs" / "PRINT_MANIFEST.md": "# Print Manifest\n\nProject print intent lives here.\n",
        root / "docs" / "PART_INTERFACES.md": "# Part Interfaces\n\nProject mating-interface contracts live here.\n",
    }
    for path, content in starter_files.items():
        if path.exists() and not force:
            continue
        _write_file(path, content, created_or_updated)

    _copy_template_skills(root / "skills", created_or_updated, force=force)
    _ensure_gitignore(root / ".gitignore", [".flow/", "__pycache__/", "*.pyc"])
    created_or_updated.append(root / ".gitignore")
    return created_or_updated


def _call_with_supported_kwargs(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    signature = inspect.signature(func)
    if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return func(*args, **kwargs)
    supported = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return func(*args, **supported)


def _load_symbol(spec: str) -> Callable[..., Any]:
    module_name, sep, attr_name = spec.partition(":")
    if not sep or not module_name or not attr_name:
        raise ProjectError(f"Invalid Python entrypoint {spec!r}; expected module:attribute")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ProjectError(f"Could not import Python entrypoint module {module_name!r}: {exc}") from exc
    target: Any = module
    for part in attr_name.split("."):
        try:
            target = getattr(target, part)
        except AttributeError as exc:
            raise ProjectError(f"Could not resolve Python entrypoint {spec!r}: missing attribute {part!r}") from exc
    if not callable(target):
        raise ProjectError(f"Python entrypoint is not callable: {spec}")
    return target


def _ensure_sys_path(path: Path) -> None:
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)


def _clear_project_modules(package_name: str) -> None:
    for module_name in list(sys.modules):
        if module_name == package_name or module_name.startswith(f"{package_name}."):
            del sys.modules[module_name]


def _section(manifest: dict[str, Any], name: str) -> dict[str, Any]:
    value = manifest.get(name)
    if not isinstance(value, dict):
        raise ProjectError(f"Missing `{name}` section in project manifest")
    return value


def _require_manifest_key(manifest: dict[str, Any], key: str, path: Path) -> str:
    value = manifest.get(key)
    if value is None or value == "":
        raise ProjectError(f"Missing `{key}` in project manifest: {path}")
    return str(value)


def _required_section_value(section: dict[str, Any], key: str, path: Path) -> str:
    value = section.get(key)
    if value is None or value == "":
        raise ProjectError(f"Missing `{key}` entrypoint in project manifest: {path}")
    return str(value)


def _docs_from_manifest(root: Path, manifest: dict[str, Any]) -> ProjectDocs:
    docs = manifest.get("docs", {})
    if not isinstance(docs, dict):
        docs = {}
    return ProjectDocs(
        print_manifest=root / str(docs.get("print_manifest", "docs/PRINT_MANIFEST.md")),
        part_interfaces=root / str(docs.get("part_interfaces", "docs/PART_INTERFACES.md")),
    )


def _read_simple_yaml(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = {}
    current_section: dict[str, Any] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line:
            continue
        if line.startswith("  "):
            if current_section is None:
                raise ProjectError(f"Nested key without a section in {path}: {raw_line}")
            key, value = _parse_key_value(line.strip(), path)
            current_section[key] = value
            continue
        key, value = _parse_key_value(line, path)
        if value == "":
            section: dict[str, Any] = {}
            data[key] = section
            current_section = section
        else:
            data[key] = value
            current_section = None
    return data


def _parse_key_value(line: str, path: Path) -> tuple[str, str]:
    key, sep, value = line.partition(":")
    if not sep:
        raise ProjectError(f"Invalid manifest line in {path}: {line}")
    return key.strip(), value.strip().strip("'\"")


def _write_file(path: Path, content: str, changed: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    changed.append(path)


def _copy_template_skills(dest_root: Path, changed: list[Path], *, force: bool) -> None:
    if not TEMPLATE_SKILLS_DIR.exists():
        return

    for source in sorted(TEMPLATE_SKILLS_DIR.iterdir()):
        if not source.is_dir():
            continue
        dest = dest_root / source.name
        if dest.exists() and not force:
            continue
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        changed.append(dest)


def _ensure_gitignore(path: Path, entries: list[str]) -> None:
    existing = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    updated = existing[:]
    for entry in entries:
        if entry not in updated:
            updated.append(entry)
    path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def _default_manifest(project_id: str) -> str:
    normalized_id = project_id.replace(" ", "_").lower() or "flow_project"
    return f"""schema_version: 1
project_id: {normalized_id}
name: {project_id}

python:
  source_root: flow
  params: flow.params:ProjectParams
  registry: flow.assemblies.robot:iter_part_definitions
  assembly: flow.assemblies.robot:get_assembly_placements

outputs:
  exports: exports
  reports: reports
  local_state: .flow
  cache: .flow/registry.db

validators:
  project: flow.validators.project:validate_project

docs:
  print_manifest: docs/PRINT_MANIFEST.md
  part_interfaces: docs/PART_INTERFACES.md
"""


def _starter_params(project_id: str) -> str:
    return f"""from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectParams:
    project_id: str = "{project_id}"
"""


def _starter_part() -> str:
    return """from __future__ import annotations

from build123d import Box


def make_example_block(_params):
    return Box(20.0, 20.0, 10.0)
"""


def _starter_assembly() -> str:
    return """from __future__ import annotations

from flow_cad.core.metadata import PartDefinition
from flow.parts.example import make_example_block


PART_DEFINITIONS = (
    PartDefinition("example_block", "example", "example_block.step", make_example_block),
)


def iter_part_definitions(*, include_references: bool = True):
    yield from PART_DEFINITIONS


def get_assembly_placements(_params, *, include_references: bool = False):
    return [
        {
            "name": "example_block",
            "part_key": "example_block",
            "location": (0.0, 0.0, 0.0),
            "rotation": (0.0, 0.0, 0.0),
        }
    ]
"""


def _starter_validator() -> str:
    return """from __future__ import annotations


def validate_project(_project):
    return []
"""
