from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest

from flow_cad.registry import LifecycleError, get_part, rename_part, retire_part, sync_project
from flow_cad.sdk import PartStatus, load_manifest


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "projects"


def _copy_fixture(tmp_path: Path, name: str = "minimal_alpha") -> Path:
    root = tmp_path / name
    shutil.copytree(FIXTURES / name, root)
    sync_project(root)
    return root


def test_rename_preserves_uuid_artifacts_occurrences_and_old_key_alias(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    before = load_manifest(root / "flowcad.project.yaml")

    started = time.perf_counter()
    result = rename_part(root, "alpha_panel", "alpha_mounting_panel")
    elapsed = time.perf_counter() - started
    after = load_manifest(root / "flowcad.project.yaml")

    assert result.changed
    assert elapsed < 1.0
    assert after.parts[0].uuid == before.parts[0].uuid
    assert after.parts[0].key == "alpha_mounting_panel"
    assert after.parts[0].aliases == ("alpha_panel", "original_alpha_panel")
    assert after.parts[0].artifacts == before.parts[0].artifacts
    assert after.assemblies == before.assemblies
    assert get_part(root, "alpha_panel").key == "alpha_mounting_panel"  # type: ignore[union-attr]


def test_rename_can_restore_an_alias_without_duplicate_identity(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)

    result = rename_part(root, "alpha_panel", "original_alpha_panel")
    part = load_manifest(root / "flowcad.project.yaml").parts[0]

    assert result.new_key == "original_alpha_panel"
    assert part.aliases == ("alpha_panel",)


def test_retire_keeps_part_queryable_and_is_idempotent(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)

    first = retire_part(root, "alpha_panel")
    second = retire_part(root, "original_alpha_panel")

    assert first.changed
    assert not second.changed
    assert load_manifest(root / "flowcad.project.yaml").parts[0].status is PartStatus.RETIRED
    assert get_part(root, "alpha_panel").status == "retired"  # type: ignore[union-attr]


def test_rename_failure_restores_original_manifest_and_index(tmp_path: Path, monkeypatch) -> None:
    root = _copy_fixture(tmp_path)
    manifest_path = root / "flowcad.project.yaml"
    original_bytes = manifest_path.read_bytes()
    real_sync = sync_project
    calls = 0

    def fail_once(project_root: Path, *, force: bool = False):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("injected sync failure")
        return real_sync(project_root, force=force)

    monkeypatch.setattr("flow_cad.registry.lifecycle.sync_project", fail_once)

    with pytest.raises(LifecycleError, match="restored"):
        rename_part(root, "alpha_panel", "must_not_persist")

    assert manifest_path.read_bytes() == original_bytes
    assert get_part(root, "alpha_panel") is not None
    assert get_part(root, "must_not_persist") is None


def test_rename_rejects_another_parts_key_without_writes(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path, "minimal_beta")
    manifest_path = root / "flowcad.project.yaml"
    original_bytes = manifest_path.read_bytes()

    with pytest.raises(LifecycleError, match="already exists"):
        rename_part(root, "beta_body", "beta_reference")

    assert manifest_path.read_bytes() == original_bytes
