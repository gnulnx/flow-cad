from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import flow_cad.sdk as sdk


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "projects"


def test_public_sdk_surface_is_small_and_explicit() -> None:
    assert sdk.__all__ == [
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


def test_public_manifest_models_are_immutable() -> None:
    manifest = sdk.load_manifest(FIXTURE_ROOT / "minimal_alpha" / "flowcad.project.yaml")

    with pytest.raises(FrozenInstanceError):
        manifest.parts[0].key = "renamed"  # type: ignore[misc]


@pytest.mark.parametrize("fixture_name", ["minimal_alpha", "minimal_beta"])
def test_loading_fixture_is_metadata_only_in_a_clean_process(fixture_name: str) -> None:
    fixture = FIXTURE_ROOT / fixture_name
    manifest_path = fixture / "flowcad.project.yaml"
    env = os.environ.copy()
    python_path = [str(Path(__file__).parents[2] / "src"), str(fixture)]
    if env.get("PYTHONPATH"):
        python_path.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(python_path)
    script = f"""
import sys
from flow_cad.sdk import load_manifest

manifest = load_manifest({str(manifest_path)!r})
assert manifest.project_id == {fixture_name!r}
assert 'build123d' not in sys.modules
assert {fixture_name!r} not in sys.modules
assert not any(name.startswith({fixture_name + '.'!r}) for name in sys.modules)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
