from pathlib import Path
from typing import Any, Callable

import pytest

from flow_cad.editing.kernel import shape_for_entity
from flow_cad.editing.service import EditService, EditServiceError
from flow_cad.project import bundled_example_project
from flow_cad.viewer.app import create_app
from flow_cad.viewer.service import ViewerService


def test_empty_edit_document_is_created_under_flow_source(tmp_path: Path) -> None:
    service = EditService(bundled_example_project(tmp_path))

    payload = service.document()

    assert payload["document_path"] == "flow/document.json"
    assert payload["schema_version"] == 1
    assert payload["revision"] == 0
    assert payload["entities"] == {}
    assert (tmp_path / "flow" / "document.json").exists()


def test_create_box_operation_persists_and_reloads_exact_dimensions(tmp_path: Path) -> None:
    service = EditService(bundled_example_project(tmp_path))

    result = service.append_operation(
        {
            "type": "create_box",
            "entity_id": "box_custom",
            "size_mm": [10, 20, 30],
            "transform": {
                "translation_mm": [0, 0, 15],
                "rotation_deg": [0, 0, 0],
            },
        }
    )

    assert result["document_revision"] == 1
    assert result["operation"]["id"] == "op_001"
    assert result["operation"]["type"] == "create_box"
    assert result["entity"]["id"] == "box_custom"
    assert result["entity"]["role"] == "inspection"
    assert result["entity"]["bounds"]["size_mm"] == pytest.approx([10.0, 20.0, 30.0])
    assert result["entity"]["bounds"]["center_mm"] == pytest.approx([0.0, 0.0, 15.0])

    reloaded = EditService(bundled_example_project(tmp_path)).document()
    assert reloaded["revision"] == 1
    assert reloaded["entities"]["box_custom"]["kind"] == "primitive_box"
    assert reloaded["entities"]["box_custom"]["size_mm"] == [10.0, 20.0, 30.0]
    assert reloaded["operations"][0]["entity_id"] == "box_custom"


def test_create_box_rejects_invalid_transform_payload(tmp_path: Path) -> None:
    service = EditService(bundled_example_project(tmp_path))

    with pytest.raises(EditServiceError, match="`transform` must be an object"):
        service.append_operation({"type": "create_box", "transform": [0, 0, 0]})


def test_transform_and_resize_operations_persist_entity_updates(tmp_path: Path) -> None:
    service = EditService(bundled_example_project(tmp_path))
    service.append_operation(
        {
            "type": "create_box",
            "entity_id": "box_custom",
            "size_mm": [10, 20, 30],
            "translation_mm": [0, 0, 15],
        }
    )

    moved = service.append_operation(
        {
            "type": "set_transform",
            "entity_id": "box_custom",
            "translation_mm": [5, 0, 20],
        }
    )

    assert moved["document_revision"] == 2
    assert moved["operation"]["id"] == "op_002"
    assert moved["operation"]["type"] == "set_transform"
    assert moved["entity"]["bounds"]["center_mm"] == pytest.approx([5.0, 0.0, 20.0])

    resized = service.patch_entity("edit:box_custom", {"size_mm": [20, 10, 8]})

    assert resized["document_revision"] == 3
    assert resized["operation"]["id"] == "op_003"
    assert resized["operation"]["type"] == "resize_box"
    assert resized["entity"]["bounds"]["size_mm"] == pytest.approx([20.0, 10.0, 8.0])
    assert resized["entity"]["bounds"]["center_mm"] == pytest.approx([5.0, 0.0, 20.0])

    reloaded = EditService(bundled_example_project(tmp_path)).document()
    assert reloaded["revision"] == 3
    assert reloaded["entities"]["box_custom"]["size_mm"] == [20.0, 10.0, 8.0]
    assert reloaded["entities"]["box_custom"]["transform"]["translation_mm"] == [5.0, 0.0, 20.0]
    assert [operation["type"] for operation in reloaded["operations"]] == [
        "create_box",
        "set_transform",
        "resize_box",
    ]


def test_create_and_update_points_preserves_quality_and_source(tmp_path: Path) -> None:
    service = EditService(bundled_example_project(tmp_path))

    created = service.create_point(
        {
            "position_mm": [1, 2, 3],
            "quality": "approximate",
            "source": {
                "kind": "mesh_pick",
                "part_id": "loose_stl",
            },
        }
    )

    assert created["document_revision"] == 1
    assert created["operation"]["type"] == "create_point"
    assert created["point"]["id"] == "point_001"
    assert created["point"]["position_mm"] == [1.0, 2.0, 3.0]
    assert created["point"]["quality"] == "approximate"
    assert created["point"]["source"]["kind"] == "mesh_pick"

    updated = service.patch_point(
        "point_001",
        {
            "position_mm": [4, 5, 6],
            "quality": "exact",
            "source": {
                "kind": "typed_coordinates",
            },
        },
    )

    assert updated["document_revision"] == 2
    assert updated["operation"]["type"] == "update_point"
    assert updated["operation"]["previous_point"]["quality"] == "approximate"
    assert updated["point"]["position_mm"] == [4.0, 5.0, 6.0]
    assert updated["point"]["quality"] == "exact"

    reloaded = EditService(bundled_example_project(tmp_path)).document()
    assert reloaded["revision"] == 2
    assert reloaded["points"]["point_001"]["position_mm"] == [4.0, 5.0, 6.0]
    assert reloaded["points"]["point_001"]["quality"] == "exact"


def test_create_point_requires_coordinates(tmp_path: Path) -> None:
    service = EditService(bundled_example_project(tmp_path))

    with pytest.raises(EditServiceError, match="`position_mm` is required"):
        service.create_point({"quality": "exact"})


def test_cut_hole_operation_persists_and_changes_exact_box_shape(tmp_path: Path) -> None:
    service = EditService(bundled_example_project(tmp_path))
    service.append_operation(
        {
            "type": "create_box",
            "entity_id": "box_custom",
            "size_mm": [20, 20, 20],
            "translation_mm": [0, 0, 10],
        }
    )
    service.create_point({"point_id": "point_center", "position_mm": [0, 0, 10], "quality": "exact"})
    before = shape_for_entity(service.document_model().entities["box_custom"]).volume

    result = service.append_operation(
        {
            "type": "cut_hole",
            "target_entity_id": "edit:box_custom",
            "point_id": "point_center",
            "preset": "m4_clearance",
            "axis": [0, 0, 1],
        }
    )

    assert result["document_revision"] == 3
    assert result["operation"]["type"] == "cut_hole"
    assert result["operation"]["preset"] == "m4_clearance"
    assert result["operation"]["diameter_mm"] == 4.5
    assert result["entity"]["holes"][0]["point_id"] == "point_center"
    assert result["entity"]["holes"][0]["axis"] == [0.0, 0.0, 1.0]
    assert result["entity"]["bounds"]["size_mm"] == pytest.approx([20.0, 20.0, 20.0])

    reloaded = EditService(bundled_example_project(tmp_path)).document_model()
    assert reloaded.revision == 3
    assert reloaded.entities["box_custom"].holes[0].diameter_mm == pytest.approx(4.5)
    assert [operation["type"] for operation in reloaded.operations] == ["create_box", "create_point", "cut_hole"]
    assert shape_for_entity(reloaded.entities["box_custom"]).volume < before


def test_cut_hole_rejects_approximate_points(tmp_path: Path) -> None:
    service = EditService(bundled_example_project(tmp_path))
    service.append_operation({"type": "create_box", "entity_id": "box_custom"})
    service.create_point({"point_id": "point_mesh", "position_mm": [0, 0, 0], "quality": "approximate"})

    with pytest.raises(EditServiceError, match="Approximate edit points cannot drive exact through-hole cuts"):
        service.create_hole({"target_entity_id": "box_custom", "point_id": "point_mesh"})


def test_cut_hole_rejects_non_cardinal_axes(tmp_path: Path) -> None:
    service = EditService(bundled_example_project(tmp_path))
    service.append_operation({"type": "create_box", "entity_id": "box_custom"})
    service.create_point({"point_id": "point_center", "position_mm": [0, 0, 0], "quality": "exact"})

    with pytest.raises(EditServiceError, match=r"\+/-X, \+/-Y, \+/-Z"):
        service.create_hole({"target_entity_id": "box_custom", "point_id": "point_center", "axis": [1, 1, 0]})


def test_boolean_fuse_keeps_tool_as_construction_and_updates_target_shape(tmp_path: Path) -> None:
    service = EditService(bundled_example_project(tmp_path))
    service.append_operation({"type": "create_box", "entity_id": "target", "size_mm": [10, 10, 10]})
    service.append_operation({"type": "create_box", "entity_id": "tool", "size_mm": [10, 10, 10], "translation_mm": [12, 0, 0]})
    before = shape_for_entity(service.document_model().entities["target"]).volume

    result = service.create_boolean({"operation": "fuse", "target_entity_id": "target", "tool_entity_id": "edit:tool"})

    assert result["document_revision"] == 3
    assert result["operation"]["type"] == "fuse"
    assert result["boolean"]["tool_entity_id"] == "tool"
    assert result["tool_entity"]["role"] == "construction"

    reloaded = EditService(bundled_example_project(tmp_path)).document_model()
    assert reloaded.entities["target"].booleans[0].type == "fuse"
    assert reloaded.entities["tool"].role == "construction"
    assert shape_for_entity(reloaded.entities["target"], reloaded).volume > before


def test_boolean_cut_keeps_tool_and_removes_volume_from_target_shape(tmp_path: Path) -> None:
    service = EditService(bundled_example_project(tmp_path))
    service.append_operation({"type": "create_box", "entity_id": "target", "size_mm": [20, 20, 20]})
    service.append_operation({"type": "create_box", "entity_id": "tool", "size_mm": [10, 10, 10]})
    before = shape_for_entity(service.document_model().entities["target"]).volume

    result = service.append_operation({"type": "cut", "target_entity_id": "edit:target", "tool_entity_id": "tool"})

    assert result["document_revision"] == 3
    assert result["operation"]["type"] == "cut"
    assert result["entity"]["booleans"][0]["type"] == "cut"
    assert result["entity"]["bounds"]["size_mm"] == pytest.approx([20.0, 20.0, 20.0])

    reloaded = EditService(bundled_example_project(tmp_path)).document_model()
    assert reloaded.entities["tool"].role == "construction"
    assert shape_for_entity(reloaded.entities["target"], reloaded).volume < before


def test_boolean_operations_reject_invalid_targets(tmp_path: Path) -> None:
    service = EditService(bundled_example_project(tmp_path))
    service.append_operation({"type": "create_box", "entity_id": "target"})

    with pytest.raises(EditServiceError, match="Boolean target and tool must be different"):
        service.create_boolean({"operation": "cut", "target_entity_id": "target", "tool_entity_id": "target"})

    with pytest.raises(EditServiceError, match="Edit entity is not registered: missing"):
        service.create_boolean({"operation": "fuse", "target_entity_id": "target", "tool_entity_id": "missing"})


def test_edit_api_status_document_and_create_box_operation(tmp_path: Path) -> None:
    viewer_service = ViewerService(tmp_path)
    app = create_app(service=viewer_service)
    edit_status = _endpoint(app, "/api/edit/status", "GET")
    edit_document = _endpoint(app, "/api/edit/document", "GET")
    edit_operations = _endpoint(app, "/api/edit/operations", "POST")
    edit_entity = _endpoint(app, "/api/edit/entities/{entity_id}", "PATCH")
    edit_points = _endpoint(app, "/api/edit/points", "POST")
    edit_point = _endpoint(app, "/api/edit/points/{point_id}", "PATCH")
    edit_holes = _endpoint(app, "/api/edit/holes", "POST")
    edit_booleans = _endpoint(app, "/api/edit/booleans", "POST")
    health = _endpoint(app, "/api/health", "GET")

    status = edit_status()
    assert status["editing_available"] is True
    assert status["document_path"] == "flow/document.json"
    assert status["document_exists"] is False
    assert status["document_revision"] == 0
    assert status["tool_presets"]["holes"]["m4_clearance"]["diameter_mm"] == 4.5
    assert status["tool_presets"]["holes"]["m5_clearance"]["diameter_mm"] == 5.5

    document = edit_document()
    assert document["revision"] == 0
    assert (tmp_path / "flow" / "document.json").exists()

    created = edit_operations(
        {
            "type": "create_box",
            "size_mm": [12, 14, 16],
            "translation_mm": [0, 0, 8],
        }
    )

    assert created["ok"] is True
    assert created["document_revision"] == 1
    assert created["entity"]["id"] == "box_001"
    assert created["entity"]["bounds"]["size_mm"] == pytest.approx([12.0, 14.0, 16.0])
    assert health()["revision"] == 1

    moved = edit_entity("box_001", {"translation_mm": [1, 2, 3]})
    assert moved["document_revision"] == 2
    assert moved["operation"]["type"] == "set_transform"
    assert health()["revision"] == 2

    point = edit_points({"position_mm": [9, 8, 7], "quality": "exact"})
    assert point["document_revision"] == 3
    assert point["point"]["id"] == "point_001"
    assert health()["revision"] == 3

    point_update = edit_point("point_001", {"position_mm": [3, 2, 1]})
    assert point_update["document_revision"] == 4
    assert point_update["point"]["position_mm"] == [3.0, 2.0, 1.0]
    assert health()["revision"] == 4

    hole = edit_holes({"target_entity_id": "box_001", "point_id": "point_001", "preset": "m5_clearance"})
    assert hole["document_revision"] == 5
    assert hole["operation"]["type"] == "cut_hole"
    assert hole["hole"]["diameter_mm"] == 5.5
    assert health()["revision"] == 5

    tool = edit_operations({"type": "create_box", "entity_id": "tool", "size_mm": [4, 4, 4]})
    assert tool["document_revision"] == 6
    boolean = edit_booleans({"operation": "cut", "target_entity_id": "box_001", "tool_entity_id": "tool"})
    assert boolean["document_revision"] == 7
    assert boolean["operation"]["type"] == "cut"
    assert boolean["tool_entity"]["role"] == "construction"
    assert health()["revision"] == 7

    reloaded = edit_document()
    assert reloaded["revision"] == 7
    assert sorted(reloaded["entities"]) == ["box_001", "tool"]
    assert sorted(reloaded["points"]) == ["point_001"]
    assert reloaded["entities"]["box_001"]["holes"][0]["preset"] == "m5_clearance"
    assert reloaded["entities"]["box_001"]["booleans"][0]["type"] == "cut"


def test_viewer_service_lists_edit_entities_as_exact_parts(tmp_path: Path) -> None:
    viewer_service = ViewerService(tmp_path)
    viewer_service.append_edit_operation(
        {
            "type": "create_box",
            "size_mm": [10, 20, 30],
            "translation_mm": [0, 0, 15],
        }
    )

    payload = viewer_service.list_parts()
    edit_part = next(part for part in payload["parts"] if part["id"] == "edit:box_001")

    assert edit_part["module_id"] == "flow_document"
    assert edit_part["role"] == "inspection"
    assert edit_part["source_kind"] == "flow_document"
    assert edit_part["geometry_authority"] == "step_kernel"
    assert edit_part["capabilities"]["exact_editing"] is True
    assert edit_part["artifact_format"] == "step"
    assert edit_part["artifact_path"] == "example/viewer-cache/edit-step/box_001.step"
    assert edit_part["model_url"] == "/api/parts/edit:box_001/model"
    assert edit_part["source_url"] == "/api/parts/edit:box_001/source"
    assert edit_part["snap_features_url"] == "/api/parts/edit:box_001/snap-features"
    assert edit_part["occurrences"] == [
        {
            "name": "box_001",
            "location": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
        }
    ]
    assert edit_part["default_visible"] is True

    context = viewer_service.source_context("edit:box_001")
    assert context["relative_file_path"] == "flow/document.json"
    assert context["language"] == "json"
    assert context["symbol"] == "box_001"
    assert '"box_001"' in context["content"]


def test_viewer_service_lazily_exports_edit_entity_model(tmp_path: Path) -> None:
    calls: list[tuple[Path, Path]] = []

    def converter(source: Path, dest: Path) -> Path:
        calls.append((source, dest))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("solid edit\nendsolid edit\n")
        return dest

    viewer_service = ViewerService(tmp_path, converter=converter)
    viewer_service.append_edit_operation(
        {
            "type": "create_box",
            "size_mm": [10, 20, 30],
            "translation_mm": [0, 0, 15],
        }
    )

    model_path, source_format = viewer_service.model_path("edit:box_001")

    expected_step_path = tmp_path / "example" / "viewer-cache" / "edit-step" / "box_001.step"
    expected_stl_path = tmp_path / "example" / "viewer-cache" / "stl-from-edit" / "box_001.stl"
    assert source_format == "step"
    assert model_path == expected_stl_path
    assert expected_step_path.exists()
    assert calls == [(expected_step_path, expected_stl_path)]

    viewer_service.model_path("edit:box_001")
    assert calls == [(expected_step_path, expected_stl_path)]

    snap_payload = viewer_service.snap_features("edit:box_001")
    assert snap_payload["component_id"] == "edit:box_001"
    assert snap_payload["source_format"] == "step"
    assert snap_payload["artifact_path"] == "example/viewer-cache/edit-step/box_001.step"
    assert snap_payload["capabilities"]["exact_snap"] is True
    assert snap_payload["capabilities"]["exact_editing"] is True
    assert {feature["kind"] for feature in snap_payload["features"]} >= {"vertex", "line_edge", "edge_midpoint"}


def test_viewer_service_refreshes_edit_snap_features_after_hole_cut(tmp_path: Path) -> None:
    viewer_service = ViewerService(tmp_path)
    viewer_service.append_edit_operation(
        {
            "type": "create_box",
            "size_mm": [20, 20, 20],
            "translation_mm": [0, 0, 10],
        }
    )
    viewer_service.create_edit_point({"point_id": "point_center", "position_mm": [0, 0, 10], "quality": "exact"})
    before = viewer_service.snap_features("edit:box_001")
    assert all(feature["kind"] != "circle_center" for feature in before["features"])

    viewer_service.create_edit_hole(
        {
            "target_entity_id": "edit:box_001",
            "point_id": "point_center",
            "preset": "m4_clearance",
            "axis": [0, 0, 1],
        }
    )

    after = viewer_service.snap_features("edit:box_001")
    circle_centers = [feature for feature in after["features"] if feature["kind"] == "circle_center"]
    assert after["capabilities"]["exact_editing"] is True
    assert [feature["radius"] for feature in circle_centers] == pytest.approx([2.25, 2.25])
    assert sorted(round(feature["point"][2], 3) for feature in circle_centers) == [0.0, 20.0]


def _endpoint(app: Any, path: str, method: str) -> Callable[..., dict[str, Any]]:
    for route in app.routes:
        if getattr(route, "path", "") == path and method in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"Route not found: {method} {path}")
