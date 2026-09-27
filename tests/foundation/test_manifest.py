from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from flow_cad.sdk import (
    ManifestError,
    MassProperties,
    PartRole,
    PartStatus,
    PrintSpec,
    ReleaseHookKind,
    dump_manifest,
    load_manifest,
    loads_manifest,
)


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


def test_manifest_round_trips_explicit_project_parameter_provider() -> None:
    manifest = loads_manifest(
        _manifest_yaml().replace(
            "python_package: sample\n",
            "python_package: sample\nparameter_provider: sample.params:ProjectParams\n",
        )
    )

    assert manifest.parameter_provider == "sample.params:ProjectParams"
    assert loads_manifest(dump_manifest(manifest)) == manifest


def test_manifest_round_trips_project_owned_release_hooks() -> None:
    manifest = loads_manifest(
        _manifest_yaml().replace(
            "parts:\n",
            """release_hooks:
  - key: focused
    kind: validator
    provider: sample.validators.release:validate_focused
    timeout_seconds: 12.5
  - key: assembly_clearance
    kind: interference
    provider: sample.validators.release:validate_interference
parts:
""",
        )
    )

    assert [hook.kind for hook in manifest.release_hooks] == [
        ReleaseHookKind.VALIDATOR,
        ReleaseHookKind.INTERFERENCE,
    ]
    assert manifest.release_hooks[0].timeout_seconds == 12.5
    assert manifest.release_hooks[1].timeout_seconds == 30.0
    assert loads_manifest(dump_manifest(manifest)) == manifest


@pytest.mark.parametrize("timeout", [0, -1, 181])
def test_manifest_rejects_release_hook_timeouts_outside_gate_bounds(timeout: int) -> None:
    invalid = _manifest_yaml().replace(
        "parts:\n",
        f"""release_hooks:
  - key: focused
    kind: validator
    provider: sample.validators.release:validate_focused
    timeout_seconds: {timeout}
parts:
""",
    )

    with pytest.raises(ManifestError, match="must be greater than 0 and at most 180"):
        loads_manifest(invalid, source="release-hooks.yaml")


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


def test_stl_artifact_round_trips_tessellation_tolerances() -> None:
    source = _manifest_yaml().replace(
        "      step: exports/step/sample.step",
        """      step: exports/step/sample.step
      stl:
        path: exports/stl/sample.stl
        linear_tolerance: 0.2
        angular_tolerance: 0.25""",
    )

    manifest = loads_manifest(source, source="tessellation.yaml")
    stl = next(artifact for artifact in manifest.parts[0].artifacts if artifact.kind == "stl")

    assert stl.linear_tolerance == 0.2
    assert stl.angular_tolerance == 0.25
    assert loads_manifest(dump_manifest(manifest)) == manifest


@pytest.mark.parametrize("kind", ["step", "glb"])
def test_manifest_rejects_tessellation_tolerances_for_non_stl_artifacts(kind: str) -> None:
    invalid = _manifest_yaml().replace(
        "      step: exports/step/sample.step",
        f"""      step:
        path: exports/step/sample.step
        linear_tolerance: 0.2""",
    )
    if kind == "glb":
        invalid = invalid.replace("      step:", "      glb:", 1)

    with pytest.raises(ManifestError, match="supported only for STL"):
        loads_manifest(invalid, source="tessellation.yaml")


def test_manifest_round_trips_project_owned_print_and_physical_metadata() -> None:
    source = _manifest_yaml().replace(
        "    artifacts:\n",
        """    family: compute
    version: b3_v2
    compatible_versions: [b3_v1]
    material: PETG
    print:
      shell_count: 4
      infill_density: 0.4
    mass_properties:
      mass_kg: 0.125
      center_of_mass_mm: [1, 2, 3]
      inertia_kg_m2: [1, 2, 3, 4, 5, 6]
      source: measured
      status: complete
      notes: Bench measurement
    artifacts:
""",
    )

    manifest = loads_manifest(source, source="metadata.yaml")
    part = manifest.parts[0]

    assert part.family == "compute"
    assert part.version == "b3_v2"
    assert part.compatible_versions == ("b3_v1",)
    assert part.print == PrintSpec(shell_count=4, infill_density=0.4)
    assert part.mass_properties == MassProperties(
        mass_kg=0.125,
        center_of_mass_mm=(1.0, 2.0, 3.0),
        inertia_kg_m2=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
        source="measured",
        status="complete",
        notes="Bench measurement",
    )
    assert loads_manifest(dump_manifest(manifest)) == manifest


@pytest.mark.parametrize(
    ("needle", "replacement", "message"),
    [
        ("shell_count: 4", "shell_count: 0", "must be a positive integer"),
        ("infill_density: 0.4", "infill_density: 1.4", "must be between 0 and 1"),
        ("mass_kg: 0.125", "mass_kg: -1", "must be non-negative"),
    ],
)
def test_manifest_rejects_invalid_project_owned_metadata(
    needle: str, replacement: str, message: str
) -> None:
    source = _manifest_yaml().replace(
        "    artifacts:\n",
        """    print:
      shell_count: 4
      infill_density: 0.4
    mass_properties:
      mass_kg: 0.125
    artifacts:
""",
    )

    with pytest.raises(ManifestError, match=message):
        loads_manifest(source.replace(needle, replacement), source="metadata.yaml")


def test_manifest_round_trips_historical_assembly_artifacts() -> None:
    source = _manifest_yaml().replace(
        "  active:\n    occurrences:",
        """  active:
    artifacts:
      step:
        path: exports/step/sample_assembly.step
        sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        byte_count: 456
    occurrences:""",
    )

    manifest = loads_manifest(source, source="assembly-artifact.yaml")

    assert manifest.assemblies[0].artifacts[0].path == "exports/step/sample_assembly.step"
    assert loads_manifest(dump_manifest(manifest)) == manifest


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
