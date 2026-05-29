from pathlib import Path
import time

from flow_cad.viewer.app import create_app
from flow_cad.viewer.service import ConversionUnavailableError, ViewerService


def _export_path(project_root: Path, kind: str, module_id: str, filename: str) -> Path:
    return project_root / "example" / "exports" / kind / module_id / filename


def _write_step(project_root: Path, module_id: str = "example", filename: str = "example_block.step") -> Path:
    path = _export_path(project_root, "step", module_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n")
    return path


def _write_stl(project_root: Path, module_id: str = "example", filename: str = "example_block.stl") -> Path:
    path = _export_path(project_root, "stl", module_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("solid sample\nendsolid sample\n")
    return path


def _write_build123d_step(project_root: Path, shape) -> Path:
    from build123d import export_step

    path = _export_path(project_root, "step", "example", "example_block.step")
    path.parent.mkdir(parents=True, exist_ok=True)
    export_step(shape, path)
    return path


def test_viewer_service_lists_example_parts_and_prefers_step(tmp_path) -> None:
    _write_step(tmp_path)
    _write_stl(tmp_path)

    service = ViewerService(tmp_path)
    payload = service.list_parts()
    part = payload["parts"][0]

    assert payload["project_id"] == "flow_example"
    assert part["id"] == "example_block"
    assert part["artifact_format"] == "step"
    assert part["artifact_path"] == "example/exports/step/example/example_block.step"
    assert part["direct_stl_path"] == "example/exports/stl/example/example_block.stl"
    assert part["snap_features_url"] == "/api/parts/example_block/snap-features"
    assert part["in_assembly"] is True
    assert part["default_visible"] is True
    assert part["occurrences"] == [
        {
            "name": "example_block",
            "location": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
        }
    ]


def test_viewer_service_serves_direct_stl_when_no_step_exists(tmp_path) -> None:
    stl_path = _write_stl(tmp_path)

    service = ViewerService(tmp_path)
    model_path, source_format = service.model_path("example_block")

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
    model_path, source_format = service.model_path("example_block")

    assert source_format == "step"
    assert model_path == tmp_path / "example" / "viewer-cache" / "stl-from-step" / "example" / "example_block.stl"
    assert calls == [(step_path, model_path)]


def test_viewer_service_returns_source_context() -> None:
    context = ViewerService().source_context("example_block")

    assert context["component_id"] == "example_block"
    assert context["symbol"] == "_make_example_block"
    assert context["relative_file_path"] == "src/flow_cad/project.py"
    assert context["language"] == "python"
    assert context["start_line"] == 1
    assert context["end_line"] == len(context["content"].splitlines())
    assert "def _make_example_block" in context["content"]
    assert context["highlight_start_line"] > context["start_line"]
    assert context["highlight_end_line"] >= context["highlight_start_line"]


def test_viewer_app_registers_v1_routes(tmp_path) -> None:
    service = ViewerService(tmp_path)
    app = create_app(service=service)

    route_paths = {getattr(route, "path", "") for route in app.routes}

    assert "/api/health" in route_paths
    assert "/api/parts" in route_paths
    assert "/api/parts/{component_id}/model" in route_paths
    assert "/api/parts/{component_id}/source" in route_paths
    assert "/api/parts/{component_id}/snap-features" in route_paths
    assert "/api/reload" in route_paths


def test_viewer_service_reload_and_direct_model(tmp_path) -> None:
    _write_stl(tmp_path)
    service = ViewerService(tmp_path)

    parts = service.list_parts()["parts"]
    assert any(part["id"] == "example_block" for part in parts)

    model_path, source_format = service.model_path("example_block")
    assert source_format == "stl"
    assert model_path.read_text() == "solid sample\nendsolid sample\n"

    assert service.reload()["revision"] == 1


def test_viewer_api_reports_missing_converter(tmp_path) -> None:
    _write_step(tmp_path)

    def converter(_source: Path, _dest: Path) -> Path:
        raise ConversionUnavailableError("missing STEP converter")

    service = ViewerService(tmp_path, converter=converter)

    try:
        service.model_path("example_block")
    except ConversionUnavailableError as exc:
        assert str(exc) == "missing STEP converter"
    else:
        raise AssertionError("Expected missing converter error")


def test_viewer_service_extracts_step_snap_features(tmp_path) -> None:
    from build123d import Box, Cylinder

    _write_build123d_step(tmp_path, Box(10, 20, 30))
    service = ViewerService(tmp_path)

    box_payload = service.snap_features("example_block")
    box_features = box_payload["features"]

    assert box_payload["component_id"] == "example_block"
    assert box_payload["schema_version"] == 2
    assert box_payload["source_format"] == "step"
    assert box_payload["artifact_path"] == "example/exports/step/example/example_block.step"
    assert {feature["kind"] for feature in box_features} >= {"vertex", "line_edge", "edge_midpoint"}
    assert any(feature["label"] == "Edge" and feature["length"] == 30.0 for feature in box_features)
    assert len({feature["id"] for feature in box_features}) == len(box_features)

    _write_build123d_step(tmp_path, Cylinder(3, 8))
    step_path = _export_path(tmp_path, "step", "example", "example_block.step")
    future = time.time() + 5
    step_path.touch()
    step_path.parent.touch()
    import os
    os.utime(step_path, (future, future))

    cylinder_payload = service.snap_features("example_block")
    cylinder_features = cylinder_payload["features"]

    assert any(feature["kind"] == "circle_center" for feature in cylinder_features)
    assert any(feature["label"] == "Hole Center" and feature["radius"] == 3.0 for feature in cylinder_features)
    assert any(feature["kind"] == "circle_center" and len(feature["ring_points"]) == 8 for feature in cylinder_features)


def test_viewer_service_snap_features_fallbacks_are_safe(tmp_path) -> None:
    _write_stl(tmp_path)
    service = ViewerService(tmp_path)

    assert service.snap_features("example_block") == {
        "component_id": "example_block",
        "artifact_path": None,
        "schema_version": 2,
        "source_format": "stl",
        "features": [],
        "warnings": [],
    }

    _write_step(tmp_path)
    payload = service.snap_features("example_block")

    assert payload["component_id"] == "example_block"
    assert payload["source_format"] == "step"
    assert payload["features"] == []
    assert payload["warnings"]
