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


def test_edit_api_status_document_and_create_box_operation(tmp_path: Path) -> None:
    viewer_service = ViewerService(tmp_path)
    app = create_app(service=viewer_service)
    edit_status = _endpoint(app, "/api/edit/status", "GET")
    edit_document = _endpoint(app, "/api/edit/document", "GET")
    edit_operations = _endpoint(app, "/api/edit/operations", "POST")
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

    reloaded = edit_document()
    assert reloaded["revision"] == 1
    assert sorted(reloaded["entities"]) == ["box_001"]


def _endpoint(app: Any, path: str, method: str) -> Callable[..., dict[str, Any]]:
    for route in app.routes:
        if getattr(route, "path", "") == path and method in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError(f"Route not found: {method} {path}")
