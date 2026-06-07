from pathlib import Path
from typing import Any, Callable

import pytest

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


def test_edit_api_status_document_and_create_box_operation(tmp_path: Path) -> None:
    viewer_service = ViewerService(tmp_path)
    app = create_app(service=viewer_service)
    edit_status = _endpoint(app, "/api/edit/status", "GET")
    edit_document = _endpoint(app, "/api/edit/document", "GET")
    edit_operations = _endpoint(app, "/api/edit/operations", "POST")
    edit_entity = _endpoint(app, "/api/edit/entities/{entity_id}", "PATCH")
    health = _endpoint(app, "/api/health", "GET")

    status = edit_status()
    assert status["editing_available"] is True
    assert status["document_path"] == "flow/document.json"
    assert status["document_exists"] is False
    assert status["document_revision"] == 0

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

    reloaded = edit_document()
    assert reloaded["revision"] == 2
    assert sorted(reloaded["entities"]) == ["box_001"]


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


def _endpoint(app: Any, path: str, method: str) -> Callable[..., dict[str, Any]]:
    for route in app.routes:
        if getattr(route, "path", "") == path and method in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"Route not found: {method} {path}")
