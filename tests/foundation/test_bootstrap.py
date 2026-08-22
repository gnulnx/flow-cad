from __future__ import annotations

from pathlib import Path

from flow_cad.bootstrap import PROJECT_MANIFEST, init_project, normalize_python_package
from flow_cad.sdk import load_manifest


def test_replacement_init_creates_only_project_owned_layout(tmp_path: Path) -> None:
    result = init_project(tmp_path / "flow_b2")
    root = result.root

    expected_files = {
        "AGENTS.md",
        PROJECT_MANIFEST,
        "flow_b2/__init__.py",
        "flow_b2/params.py",
        "flow_b2/parts/__init__.py",
        "flow_b2/validators/__init__.py",
        "docs/PART_INTERFACES.md",
        "docs/PRINT_MANIFEST.md",
        ".flow/.gitignore",
    }
    actual_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }
    assert actual_files == expected_files
    assert (root / "tests").is_dir()
    assert not (root / "flow").exists()
    assert not (root / "exports").exists()
    assert not (root / "reports").exists()
    assert not (root / ".flow" / "config.toml").exists()

    manifest = load_manifest(root / PROJECT_MANIFEST)
    assert manifest.project_id == "flow_b2"
    assert manifest.python_package == "flow_b2"
    assert manifest.parts == ()
    assert manifest.assemblies[0].key == "active"


def test_replacement_init_is_idempotent_and_preserves_project_source(tmp_path: Path) -> None:
    root = tmp_path / "custom-project"
    first = init_project(root)
    params_path = root / "custom_project" / "params.py"
    params_path.write_text("# user-owned parameters\n", encoding="utf-8")

    second = init_project(root)

    assert first.changed_paths
    assert second.changed_paths == ()
    assert params_path.read_text(encoding="utf-8") == "# user-owned parameters\n"
    assert second.python_package == "custom_project"


def test_python_package_normalization_is_deterministic() -> None:
    assert normalize_python_package("Flow-B2 CAD") == "flow_b2_cad"
    assert normalize_python_package("2026 robot") == "flow_2026_robot"
