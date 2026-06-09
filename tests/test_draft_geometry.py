from pathlib import Path

import pytest

from flow_cad.draft_geometry import DraftGeometryError, DraftGeometryStore, DraftNotFoundError
from flow_cad.project import init_project, load_project


def _draft_store(project_root: Path) -> DraftGeometryStore:
    init_project(project_root)
    project = load_project(project_root, fallback_to_bundled=False)
    return DraftGeometryStore(project)


def test_draft_panel_operations_return_facts_and_isolated_preview_step(tmp_path: Path) -> None:
    store = _draft_store(tmp_path)

    created = store.create_box_part(
        part_id="left_panel",
        length=120.0,
        width=45.0,
        height=3.0,
        material="PETG",
        role="draft",
    )
    draft_token = created["draft_token"]

    assert created["ok"] is True
    assert created["part_id"] == "left_panel"
    assert created["bounding_box"]["size"] == [120.0, 45.0, 3.0]
    assert created["feature_list"] == []
    assert created["hole_centers"] == []
    assert (tmp_path / ".flow" / "drafts" / draft_token / "draft.json").exists()

    store.set_panel_thickness(draft_token, thickness=4.0)
    store.add_hole(draft_token, face="top", x=12.0, y=8.0, diameter=4.2)
    store.add_hole(draft_token, face="top", x=108.0, y=8.0, diameter=4.2)
    store.add_counterbore(draft_token, face="top", x=60.0, y=20.0, diameter=8.0, depth=1.5)
    measured = store.add_slot(draft_token, face="top", x=60.0, y=32.0, length=20.0, width=5.0)

    assert measured["bounding_box"]["size"] == [120.0, 45.0, 4.0]
    assert [feature["kind"] for feature in measured["feature_list"]] == ["hole", "hole", "counterbore", "slot"]
    assert [center["diameter"] for center in measured["hole_centers"]] == [4.2, 4.2, 8.0]
    assert measured["hole_centers"][0]["center"] == [-48.0, -14.5, 0.0]
    assert measured["hole_centers"][0]["axis"] == [0.0, 0.0, 1.0]
    assert measured["feature_list"][0]["minimum_edge_distance_mm"] == pytest.approx(5.9)
    assert measured["warnings"] == []

    exported = store.export_draft_step(draft_token)
    preview_path = Path(str(exported["preview_step_path"]))

    assert preview_path.exists()
    assert preview_path.is_relative_to(tmp_path / ".flow" / "drafts")
    assert not preview_path.is_relative_to(tmp_path / "exports")
    assert not (tmp_path / "flow" / "parts" / "left_panel.py").exists()
    assert not any(path.is_file() for path in (tmp_path / "exports").rglob("*"))


def test_draft_state_can_be_reloaded_from_local_runtime_state(tmp_path: Path) -> None:
    store = _draft_store(tmp_path)
    created = store.create_box_part(part_id="reload_panel", length=20.0, width=10.0, height=2.0)
    draft_token = created["draft_token"]
    store.add_hole(draft_token, face="top", x=10.0, y=5.0, diameter=3.0)

    reloaded_store = DraftGeometryStore(load_project(tmp_path, fallback_to_bundled=False))
    measured = reloaded_store.measure_part(draft_token)

    assert measured["draft_token"] == draft_token
    assert measured["feature_list"][0]["kind"] == "hole"
    assert measured["hole_centers"][0]["center"] == [0.0, 0.0, 0.0]


def test_draft_discard_removes_local_runtime_artifacts(tmp_path: Path) -> None:
    store = _draft_store(tmp_path)
    created = store.create_box_part(part_id="discard_panel", length=20.0, width=10.0, height=2.0)
    draft_token = created["draft_token"]
    draft_dir = tmp_path / ".flow" / "drafts" / draft_token

    assert draft_dir.exists()
    assert store.discard(draft_token) == {"ok": True, "draft_token": draft_token, "discarded": True}
    assert not draft_dir.exists()

    with pytest.raises(DraftNotFoundError):
        store.measure_part(draft_token)


def test_draft_store_rejects_local_state_under_handoff_outputs(tmp_path: Path) -> None:
    init_project(tmp_path)
    manifest_path = tmp_path / "flowcad.project.yaml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace("  local_state: .flow", "  local_state: exports"),
        encoding="utf-8",
    )
    project = load_project(tmp_path, fallback_to_bundled=False)

    with pytest.raises(DraftGeometryError, match="must stay out of project source"):
        DraftGeometryStore(project)
