"""Strict YAML serialization for the geometry-free public manifest contract."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn
from uuid import UUID

import yaml

from .models import (
    ArtifactSpec,
    AssemblyOccurrence,
    AssemblySpec,
    MassProperties,
    ManifestPart,
    PartRole,
    PartStatus,
    PrintSpec,
    ProjectManifest,
    Vector3,
)


SCHEMA_VERSION = 1
_PYTHON_PACKAGE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class ManifestError(ValueError):
    """A manifest error tied to both a source and a schema location."""

    def __init__(self, source: str | Path, location: str, message: str):
        self.source = str(source)
        self.location = location
        self.message = message
        super().__init__(f"{self.source}:{self.location}: {self.message}")


def load_manifest(path: str | Path) -> ProjectManifest:
    """Load a manifest without importing its generator modules or CAD libraries."""

    manifest_path = Path(path)
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ManifestError(manifest_path, "root", f"could not read manifest: {exc}") from exc
    return loads_manifest(text, source=manifest_path)


def loads_manifest(text: str, *, source: str | Path = "<manifest>") -> ProjectManifest:
    """Parse manifest YAML using only :func:`yaml.safe_load`."""

    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = "yaml"
        if mark is not None:
            location = f"yaml line {mark.line + 1}, column {mark.column + 1}"
        raise ManifestError(source, location, str(exc).splitlines()[0]) from exc
    return _parse_project(raw, source)


def dump_manifest(manifest: ProjectManifest) -> str:
    """Serialize a typed manifest deterministically as safe YAML."""

    if manifest.schema_version != SCHEMA_VERSION:
        raise ManifestError("<model>", "schema_version", f"expected {SCHEMA_VERSION}")
    payload: dict[str, Any] = {
        "schema_version": manifest.schema_version,
        "project_id": manifest.project_id,
        "python_package": manifest.python_package,
        "parts": [_dump_part(part) for part in manifest.parts],
        "assemblies": {
            assembly.key: {
                "occurrences": [_dump_occurrence(occurrence) for occurrence in assembly.occurrences]
            }
            for assembly in manifest.assemblies
        },
    }
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def _parse_project(raw: Any, source: str | Path) -> ProjectManifest:
    data = _mapping(raw, source, "root")
    _keys(
        data,
        source,
        "root",
        required={"schema_version", "project_id", "python_package", "parts", "assemblies"},
        allowed={"schema_version", "project_id", "python_package", "parts", "assemblies"},
    )
    schema_version = data["schema_version"]
    if type(schema_version) is not int or schema_version != SCHEMA_VERSION:
        _fail(source, "schema_version", f"expected integer {SCHEMA_VERSION}")

    project_id = _nonempty_string(data["project_id"], source, "project_id")
    python_package = _nonempty_string(data["python_package"], source, "python_package")
    if _PYTHON_PACKAGE_RE.fullmatch(python_package) is None:
        _fail(source, "python_package", "must be a dotted Python package name")

    raw_parts = _sequence(data["parts"], source, "parts")
    parts = tuple(_parse_part(value, source, f"parts[{index}]") for index, value in enumerate(raw_parts))
    _validate_part_identity(parts, source)

    raw_assemblies = _mapping(data["assemblies"], source, "assemblies")
    assemblies = tuple(
        _parse_assembly(key, value, source, f"assemblies.{key}")
        for key, value in raw_assemblies.items()
    )
    _validate_occurrences(assemblies, parts, source)

    return ProjectManifest(
        schema_version=schema_version,
        project_id=project_id,
        python_package=python_package,
        parts=parts,
        assemblies=assemblies,
    )


def _parse_part(raw: Any, source: str | Path, location: str) -> ManifestPart:
    data = _mapping(raw, source, location)
    _keys(
        data,
        source,
        location,
        required={"uuid", "key", "aliases", "generator", "role", "status", "artifacts"},
        allowed={
            "uuid",
            "key",
            "aliases",
            "generator",
            "role",
            "status",
            "artifacts",
            "material",
            "family",
            "version",
            "compatible_versions",
            "print",
            "mass_properties",
        },
    )
    part_uuid = _uuid(data["uuid"], source, f"{location}.uuid")
    key = _identifier(data["key"], source, f"{location}.key")
    generator = _nonempty_string(data["generator"], source, f"{location}.generator")

    raw_aliases = _sequence(data["aliases"], source, f"{location}.aliases")
    aliases = tuple(
        _identifier(alias, source, f"{location}.aliases[{index}]")
        for index, alias in enumerate(raw_aliases)
    )
    if len(set(aliases)) != len(aliases):
        _fail(source, f"{location}.aliases", "contains duplicate aliases")
    if key in aliases:
        _fail(source, f"{location}.aliases", "must not repeat the current part key")

    role = _enum(PartRole, data["role"], source, f"{location}.role")
    status = _enum(PartStatus, data["status"], source, f"{location}.status")
    material = data.get("material")
    if material is not None:
        material = _nonempty_string(material, source, f"{location}.material")
    family = data.get("family")
    if family is not None:
        family = _identifier(family, source, f"{location}.family")
    version = data.get("version")
    if version is not None:
        version = _identifier(version, source, f"{location}.version")
    raw_compatible_versions = _sequence(
        data.get("compatible_versions", ()), source, f"{location}.compatible_versions"
    )
    compatible_versions = tuple(
        _identifier(value, source, f"{location}.compatible_versions[{index}]")
        for index, value in enumerate(raw_compatible_versions)
    )
    if len(set(compatible_versions)) != len(compatible_versions):
        _fail(source, f"{location}.compatible_versions", "contains duplicate versions")
    print_spec = None
    if "print" in data:
        print_spec = _parse_print_spec(data["print"], source, f"{location}.print")
    mass_properties = None
    if "mass_properties" in data:
        mass_properties = _parse_mass_properties(
            data["mass_properties"], source, f"{location}.mass_properties"
        )

    artifact_map = _mapping(data["artifacts"], source, f"{location}.artifacts")
    artifacts = tuple(
        _parse_artifact(kind, value, source, f"{location}.artifacts.{kind}")
        for kind, value in artifact_map.items()
    )
    return ManifestPart(
        uuid=part_uuid,
        key=key,
        aliases=aliases,
        generator=generator,
        role=role,
        status=status,
        artifacts=artifacts,
        material=material,
        family=family,
        version=version,
        compatible_versions=compatible_versions,
        print=print_spec,
        mass_properties=mass_properties,
    )


def _parse_print_spec(raw: Any, source: str | Path, location: str) -> PrintSpec:
    data = _mapping(raw, source, location)
    _keys(
        data,
        source,
        location,
        required={"shell_count", "infill_density"},
        allowed={"shell_count", "infill_density"},
    )
    shell_count = data["shell_count"]
    if type(shell_count) is not int or shell_count <= 0:
        _fail(source, f"{location}.shell_count", "must be a positive integer")
    infill_density = _finite_number(
        data["infill_density"], source, f"{location}.infill_density"
    )
    if not 0.0 <= infill_density <= 1.0:
        _fail(source, f"{location}.infill_density", "must be between 0 and 1")
    return PrintSpec(shell_count=shell_count, infill_density=infill_density)


def _parse_mass_properties(raw: Any, source: str | Path, location: str) -> MassProperties:
    data = _mapping(raw, source, location)
    _keys(
        data,
        source,
        location,
        required=set(),
        allowed={
            "mass_kg",
            "center_of_mass_mm",
            "inertia_kg_m2",
            "source",
            "status",
            "notes",
        },
    )
    mass_kg = None
    if "mass_kg" in data:
        mass_kg = _finite_number(data["mass_kg"], source, f"{location}.mass_kg")
        if mass_kg < 0.0:
            _fail(source, f"{location}.mass_kg", "must be non-negative")
    center_of_mass_mm = None
    if "center_of_mass_mm" in data:
        center_of_mass_mm = _vector3(
            data["center_of_mass_mm"], source, f"{location}.center_of_mass_mm"
        )
    inertia_kg_m2 = None
    if "inertia_kg_m2" in data:
        inertia_values = _sequence(
            data["inertia_kg_m2"], source, f"{location}.inertia_kg_m2"
        )
        if len(inertia_values) != 6:
            _fail(source, f"{location}.inertia_kg_m2", "must contain exactly six numbers")
        inertia_kg_m2 = tuple(
            _finite_number(value, source, f"{location}.inertia_kg_m2[{index}]")
            for index, value in enumerate(inertia_values)
        )
    source_name = _nonempty_string(data.get("source", "unset"), source, f"{location}.source")
    status = _identifier(data.get("status", "todo"), source, f"{location}.status")
    notes = data.get("notes", "")
    if not isinstance(notes, str):
        _fail(source, f"{location}.notes", "must be a string")
    return MassProperties(
        mass_kg=mass_kg,
        center_of_mass_mm=center_of_mass_mm,
        inertia_kg_m2=inertia_kg_m2,  # type: ignore[arg-type]
        source=source_name,
        status=status,
        notes=notes,
    )


def _parse_artifact(kind: Any, raw: Any, source: str | Path, location: str) -> ArtifactSpec:
    artifact_kind = _identifier(kind, source, location)
    if isinstance(raw, str):
        return ArtifactSpec(kind=artifact_kind, path=_relative_path(raw, source, location))

    data = _mapping(raw, source, location)
    _keys(data, source, location, required={"path"}, allowed={"path", "sha256", "byte_count"})
    digest = data.get("sha256")
    if digest is not None:
        digest = _nonempty_string(digest, source, f"{location}.sha256")
        if _SHA256_RE.fullmatch(digest) is None:
            _fail(source, f"{location}.sha256", "must contain exactly 64 hexadecimal characters")
        digest = digest.lower()
    byte_count = data.get("byte_count")
    if byte_count is not None and (type(byte_count) is not int or byte_count < 0):
        _fail(source, f"{location}.byte_count", "must be a non-negative integer")
    return ArtifactSpec(
        kind=artifact_kind,
        path=_relative_path(data["path"], source, f"{location}.path"),
        sha256=digest,
        byte_count=byte_count,
    )


def _parse_assembly(key: Any, raw: Any, source: str | Path, location: str) -> AssemblySpec:
    assembly_key = _identifier(key, source, "assemblies")
    data = _mapping(raw, source, location)
    _keys(data, source, location, required={"occurrences"}, allowed={"occurrences"})
    raw_occurrences = _sequence(data["occurrences"], source, f"{location}.occurrences")
    occurrences = tuple(
        _parse_occurrence(value, source, f"{location}.occurrences[{index}]")
        for index, value in enumerate(raw_occurrences)
    )
    occurrence_ids = [occurrence.id for occurrence in occurrences]
    if len(set(occurrence_ids)) != len(occurrence_ids):
        _fail(source, f"{location}.occurrences", "occurrence ids must be unique within an assembly")
    return AssemblySpec(key=assembly_key, occurrences=occurrences)


def _parse_occurrence(raw: Any, source: str | Path, location: str) -> AssemblyOccurrence:
    data = _mapping(raw, source, location)
    _keys(
        data,
        source,
        location,
        required={"id", "part_uuid", "translation_mm", "rotation_deg"},
        allowed={"id", "part_uuid", "translation_mm", "rotation_deg"},
    )
    return AssemblyOccurrence(
        id=_identifier(data["id"], source, f"{location}.id"),
        part_uuid=_uuid(data["part_uuid"], source, f"{location}.part_uuid"),
        translation_mm=_vector3(data["translation_mm"], source, f"{location}.translation_mm"),
        rotation_deg=_vector3(data["rotation_deg"], source, f"{location}.rotation_deg"),
    )


def _validate_part_identity(parts: tuple[ManifestPart, ...], source: str | Path) -> None:
    seen_uuids: dict[UUID, int] = {}
    seen_names: dict[str, str] = {}
    for index, part in enumerate(parts):
        if part.uuid in seen_uuids:
            _fail(
                source,
                f"parts[{index}].uuid",
                f"duplicates parts[{seen_uuids[part.uuid]}].uuid",
            )
        seen_uuids[part.uuid] = index
        for name, location in ((part.key, f"parts[{index}].key"), *(
            (alias, f"parts[{index}].aliases[{alias_index}]")
            for alias_index, alias in enumerate(part.aliases)
        )):
            previous = seen_names.get(name)
            if previous is not None:
                _fail(source, location, f"part key or alias {name!r} already used at {previous}")
            seen_names[name] = location


def _validate_occurrences(
    assemblies: tuple[AssemblySpec, ...],
    parts: tuple[ManifestPart, ...],
    source: str | Path,
) -> None:
    known_part_uuids = {part.uuid for part in parts}
    for assembly in assemblies:
        for index, occurrence in enumerate(assembly.occurrences):
            if occurrence.part_uuid not in known_part_uuids:
                _fail(
                    source,
                    f"assemblies.{assembly.key}.occurrences[{index}].part_uuid",
                    f"unknown part UUID {occurrence.part_uuid}",
                )


def _dump_part(part: ManifestPart) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "uuid": str(part.uuid),
        "key": part.key,
        "aliases": list(part.aliases),
        "generator": part.generator,
        "role": part.role.value,
        "status": part.status.value,
    }
    if part.material is not None:
        payload["material"] = part.material
    if part.family is not None:
        payload["family"] = part.family
    if part.version is not None:
        payload["version"] = part.version
    if part.compatible_versions:
        payload["compatible_versions"] = list(part.compatible_versions)
    if part.print is not None:
        payload["print"] = {
            "shell_count": part.print.shell_count,
            "infill_density": part.print.infill_density,
        }
    if part.mass_properties is not None:
        mass_properties: dict[str, Any] = {
            "source": part.mass_properties.source,
            "status": part.mass_properties.status,
            "notes": part.mass_properties.notes,
        }
        if part.mass_properties.mass_kg is not None:
            mass_properties["mass_kg"] = part.mass_properties.mass_kg
        if part.mass_properties.center_of_mass_mm is not None:
            mass_properties["center_of_mass_mm"] = list(
                part.mass_properties.center_of_mass_mm
            )
        if part.mass_properties.inertia_kg_m2 is not None:
            mass_properties["inertia_kg_m2"] = list(part.mass_properties.inertia_kg_m2)
        payload["mass_properties"] = mass_properties
    payload["artifacts"] = {artifact.kind: _dump_artifact(artifact) for artifact in part.artifacts}
    return payload


def _dump_artifact(artifact: ArtifactSpec) -> str | dict[str, Any]:
    if artifact.sha256 is None and artifact.byte_count is None:
        return artifact.path
    payload: dict[str, Any] = {"path": artifact.path}
    if artifact.sha256 is not None:
        payload["sha256"] = artifact.sha256
    if artifact.byte_count is not None:
        payload["byte_count"] = artifact.byte_count
    return payload


def _dump_occurrence(occurrence: AssemblyOccurrence) -> dict[str, Any]:
    return {
        "id": occurrence.id,
        "part_uuid": str(occurrence.part_uuid),
        "translation_mm": list(occurrence.translation_mm),
        "rotation_deg": list(occurrence.rotation_deg),
    }


def _mapping(value: Any, source: str | Path, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(source, location, "must be a mapping")
    for key in value:
        if not isinstance(key, str):
            _fail(source, location, "mapping keys must be strings")
    return value


def _sequence(value: Any, source: str | Path, location: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        _fail(source, location, "must be a sequence")
    return value


def _keys(
    data: Mapping[str, Any],
    source: str | Path,
    location: str,
    *,
    required: set[str],
    allowed: set[str],
) -> None:
    missing = sorted(required - set(data))
    if missing:
        _fail(source, location, f"missing required keys: {', '.join(missing)}")
    unknown = sorted(set(data) - allowed)
    if unknown:
        _fail(source, location, f"unknown keys: {', '.join(unknown)}")


def _nonempty_string(value: Any, source: str | Path, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(source, location, "must be a non-empty string")
    return value.strip()


def _identifier(value: Any, source: str | Path, location: str) -> str:
    identifier = _nonempty_string(value, source, location)
    if any(character.isspace() for character in identifier):
        _fail(source, location, "must not contain whitespace")
    return identifier


def _uuid(value: Any, source: str | Path, location: str) -> UUID:
    if not isinstance(value, str):
        _fail(source, location, "must be a UUID string")
    try:
        return UUID(value)
    except ValueError as exc:
        raise ManifestError(source, location, f"invalid UUID {value!r}") from exc


def _enum(enum_type: type[PartRole] | type[PartStatus], value: Any, source: str | Path, location: str):
    if not isinstance(value, str):
        _fail(source, location, "must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ManifestError(source, location, f"expected one of: {allowed}") from exc


def _relative_path(value: Any, source: str | Path, location: str) -> str:
    path_text = _nonempty_string(value, source, location)
    path = PurePosixPath(path_text)
    if path.is_absolute() or ".." in path.parts:
        _fail(source, location, "must be a project-relative path without '..'")
    return path.as_posix()


def _vector3(value: Any, source: str | Path, location: str) -> Vector3:
    values = _sequence(value, source, location)
    if len(values) != 3:
        _fail(source, location, "must contain exactly three numbers")
    vector: list[float] = []
    for index, component in enumerate(values):
        vector.append(_finite_number(component, source, f"{location}[{index}]"))
    return (vector[0], vector[1], vector[2])


def _finite_number(value: Any, source: str | Path, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail(source, location, "must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        _fail(source, location, "must be a finite number")
    return number


def _fail(source: str | Path, location: str, message: str) -> NoReturn:
    raise ManifestError(source, location, message)
