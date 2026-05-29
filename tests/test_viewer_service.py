from pathlib import Path

from flow_cad.params import ChassisParams
from flow_cad.viewer.app import create_app
from flow_cad.viewer.service import ConversionUnavailableError, ViewerService


def _export_path(project_root: Path, kind: str, module_id: str, filename: str) -> Path:
    return project_root / ChassisParams().project_id / "exports" / kind / module_id / filename


def _write_step(project_root: Path, module_id: str = "lower_chassis", filename: str = "b3_lower_chassis_left_side_plate.step") -> Path:
    path = _export_path(project_root, "step", module_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n")
    return path


def _write_stl(project_root: Path, module_id: str = "lower_chassis", filename: str = "b3_lower_chassis_left_side_plate.stl") -> Path:
    path = _export_path(project_root, "stl", module_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("solid sample\nendsolid sample\n")
    return path


def test_viewer_service_lists_registry_parts_and_prefers_step(tmp_path) -> None:
    _write_step(tmp_path)
    _write_stl(tmp_path)

    service = ViewerService(tmp_path)
    payload = service.list_parts()
    part = next(part for part in payload["parts"] if part["id"] == "left_side_plate")

    assert payload["project_id"] == "b3"
    assert part["artifact_format"] == "step"
    assert part["artifact_path"] == "b3/exports/step/lower_chassis/b3_lower_chassis_left_side_plate.step"
    assert part["direct_stl_path"] == "b3/exports/stl/lower_chassis/b3_lower_chassis_left_side_plate.stl"
    assert part["in_assembly"] is True
    assert part["default_visible"] is True
    assert part["occurrences"][0]["location"][0] < 0


def test_viewer_service_places_wheel_box_tight_insert_in_body_frame(tmp_path) -> None:
    _write_step(tmp_path, "wheel_box", "b3_wheel_box_tight_insert.step")

    service = ViewerService(tmp_path)
    part = next(part for part in service.list_parts()["parts"] if part["id"] == "wheel_box_tight_insert")

    assert part["in_assembly"] is True
    assert part["default_visible"] is False
    assert part["occurrences"] == [
        {
            "name": "wheel_box_tight_insert",
            "location": [-76.0, 0.0, 49.8],
            "rotation": [0.0, 0.0, 0.0],
        }
    ]


def test_viewer_service_serves_direct_stl_when_no_step_exists(tmp_path) -> None:
    stl_path = _write_stl(tmp_path)

    service = ViewerService(tmp_path)
    model_path, source_format = service.model_path("left_side_plate")

    assert model_path == stl_path
    assert source_format == "stl"


def test_viewer_service_converts_step_to_cached_stl(tmp_path) -> None:
    step_path = _write_step(tmp_path)
    calls: list[tuple[Path, Path]] = []

    def converter(source: Path, dest: Path) -> Path:
        calls.append((source, dest))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("solid converted\nendsolid converted\n")
        return dest

    service = ViewerService(tmp_path, converter=converter)
    model_path, source_format = service.model_path("left_side_plate")

    assert source_format == "step"
    assert model_path == tmp_path / "b3" / "viewer-cache" / "stl-from-step" / "lower_chassis" / "b3_lower_chassis_left_side_plate.stl"
    assert calls == [(step_path, model_path)]


def test_viewer_service_returns_source_context() -> None:
    context = ViewerService().source_context("left_side_plate")

    assert context["component_id"] == "left_side_plate"
    assert context["relative_file_path"].endswith("registry.py")
    assert "left_side_plate" in context["excerpt"]


def test_viewer_app_registers_v1_routes(tmp_path) -> None:
    service = ViewerService(tmp_path)
    app = create_app(service=service)

    route_paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/health" in route_paths
    assert "/api/parts" in route_paths
    assert "/api/parts/{component_id}/model" in route_paths
    assert "/api/parts/{component_id}/source" in route_paths
    assert "/api/reload" in route_paths


def test_viewer_service_reload_and_direct_model(tmp_path) -> None:
    _write_stl(tmp_path)
    service = ViewerService(tmp_path)

    parts = service.list_parts()["parts"]
    assert any(part["id"] == "left_side_plate" for part in parts)

    model_path, source_format = service.model_path("left_side_plate")
    assert source_format == "stl"
    assert model_path.read_text() == "solid sample\nendsolid sample\n"

    assert service.reload()["revision"] == 1


def test_viewer_api_reports_missing_converter(tmp_path) -> None:
    _write_step(tmp_path)

    def converter(_source: Path, _dest: Path) -> Path:
        raise ConversionUnavailableError("missing STEP converter")

    service = ViewerService(tmp_path, converter=converter)

    try:
        service.model_path("left_side_plate")
    except ConversionUnavailableError as exc:
        assert str(exc) == "missing STEP converter"
    else:
        raise AssertionError("Expected missing converter error")
