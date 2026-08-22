from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from flow_cad.sdk import ManifestError, PartRole, PartStatus, dump_manifest, load_manifest, loads_manifest


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "projects"


@pytest.mark.parametrize("fixture_name", ["minimal_alpha", "minimal_beta"])
def test_fixture_manifest_round_trips_without_losing_typed_metadata(fixture_name: str) -> None:
    source = FIXTURE_ROOT / fixture_name / "flowcad.project.yaml"
    manifest = load_manifest(source)

    reloaded = loads_manifest(dump_manifest(manifest), source=f"roundtrip:{fixture_name}")

    assert reloaded == manifest
    assert all(isinstance(part.uuid, UUID) for part in manifest.parts)
    assert all(isinstance(part.role, PartRole) for part in manifest.parts)
    assert all(isinstance(part.status, PartStatus) for part in manifest.parts)


def test_manifest_preserves_generator_reference_as_an_opaque_string() -> None:
    manifest = loads_manifest(_manifest_yaml(generator="not an importable module reference"))

    assert manifest.parts[0].generator == "not an importable module reference"


def test_manifest_requires_exact_schema_version() -> None:
    with pytest.raises(ManifestError, match=r"example.yaml:schema_version: expected integer 1"):
        loads_manifest(_manifest_yaml().replace("schema_version: 1", "schema_version: 2"), source="example.yaml")


def test_manifest_rejects_unknown_nested_keys_with_schema_location() -> None:
    invalid = _manifest_yaml().replace("    status: active", "    status: active\n    surprise: value")

    with pytest.raises(ManifestError) as caught:
        loads_manifest(invalid, source="strict.yaml")

    assert "strict.yaml:parts[0]: unknown keys: surprise" in str(caught.value)


def test_manifest_rejects_duplicate_keys_and_aliases_across_parts() -> None:
    invalid = _manifest_yaml().replace(
        "\nassemblies:",
        """
  - uuid: 44444444-4444-4444-8444-444444444444
    key: replacement
    aliases: [sample_part]
    generator: ignored
    role: reference
    status: active
    artifacts: {}

assemblies:""",
    )

    with pytest.raises(ManifestError, match=r"part key or alias 'sample_part' already used"):
        loads_manifest(invalid, source="identity.yaml")


def test_manifest_rejects_occurrence_for_unknown_part_uuid() -> None:
    invalid = _manifest_yaml().replace(
        "11111111-1111-4111-8111-111111111111\n        translation_mm",
        "99999999-9999-4999-8999-999999999999\n        translation_mm",
    )

    with pytest.raises(ManifestError) as caught:
        loads_manifest(invalid, source="references.yaml")

    assert "references.yaml:assemblies.active.occurrences[0].part_uuid" in str(caught.value)
    assert "unknown part UUID" in str(caught.value)


def test_manifest_requires_finite_three_component_transforms() -> None:
    invalid = _manifest_yaml().replace("translation_mm: [0, 0, 0]", "translation_mm: [0, 0]")

    with pytest.raises(ManifestError, match="must contain exactly three numbers"):
        loads_manifest(invalid, source="transform.yaml")


def test_manifest_uses_safe_yaml_loading() -> None:
    unsafe = "!!python/object/apply:builtins.print ['unsafe']"

    with pytest.raises(ManifestError) as caught:
        loads_manifest(unsafe, source="unsafe.yaml")

    assert "unsafe.yaml:yaml" in str(caught.value)


def test_artifact_metadata_is_typed_and_paths_are_project_relative() -> None:
    manifest = load_manifest(FIXTURE_ROOT / "minimal_alpha" / "flowcad.project.yaml")
    stl = next(artifact for artifact in manifest.parts[0].artifacts if artifact.kind == "stl")

    assert stl.path == "exports/stl/alpha_panel.stl"
    assert stl.sha256 == "a" * 64
    assert stl.byte_count == 123

    invalid = _manifest_yaml().replace("exports/step/sample.step", "../outside.step")
    with pytest.raises(ManifestError, match="must be a project-relative path"):
        loads_manifest(invalid, source="artifact.yaml")


def _manifest_yaml(*, generator: str = "sample.generators:make_part") -> str:
    return f"""schema_version: 1
project_id: sample
python_package: sample
parts:
  - uuid: 11111111-1111-4111-8111-111111111111
    key: sample_part
    aliases: []
    generator: {generator}
    role: printable
    status: active
    artifacts:
      step: exports/step/sample.step
assemblies:
  active:
    occurrences:
      - id: sample_part_main
        part_uuid: 11111111-1111-4111-8111-111111111111
        translation_mm: [0, 0, 0]
        rotation_deg: [0, 0, 0]
"""
