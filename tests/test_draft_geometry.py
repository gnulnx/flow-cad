import subprocess
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


def test_draft_profile_operations_return_non_rectangular_profile_facts_and_step(tmp_path: Path) -> None:
    store = _draft_store(tmp_path)

    profile_points = [
        [-50.0, -12.0],
        [-20.0, -32.5],
        [0.0, -18.0],
        [20.0, -32.5],
        [50.0, -12.0],
        [34.0, 12.0],
        [0.0, 32.5],
        [-34.0, 12.0],
        [-50.0, -12.0],
    ]
    created = store.create_profile_part(
        part_id="sketch_profile",
        length=100.0,
        width=65.0,
        height=10.0,
        profile_points=profile_points,
    )
    draft_token = created["draft_token"]

    assert created["ok"] is True
    assert created["part_id"] == "sketch_profile"
    assert created["profile_points"] == profile_points
    assert created["bounding_box"]["size"] == pytest.approx([100.0, 65.0, 10.0])
    assert created["profile_points"][:4] != [
        [-50.0, -32.5],
        [50.0, -32.5],
        [50.0, 32.5],
        [-50.0, 32.5],
    ]

    store.add_hole(draft_token, face="top", x=25.0, y=32.5, diameter=4.0)
    with_hole = store.add_counterbore(draft_token, face="top", x=75.0, y=32.5, diameter=7.2, depth=2.5)

    assert [feature["kind"] for feature in with_hole["feature_list"]] == ["hole", "counterbore"]
    assert with_hole["hole_centers"][0]["center"] == [-25.0, 0.0, 0.0]
    exported = store.export_draft_step(draft_token)
    assert Path(str(exported["preview_step_path"])).exists()


def test_draft_features_can_be_mirrored_to_opposing_face(tmp_path: Path) -> None:
    store = _draft_store(tmp_path)
    created = store.create_box_part(part_id="mirrored_panel", length=40.0, width=20.0, height=3.0)
    draft_token = created["draft_token"]
    store.add_hole(draft_token, face="top", x=8.0, y=6.0, diameter=3.2)
    store.add_counterbore(draft_token, face="top", x=30.0, y=10.0, diameter=6.0, depth=1.0)
    exported = store.export_draft_step(draft_token)

    mirrored = store.mirror_features(draft_token, source_face="top", target_face="bottom")

    assert mirrored["preview_step_path"] is None
    assert Path(str(exported["preview_step_path"])).exists()
    assert [feature["face"] for feature in mirrored["feature_list"]] == ["top", "top", "bottom", "bottom"]
    assert [feature["kind"] for feature in mirrored["feature_list"]] == ["hole", "counterbore", "hole", "counterbore"]
    assert mirrored["feature_list"][2]["parameters"]["x"] == 8.0
    assert mirrored["feature_list"][2]["parameters"]["y"] == 6.0
    assert mirrored["hole_centers"][2]["axis"] == [0.0, 0.0, -1.0]
    assert mirrored["hole_centers"][2]["center"] == [-12.0, -4.0, 0.0]
    assert mirrored["hole_centers"][3]["axis"] == [0.0, 0.0, -1.0]


def test_draft_feature_mirroring_requires_opposing_faces_with_features(tmp_path: Path) -> None:
    store = _draft_store(tmp_path)
    created = store.create_box_part(part_id="bad_mirror_panel", length=40.0, width=20.0, height=3.0)
    draft_token = created["draft_token"]
    store.add_hole(draft_token, face="top", x=8.0, y=6.0, diameter=3.2)

    with pytest.raises(DraftGeometryError, match="opposing faces"):
        store.mirror_features(draft_token, source_face="top", target_face="front")

    with pytest.raises(DraftGeometryError, match="No features found"):
        store.mirror_features(draft_token, source_face="bottom", target_face="top")


def test_draft_transaction_accepts_into_review_artifacts_without_source_writes(tmp_path: Path) -> None:
    store = _draft_store(tmp_path)

    begun = store.begin_transaction(part_id="transaction_panel")
    transaction_token = begun["transaction_token"]
    transaction_dir = tmp_path / ".flow" / "draft-transactions" / transaction_token

    assert begun["status"] == "open"
    assert begun["draft"] is None
    assert (transaction_dir / "transaction.json").exists()

    created = store.transaction_create_box(
        transaction_token,
        length=120.0,
        width=45.0,
        height=3.0,
        material="PETG",
    )
    draft_token = created["draft_token"]
    store.transaction_add_hole(transaction_token, face="top", x=12.0, y=8.0, diameter=4.2)
    store.transaction_add_louver_pattern(
        transaction_token,
        face="top",
        count=3,
        pitch=12.0,
        x=60.0,
        y=30.0,
        width=10.0,
        height=3.0,
    )
    previewed = store.transaction_preview(transaction_token)
    preview_path = Path(str(previewed["preview_step_path"]))

    assert preview_path.exists()
    assert preview_path.is_relative_to(tmp_path / ".flow" / "drafts")

    accepted = store.accept_transaction(transaction_token)
    source_patch_path = Path(str(accepted["source_patch_path"]))
    generated_source_path = Path(str(accepted["generated_source_path"]))
    validator_stub_path = Path(str(accepted["validator_stub_path"]))
    acceptance_manifest_path = Path(str(accepted["acceptance_manifest_path"]))

    assert accepted["status"] == "accepted"
    assert [operation["name"] for operation in accepted["operations"]] == [
        "create_box",
        "add_hole",
        "add_louver_pattern",
        "preview",
        "accept",
    ]
    assert source_patch_path.exists()
    assert source_patch_path.is_relative_to(transaction_dir)
    assert generated_source_path.exists()
    assert validator_stub_path.exists()
    assert acceptance_manifest_path.exists()
    assert "diff --git a/flow/parts/transaction_panel.py" in source_patch_path.read_text(encoding="utf-8")
    assert "diff --git a/flow/validators/check_transaction_panel_draft.py" in source_patch_path.read_text(encoding="utf-8")
    assert "make_transaction_panel" in generated_source_path.read_text(encoding="utf-8")
    assert "validate_transaction_panel_draft" in validator_stub_path.read_text(encoding="utf-8")
    compile(generated_source_path.read_text(encoding="utf-8"), str(generated_source_path), "exec")
    compile(validator_stub_path.read_text(encoding="utf-8"), str(validator_stub_path), "exec")
    subprocess.run(["git", "apply", "--check", str(source_patch_path)], cwd=tmp_path, check=True)
    assert not (tmp_path / "flow" / "parts" / "transaction_panel.py").exists()
    assert not (tmp_path / "flow" / "validators" / "check_transaction_panel_draft.py").exists()
    assert not any(path.is_file() for path in (tmp_path / "exports").rglob("*"))
    assert (tmp_path / ".flow" / "drafts" / draft_token / "draft.json").exists()

    with pytest.raises(DraftGeometryError, match="not open"):
        store.transaction_add_hole(transaction_token, face="top", x=108.0, y=8.0, diameter=4.2)


def test_draft_transaction_state_can_be_reloaded_and_discarded(tmp_path: Path) -> None:
    store = _draft_store(tmp_path)
    begun = store.begin_transaction(part_id="reload_transaction_panel")
    transaction_token = begun["transaction_token"]
    created = store.transaction_create_box(transaction_token, length=20.0, width=10.0, height=2.0)
    draft_token = created["draft_token"]
    store.transaction_add_hole(transaction_token, face="top", x=10.0, y=5.0, diameter=3.0)

    reloaded_store = DraftGeometryStore(load_project(tmp_path, fallback_to_bundled=False))
    measured = reloaded_store.transaction_measure(transaction_token)

    assert measured["transaction_token"] == transaction_token
    assert measured["draft"]["hole_centers"][0]["center"] == [0.0, 0.0, 0.0]

    discarded = reloaded_store.discard_transaction(transaction_token)

    assert discarded == {"ok": True, "transaction_token": transaction_token, "discarded": True}
    assert not (tmp_path / ".flow" / "draft-transactions" / transaction_token).exists()
    assert not (tmp_path / ".flow" / "drafts" / draft_token).exists()
    with pytest.raises(DraftNotFoundError):
        reloaded_store.transaction_measure(transaction_token)


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
