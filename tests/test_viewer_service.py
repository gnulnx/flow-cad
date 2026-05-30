from pathlib import Path
import json
import time

from flow_cad.viewer.app import create_app
from flow_cad.viewer.service import ConversionUnavailableError, ViewerService
from flow_cad.viewer.geometry_authority import DISPLAY_MESH_CONTRACT_VERSION, SNAP_EXTRACTOR_CONTRACT_VERSION
from flow_cad.core.metadata import PartDefinition, PartRole
from flow_cad.project import FlowCadProject, ProjectDocs, ProjectPaths


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
    assert part["source_kind"] == "flow_python"
    assert part["geometry_authority"] == "step_kernel"
    assert part["quality_label"] == "exact"
    assert part["capabilities"]["exact_topology"] is True
    assert part["capabilities"]["exact_snap"] is True
    assert part["capabilities"]["mesh_only"] is False
    assert part["warnings"] == []
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


def test_viewer_service_reports_active_version_and_hides_references_by_default(tmp_path) -> None:
    class Params:
        project_id = "versioned"

    definitions = (
        PartDefinition(
            "wheel_box_test_body",
            "wheel_box",
            "body.step",
            lambda _params: object(),
            role=PartRole.PRINTABLE,
            version="b3_v2",
            family="wheel_box",
            assembly_ids=("b3_v2_wheel_box",),
        ),
        PartDefinition(
            "reference_wheel_pair",
            "reference",
            "wheels.step",
            lambda _params: object(),
            role=PartRole.REFERENCE,
            version="b3_v2",
            family="reference",
            compatible_versions=("b3_v1",),
        ),
        PartDefinition(
            "left_side_plate",
            "lower_chassis",
            "left.step",
            lambda _params: object(),
            role=PartRole.LEGACY,
            version="b3_v1",
            family="lower_chassis",
            assembly_ids=("b3_v1_lower_chassis",),
        ),
    )

    def iter_part_definitions(*, include_references: bool = True):
        for definition in definitions:
            if include_references or definition.role != PartRole.REFERENCE:
                yield definition

    def get_assembly_placements(_params, *, include_references: bool = False, assembly_id: str | None = None):
        if assembly_id == "b3_v1_lower_chassis":
            placements = [
                {
                    "name": "left_side_plate",
                    "part_key": "left_side_plate",
                    "location": (-10.0, 0.0, 0.0),
                    "rotation": (0.0, 0.0, 0.0),
                }
            ]
        else:
            placements = [
                {
                    "name": "wheel_box_test_body",
                    "part_key": "wheel_box_test_body",
                    "location": (0.0, 0.0, 0.0),
                    "rotation": (0.0, 0.0, 0.0),
                }
            ]
        if include_references:
            placements.append(
                {
                    "name": "reference_wheel_pair",
                    "part_key": "reference_wheel_pair",
                    "location": (1.0, 2.0, 3.0),
                    "rotation": (0.0, 0.0, 0.0),
                }
            )
        return placements

    def assembly_definition():
        return PartDefinition(
            "assembly",
            "assembly",
            "assembly.step",
            lambda _params: None,
            role=PartRole.INSPECTION,
            version="b3_v2",
            assembly_ids=("b3_v2_wheel_box",),
        )

    project = FlowCadProject(
        root=tmp_path,
        project_id="versioned",
        name="Versioned",
        params_factory=Params,
        part_definitions=iter_part_definitions,
        assembly_placements=get_assembly_placements,
        assembly_definition_factory=assembly_definition,
        paths=ProjectPaths(
            exports=tmp_path / "exports",
            reports=tmp_path / "reports",
            local_state=tmp_path / ".flow",
            cache=tmp_path / ".flow" / "registry.db",
        ),
        docs=ProjectDocs(
            print_manifest=tmp_path / "docs" / "PRINT_MANIFEST.md",
            part_interfaces=tmp_path / "docs" / "PART_INTERFACES.md",
        ),
        validators={},
    )

    payload = ViewerService(project=project).list_parts()
    parts = {part["id"]: part for part in payload["parts"]}

    assert payload["active_version"] == "b3_v2"
    assert payload["active_assembly_id"] == "b3_v2_wheel_box"
    assert payload["versions"] == ["b3_v2", "b3_v1"]
    assert parts["wheel_box_test_body"]["default_visible"] is True
    assert parts["reference_wheel_pair"]["default_visible"] is False
    assert parts["reference_wheel_pair"]["occurrences"][0]["location"] == [1.0, 2.0, 3.0]
    assert len(parts["reference_wheel_pair"]["occurrences"]) == 2
    assert parts["left_side_plate"]["default_visible"] is False
    assert parts["left_side_plate"]["occurrences"][0]["assembly_id"] == "b3_v1_lower_chassis"
    assert parts["left_side_plate"]["occurrences"][0]["location"] == [-10.0, 0.0, 0.0]


def test_viewer_service_serves_direct_stl_when_no_step_exists(tmp_path) -> None:
    stl_path = _write_stl(tmp_path)

    service = ViewerService(tmp_path)
    part = service.list_parts()["parts"][0]
    model_path, source_format = service.model_path("example_block")

    assert part["source_kind"] == "stl"
    assert part["geometry_authority"] == "mesh"
    assert part["quality_label"] == "approximate"
    assert part["capabilities"]["mesh_only"] is True
    assert part["capabilities"]["approximate_measurement"] is True
    assert part["capabilities"]["exact_editing"] is False
    assert part["warnings"]
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

    service.model_path("example_block")
    assert calls == [(step_path, model_path)]

    metadata_path = model_path.with_suffix(".stl.json")
    metadata = json.loads(metadata_path.read_text())
    assert metadata["contract_version"] == DISPLAY_MESH_CONTRACT_VERSION
    metadata["contract_version"] = -1
    metadata_path.write_text(json.dumps(metadata))

    service.model_path("example_block")
    assert calls == [(step_path, model_path), (step_path, model_path)]


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
    assert box_payload["extractor_contract_version"] == SNAP_EXTRACTOR_CONTRACT_VERSION
    assert box_payload["source_format"] == "step"
    assert box_payload["artifact_path"] == "example/exports/step/example/example_block.step"
    assert {feature["kind"] for feature in box_features} >= {"vertex", "line_edge", "edge_midpoint"}
    assert any(feature["label"] == "Line Edge" and feature["length"] == 30.0 for feature in box_features)
    assert all(feature["quality_label"] == "Exact" for feature in box_features)
    assert len({feature["id"] for feature in box_features}) == len(box_features)

    cache_path = tmp_path / "example" / "viewer-cache" / "snap-features" / "example" / "example_block.json"
    cached = json.loads(cache_path.read_text())
    cached["extractor_contract_version"] = -1
    cache_path.write_text(json.dumps(cached))
    service.snap_features("example_block")
    assert json.loads(cache_path.read_text())["extractor_contract_version"] == SNAP_EXTRACTOR_CONTRACT_VERSION

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
    assert any(feature["label"] == "Circle Center" and feature["radius"] == 3.0 for feature in cylinder_features)
    assert not any(feature["label"] == "Hole Center" for feature in cylinder_features)
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
        "warnings": [
            "STL-only mesh: viewing and approximate mesh measurements are available; exact CAD editing is disabled.",
        ],
        "geometry_authority": "mesh",
        "capabilities": {
            "display_mesh": True,
            "mesh_metrics": True,
            "exact_topology": False,
            "exact_snap": False,
            "exact_measurement": False,
            "approximate_measurement": True,
            "exact_editing": False,
            "mesh_only": True,
        },
    }

    _write_step(tmp_path)
    payload = service.snap_features("example_block")

    assert payload["component_id"] == "example_block"
    assert payload["source_format"] == "step"
    assert payload["features"] == []
    assert payload["warnings"]
