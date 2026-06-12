from pathlib import Path
import json
import time

import pytest
from fastapi.testclient import TestClient

from flow_cad.viewer.agent_runtime import CodexExecAgentRuntimeClient
from flow_cad.viewer.app import create_app
from flow_cad.viewer.service import ConversionUnavailableError, ViewerService
from flow_cad.viewer.geometry_authority import DISPLAY_MESH_CONTRACT_VERSION, SNAP_EXTRACTOR_CONTRACT_VERSION
from flow_cad.core.metadata import PartDefinition, PartRole
from flow_cad.project import FlowCadProject, ProjectDocs, ProjectPaths, init_project


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


def _write_box_stl(
    project_root: Path,
    module_id: str = "example",
    filename: str = "example_block.stl",
    *,
    length: float = 20.0,
    width: float = 45.0,
    height: float = 3.0,
) -> Path:
    from build123d import Box, export_stl

    path = _export_path(project_root, "stl", module_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    export_stl(Box(length, width, height), path)
    return path


def _write_build123d_step(project_root: Path, shape) -> Path:
    from build123d import export_step

    path = _export_path(project_root, "step", "example", "example_block.step")
    path.parent.mkdir(parents=True, exist_ok=True)
    export_step(shape, path)
    return path


def test_viewer_service_lists_example_parts_and_prefers_step(tmp_path) -> None:
    step_path = _write_step(tmp_path)
    _write_stl(tmp_path)

    service = ViewerService(tmp_path)
    payload = service.list_parts()
    part = payload["parts"][0]

    assert payload["project_id"] == "flow_example"
    assert part["id"] == "example_block"
    assert part["artifact_format"] == "step"
    assert part["artifact_path"] == "example/exports/step/example/example_block.step"
    assert part["source_step_path"] == "example/exports/step/example/example_block.step"
    assert part["display_stl_cache_path"].endswith("viewer-cache/stl-from-step/example/example_block.stl")
    assert part["artifact_mtime_ns"] == step_path.stat().st_mtime_ns
    assert part["artifact_size"] > 0
    assert len(part["artifact_hash"]) == 64
    assert part["model_url"].startswith("/api/parts/example_block/model?v=")
    assert part["artifact_hash"] in part["model_url"]
    assert part["direct_stl_path"] == "example/exports/stl/example/example_block.stl"
    assert part["source_kind"] == "flow_python"
    assert part["geometry_authority"] == "step_kernel"
    assert part["quality_label"] == "exact"
    assert part["capabilities"]["exact_topology"] is True
    assert part["capabilities"]["exact_snap"] is True
    assert part["capabilities"]["mesh_only"] is False
    assert part["metadata_status"] == "todo"
    assert part["metadata_notes"] == ""
    assert part["warnings"] == []
    assert part["snap_features_url"].startswith("/api/parts/example_block/snap-features?v=")
    assert part["artifact_hash"] in part["snap_features_url"]
    assert part["in_assembly"] is True
    assert part["default_visible"] is True
    assert part["occurrences"] == [
        {
            "name": "example_block",
            "location": [0.0, 0.0, 0.0],
            "rotation": [0.0, 0.0, 0.0],
        }
    ]


def test_viewer_service_model_url_changes_when_artifact_identity_changes(tmp_path) -> None:
    step_path = _write_step(tmp_path)
    service = ViewerService(tmp_path)

    before = service.list_parts()["parts"][0]
    step_path.write_text("ISO-10303-21;\n/* changed */\nEND-ISO-10303-21;\n", encoding="utf-8")
    after = service.list_parts()["parts"][0]

    assert before["id"] == after["id"] == "example_block"
    assert before["artifact_hash"] != after["artifact_hash"]
    assert before["model_url"] != after["model_url"]
    assert before["snap_features_url"] != after["snap_features_url"]


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
            metadata_status="complete",
            metadata_notes="mass and inertia measured",
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
            config=tmp_path / ".flow" / "config.toml",
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
    assert parts["wheel_box_test_body"]["metadata_status"] == "complete"
    assert parts["wheel_box_test_body"]["metadata_notes"] == "mass and inertia measured"
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


def test_viewer_service_imports_loose_step_to_viewer_cache(tmp_path, monkeypatch) -> None:
    calls: list[tuple[Path, Path]] = []

    def converter(source: Path, dest: Path) -> Path:
        calls.append((source, dest))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("solid imported\nendsolid imported\n")
        return dest

    def snap_features(source: Path) -> dict[str, object]:
        return {
            "features": [
                {
                    "id": "vertex:0",
                    "kind": "vertex",
                    "label": "Vertex",
                    "point": [0, 0, 0],
                    "quality": "exact",
                    "quality_label": "Exact",
                }
            ],
            "warnings": [],
        }

    monkeypatch.setattr("flow_cad.viewer.service.extract_step_snap_features", snap_features)
    service = ViewerService(tmp_path, converter=converter)

    payload = service.import_step_file("../loose part.step", b"ISO-10303-21;\nEND-ISO-10303-21;\n")

    assert payload["filename"] == "loose_part.step"
    assert payload["part_id"] == "file:loose_part.step"
    assert payload["source_kind"] == "step"
    assert payload["geometry_authority"] == "step_kernel"
    assert payload["quality_label"] == "exact"
    assert payload["capabilities"]["exact_snap"] is True
    assert payload["snap_features"][0]["id"] == "vertex:0"
    imported_model = service.imported_model_path(payload["import_id"])
    assert imported_model.read_text() == "solid imported\nendsolid imported\n"
    assert calls == [(calls[0][0], imported_model)]
    assert calls[0][0].name == "loose_part.step"
    assert service.viewer_cache_dir in imported_model.parents


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
    assert "/api/imports/model" in route_paths
    assert "/api/imports/{import_id}/model" in route_paths
    assert "/api/parts/{component_id}/model" in route_paths
    assert "/api/parts/{component_id}/source" in route_paths
    assert "/api/parts/{component_id}/preview-context" in route_paths
    assert "/api/preview-commands/panel" in route_paths
    assert "/api/parts/{component_id}/snap-features" in route_paths
    assert "/api/drafts/box" in route_paths
    assert "/api/drafts/{draft_token}/holes" in route_paths
    assert "/api/drafts/{draft_token}/counterbores" in route_paths
    assert "/api/drafts/{draft_token}/slots" in route_paths
    assert "/api/drafts/{draft_token}/mirror-features" in route_paths
    assert "/api/drafts/{draft_token}/measure" in route_paths
    assert "/api/drafts/{draft_token}/export-step" in route_paths
    assert "/api/draft-transactions" in route_paths
    assert "/api/draft-transactions/{transaction_token}/box" in route_paths
    assert "/api/draft-transactions/{transaction_token}/holes" in route_paths
    assert "/api/draft-transactions/{transaction_token}/louver-patterns" in route_paths
    assert "/api/draft-transactions/{transaction_token}/preview" in route_paths
    assert "/api/draft-transactions/{transaction_token}/preview-model" in route_paths
    assert "/api/draft-transactions/{transaction_token}/model" in route_paths
    assert "/api/draft-transactions/{transaction_token}/status" in route_paths
    assert "/api/draft-transactions/{transaction_token}/accept" in route_paths
    assert "/api/design-threads" in route_paths
    assert "/api/design-threads/{thread_id}" in route_paths
    assert "/api/design-threads/{thread_id}/messages" in route_paths
    assert "/api/design-threads/{thread_id}/draft-events" in route_paths
    assert "/api/design-threads/{thread_id}/validator-events" in route_paths
    assert "/api/design-threads/{thread_id}/worker-jobs" in route_paths
    assert "/api/design-threads/{thread_id}/worker-jobs/{job_id}" in route_paths
    assert "/api/design-threads/{thread_id}/worker-jobs/{job_id}/stream" in route_paths
    assert "/api/design-threads/{thread_id}/worker-jobs/{job_id}/cancel" in route_paths
    assert "/api/design-threads/{thread_id}/worker-jobs/{job_id}/commit" in route_paths
    assert "/api/design-threads/{thread_id}/chat" in route_paths
    assert "/api/design-threads/{thread_id}/chat/stream" in route_paths
    assert "/api/design-threads/{thread_id}/context-snapshots" in route_paths
    assert "/api/design-threads/{thread_id}/attachments/viewport-screenshot" in route_paths
    assert "/api/design-threads/{thread_id}/visual-evidence" in route_paths
    assert "/api/design-threads/{thread_id}/visual-evidence-requests" in route_paths
    assert "/api/design-threads/{thread_id}/visual-evidence-requests/{request_id}" in route_paths
    assert "/api/design-threads/{thread_id}/visual-evidence-requests/{request_id}/complete" in route_paths
    assert "/api/design-threads/{thread_id}/visual-evidence-requests/{request_id}/fail" in route_paths
    assert "/api/design-threads/{thread_id}/visual-evidence/{artifact_id}" in route_paths
    assert "/api/design-threads/{thread_id}/visual-evidence/{artifact_id}/image" in route_paths
    assert "/api/agent-screen/capture" in route_paths
    assert "/api/agent-screen/latest" in route_paths
    assert "/api/agent-screen/captures/{capture_id}/image" in route_paths
    assert "/api/agent-screen/requests" in route_paths
    assert "/api/agent-screen/requests/latest" in route_paths
    assert "/api/agent-screen/requests/{request_id}/fail" in route_paths
    assert "/api/reload" in route_paths


def test_viewer_app_stores_agent_screen_capture(tmp_path) -> None:
    init_project(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    missing = client.get("/api/agent-screen/latest")
    assert missing.status_code == 404

    request = client.post(
        "/api/agent-screen/requests",
        json={"request_id": "../screen/request", "purpose": "agent review"},
    )
    assert request.status_code == 200
    assert request.json()["request_id"] == "screen-request"

    capture = client.post(
        "/api/agent-screen/capture",
        json={
            "request_id": request.json()["request_id"],
            "capture_id": "../screen/capture",
            "data_url": (
                "data:image/png;base64,"
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/6X9nSAAAAAASUVORK5CYII="
            ),
            "width": 1,
            "height": 1,
            "selected_ids": ["example_block"],
            "visible_ids": ["example_block"],
            "active_part_id": "example_block",
            "backend_revision": 7,
            "viewport": {"render_context": "viewport-canvas"},
            "metadata": {"source": "test"},
        },
    )
    assert capture.status_code == 200
    payload = capture.json()
    assert payload["capture_id"] == "screen-capture"
    assert payload["kind"] == "agent_screen_capture"
    assert payload["image_url"] == "/api/agent-screen/captures/screen-capture/image"
    assert payload["metadata"]["source"] == "test"

    latest = client.get("/api/agent-screen/latest")
    assert latest.status_code == 200
    assert latest.json()["capture_id"] == "screen-capture"

    image = client.get(payload["image_url"])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content.startswith(b"\x89PNG")

    listed = client.get("/api/agent-screen/requests?status=fulfilled")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["requests"][0]["capture_id"] == "screen-capture"
    assert (tmp_path / ".flow" / "agent-screen" / "screen-capture.png").exists()
    assert not any(path.is_file() for path in (tmp_path / "exports").rglob("*"))


def test_viewer_app_imports_step_and_serves_display_model(tmp_path, monkeypatch) -> None:
    def converter(source: Path, dest: Path) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("solid imported\nendsolid imported\n")
        return dest

    monkeypatch.setattr(
        "flow_cad.viewer.service.extract_step_snap_features",
        lambda _source: {"features": [], "warnings": []},
    )
    service = ViewerService(tmp_path, converter=converter)
    client = TestClient(create_app(service=service))

    response = client.post(
        "/api/imports/model",
        content=b"ISO-10303-21;\nEND-ISO-10303-21;\n",
        headers={"X-Flow-CAD-Filename": "loose.step"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["filename"] == "loose.step"
    assert payload["source_kind"] == "step"
    assert payload["model_url"].startswith(f"/api/imports/{payload['import_id']}/model?v=")
    assert payload["artifact_hash"] in payload["model_url"]
    assert payload["source_artifact_path"].endswith(f"viewer-cache/imports/{payload['import_id']}/loose.step")
    assert payload["artifact_size"] == len(b"ISO-10303-21;\nEND-ISO-10303-21;\n")

    model_response = client.get(payload["model_url"])
    assert model_response.status_code == 200
    assert model_response.headers["x-flow-cad-source-format"] == "step"
    assert model_response.headers["cache-control"] == "no-store"
    assert model_response.headers["pragma"] == "no-cache"
    assert model_response.headers["expires"] == "0"
    assert model_response.text == "solid imported\nendsolid imported\n"


def test_viewer_app_selects_codex_runtime_from_env(tmp_path, monkeypatch) -> None:
    init_project(tmp_path)
    monkeypatch.setenv("FLOW_CAD_AGENT_RUNTIME", "codex")
    monkeypatch.setenv("FLOW_CAD_CODEX_COMMAND", "codex-test")
    monkeypatch.setenv("FLOW_CAD_CODEX_MODEL", "gpt-test")
    monkeypatch.setenv("FLOW_CAD_CODEX_TIMEOUT", "13")

    service = ViewerService(tmp_path)
    app = create_app(service=service)

    runtime = app.state.agent_runtime
    assert isinstance(runtime, CodexExecAgentRuntimeClient)
    assert runtime.project_root == str(tmp_path.resolve())
    assert runtime.codex_command == "codex-test"
    assert runtime.model == "gpt-test"
    assert runtime.request_timeout == 13.0


def test_viewer_health_reports_agent_runtime(tmp_path, monkeypatch) -> None:
    init_project(tmp_path)
    monkeypatch.setenv("FLOW_CAD_AGENT_RUNTIME", "codex")
    monkeypatch.setenv("FLOW_CAD_CODEX_COMMAND", "codex-test")
    monkeypatch.setenv("FLOW_CAD_CODEX_MODEL", "gpt-test")

    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["agent_runtime"] == {
        "class": "CodexExecAgentRuntimeClient",
        "profile_id": "env-codex",
        "profile_label": "Codex",
        "provider": "codex",
        "model": "gpt-test",
        "reasoning": None,
        "command": "codex-test",
        "sandbox": "read-only",
    }
    assert payload["config"]["project_config_path"] == str((tmp_path / ".flow" / "config.toml").resolve())


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


def test_viewer_api_returns_step_part_preview_context(tmp_path) -> None:
    from build123d import Box

    _write_build123d_step(tmp_path, Box(20.0, 45.0, 3.0))
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    response = client.get("/api/parts/example_block/preview-context")
    assert response.status_code == 200
    payload = response.json()

    assert payload["id"] == "example_block"
    assert payload["component_id"] == "example_block"
    assert payload["module_id"] == "example"
    assert payload["geometry_authority"] == "step_kernel"
    assert payload["source_context"]["available"] is True
    assert payload["source_context_available"] is True
    assert payload["source_context"]["symbol"] == "_make_example_block"
    assert payload["snap_feature_summary"]["source_format"] == "step"
    assert payload["snap_feature_summary"]["available"] is True
    assert payload["preview_bounds"]["source_format"] == "stl"
    assert payload["preview_bounds"]["size"][0] == pytest.approx(20.0)
    assert payload["preview_bounds"]["size"][1] == pytest.approx(45.0)
    assert payload["preview_bounds"]["size"][2] == pytest.approx(3.0)
    assert payload["source_measurements"] == {
        "length_mm": pytest.approx(20.0),
        "width_mm": pytest.approx(45.0),
        "height_mm": pytest.approx(3.0),
        "authority": "step_kernel",
        "source": "part",
    }
    assert payload["project_frame"]["axes"]["z_positive"] == "top"
    assert payload["local_frame"]["origin_mm"] == [0.0, 0.0, 0.0]
    assert payload["mating_contracts"]["relative_path"] == "docs/PART_INTERFACES.md"


def test_viewer_api_returns_stl_only_preview_context_with_exact_edit_warning(tmp_path) -> None:
    _write_box_stl(tmp_path, length=20.0, width=45.0, height=3.0)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    response = client.get("/api/parts/example_block/preview-context")
    assert response.status_code == 200
    payload = response.json()

    assert payload["geometry_authority"] == "mesh"
    assert payload["capabilities"]["exact_editing"] is False
    assert any("STL-only mesh" in warning for warning in payload["warnings"])
    assert payload["snap_feature_summary"]["source_format"] == "stl"
    assert payload["preview_bounds"]["size"][0] == pytest.approx(20.0)
    assert payload["preview_bounds"]["size"][1] == pytest.approx(45.0)
    assert payload["preview_bounds"]["size"][2] == pytest.approx(3.0)


def test_viewer_api_returns_preview_context_for_missing_artifact(tmp_path) -> None:
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    response = client.get("/api/parts/example_block/preview-context")
    assert response.status_code == 200
    payload = response.json()

    assert payload["geometry_authority"] == "missing"
    assert payload["artifact_format"] is None
    assert payload["artifact_path"] is None
    assert payload["warnings"] == ["No generated STEP or STL artifact is available. Run `flow cad build` first."]
    assert payload["snap_feature_summary"]["source_format"] is None
    assert payload["preview_bounds"] is None
    assert payload["source_measurements"] is None


def test_viewer_backend_proposes_panel_preview_operations_without_side_effects(tmp_path) -> None:
    from build123d import Box

    init_project(tmp_path)
    _write_build123d_step(tmp_path, Box(120.0, 45.0, 3.0))
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    response = client.post(
        "/api/preview-commands/panel",
        json={
            "part_id": "example_block",
            "command": (
                "Make this a 120 x 45 x 3 mm panel, add two M4 clearance holes 12 mm from "
                "the front edge, and put five louvers on the outside face."
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["part_id"] == "example_block"
    operation_names = [operation["name"] for operation in payload["operations"]]
    assert operation_names.count("create_box") == 1
    assert operation_names.count("add_hole") == 2
    assert operation_names.count("add_louver_pattern") == 1
    assert any("Outside face is ambiguous" in warning for warning in payload["warnings"])
    assert not (tmp_path / ".flow" / "draft-transactions").exists()
    assert not (tmp_path / ".flow" / "drafts").exists()


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


def test_viewer_backend_exposes_draft_panel_operations(tmp_path) -> None:
    init_project(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    create_response = client.post(
        "/api/drafts/box",
        json={
            "part_id": "api_panel",
            "length": 120.0,
            "width": 45.0,
            "height": 3.0,
            "material": "PETG",
            "role": "draft",
        },
    )
    assert create_response.status_code == 200
    draft_token = create_response.json()["draft_token"]

    hole_response = client.post(
        f"/api/drafts/{draft_token}/holes",
        json={"face": "top", "x": 12.0, "y": 8.0, "diameter": 4.2},
    )
    assert hole_response.status_code == 200

    measure_response = client.get(f"/api/drafts/{draft_token}/measure")
    assert measure_response.status_code == 200
    measured = measure_response.json()
    assert measured["bounding_box"]["size"] == [120.0, 45.0, 3.0]
    assert measured["hole_centers"][0]["center"] == [-48.0, -14.5, 0.0]

    mirror_response = client.post(
        f"/api/drafts/{draft_token}/mirror-features",
        json={"source_face": "top", "target_face": "bottom"},
    )
    assert mirror_response.status_code == 200
    mirrored = mirror_response.json()
    assert [feature["face"] for feature in mirrored["feature_list"]] == ["top", "bottom"]
    assert mirrored["hole_centers"][1]["axis"] == [0.0, 0.0, -1.0]

    export_response = client.post(f"/api/drafts/{draft_token}/export-step")
    assert export_response.status_code == 200
    preview_path = Path(export_response.json()["preview_step_path"])
    assert preview_path.exists()
    assert preview_path.is_relative_to(tmp_path / ".flow" / "drafts")


def test_viewer_backend_exposes_draft_transaction_preview_model(tmp_path) -> None:
    init_project(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    begin_response = client.post("/api/draft-transactions", json={"part_id": "api_transaction_panel"})
    assert begin_response.status_code == 200
    transaction_token = begin_response.json()["transaction_token"]

    create_response = client.post(
        f"/api/draft-transactions/{transaction_token}/box",
        json={"length": 120.0, "width": 45.0, "height": 3.0, "material": "PETG"},
    )
    assert create_response.status_code == 200

    hole_response = client.post(
        f"/api/draft-transactions/{transaction_token}/holes",
        json={"face": "top", "x": 12.0, "y": 8.0, "diameter": 4.2},
    )
    assert hole_response.status_code == 200

    preview_response = client.post(f"/api/draft-transactions/{transaction_token}/preview-model")
    assert preview_response.status_code == 200
    payload = preview_response.json()
    assert payload["transaction_token"] == transaction_token
    assert payload["model_url"].startswith(f"/api/draft-transactions/{transaction_token}/model?v=")
    assert payload["artifact_hash"] in payload["model_url"]
    assert payload["part_id"] == "api_transaction_panel"
    assert payload["source_format"] == "step"
    assert payload["artifact_path"].endswith(".step")
    assert payload["artifact_size"] > 0
    assert payload["geometry_authority"] == "step_kernel"
    assert payload["quality_label"] == "exact"
    assert payload["dimensions"] == {
        "length_mm": 120.0,
        "width_mm": 45.0,
        "height_mm": 3.0,
        "authority": "step_kernel",
        "source": "preview",
    }
    assert "Draft features: 1" in payload["facts"]

    display_stl_path = Path(payload["display_stl_path"])
    preview_step_path = Path(payload["preview_step_path"])
    assert payload["source_step_path"] == payload["preview_step_path"]
    assert display_stl_path.exists()
    assert display_stl_path.is_relative_to(tmp_path / ".flow" / "viewer-cache" / "draft-transactions")
    assert not display_stl_path.is_relative_to(tmp_path / "exports")
    assert preview_step_path.exists()
    assert preview_step_path.is_relative_to(tmp_path / ".flow" / "drafts")
    assert not preview_step_path.is_relative_to(tmp_path / "exports")
    assert any(
        cmd.startswith("flow validate run panel-basic --draft-transaction")
        for cmd in payload["source_loop_commands"]
    )
    assert any(cmd.startswith("flow cad build --part") for cmd in payload["source_loop_commands"])


def test_viewer_backend_refreshes_stale_draft_transaction_preview_model(tmp_path) -> None:
    init_project(tmp_path)
    counters = {"calls": 0}

    def converter(source: Path, destination: Path) -> Path:
        counters["calls"] += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(f"solid preview {counters['calls']}\\nendsolid preview\\n")
        return destination

    service = ViewerService(tmp_path, converter=converter)
    client = TestClient(create_app(service=service))

    begin_response = client.post("/api/draft-transactions", json={"part_id": "api_transaction_panel"})
    assert begin_response.status_code == 200
    transaction_token = begin_response.json()["transaction_token"]

    create_response = client.post(
        f"/api/draft-transactions/{transaction_token}/box",
        json={"length": 120.0, "width": 45.0, "height": 3.0, "material": "PETG"},
    )
    assert create_response.status_code == 200

    preview_response = client.post(f"/api/draft-transactions/{transaction_token}/preview-model")
    assert preview_response.status_code == 200
    assert counters["calls"] == 1
    first_payload = preview_response.json()
    first_path = Path(first_payload["display_stl_path"])
    first_content = first_path.read_text()

    hole_response = client.post(
        f"/api/draft-transactions/{transaction_token}/holes",
        json={"face": "top", "x": 12.0, "y": 8.0, "diameter": 4.2},
    )
    assert hole_response.status_code == 200

    second_preview = client.post(f"/api/draft-transactions/{transaction_token}/preview-model")
    assert second_preview.status_code == 200
    assert counters["calls"] == 2
    second_payload = second_preview.json()
    assert second_payload["display_stl_path"] == first_payload["display_stl_path"]
    assert first_path.read_text() != first_content


def test_viewer_backend_exposes_draft_transaction_workflow(tmp_path) -> None:
    init_project(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    begin_response = client.post("/api/draft-transactions", json={"part_id": "api_transaction_panel"})
    assert begin_response.status_code == 200
    transaction_token = begin_response.json()["transaction_token"]

    create_response = client.post(
        f"/api/draft-transactions/{transaction_token}/box",
        json={"length": 120.0, "width": 45.0, "height": 3.0, "material": "PETG"},
    )
    assert create_response.status_code == 200

    hole_response = client.post(
        f"/api/draft-transactions/{transaction_token}/holes",
        json={"face": "top", "x": 12.0, "y": 8.0, "diameter": 4.2},
    )
    assert hole_response.status_code == 200

    wall_response = client.post(
        f"/api/draft-transactions/{transaction_token}/raised-walls",
        json={"face": "top", "x": 60.0, "y": 22.5, "length": 30.0, "width": 8.0, "height": 12.0},
    )
    assert wall_response.status_code == 200
    wall_features = [
        feature
        for feature in wall_response.json()["draft"]["feature_list"]
        if feature["kind"] == "raised_wall"
    ]
    assert wall_features[0]["height"] == 12.0

    preview_response = client.post(f"/api/draft-transactions/{transaction_token}/preview")
    assert preview_response.status_code == 200
    preview_path = Path(preview_response.json()["preview_step_path"])
    assert preview_path.exists()
    assert preview_path.is_relative_to(tmp_path / ".flow" / "drafts")

    accept_response = client.post(f"/api/draft-transactions/{transaction_token}/accept")
    assert accept_response.status_code == 200
    accepted = accept_response.json()
    source_patch_path = Path(accepted["source_patch_path"])
    assert accepted["status"] == "accepted"
    assert source_patch_path.exists()
    assert source_patch_path.is_relative_to(tmp_path / ".flow" / "draft-transactions")
    assert not (tmp_path / "flow" / "parts" / "api_transaction_panel.py").exists()
    assert not any(path.is_file() for path in (tmp_path / "exports").rglob("*"))

    status_response = client.get(f"/api/draft-transactions/{transaction_token}/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["status"] == "accepted"
    assert status_payload["generated_source_path"] == accepted["generated_source_path"]
    assert "part = part + Box" in Path(accepted["generated_source_path"]).read_text(encoding="utf-8")
    assert "diff --git a/flow/parts/api_transaction_panel.py" in status_payload["source_patch_preview"]
    assert any("flow validate run panel-basic --draft-transaction" in cmd for cmd in status_payload["source_loop_commands"])
    assert any("--part api_transaction_panel" in cmd for cmd in status_payload["source_loop_commands"])


def test_viewer_backend_exposes_draft_transaction_profile_workflow(tmp_path) -> None:
    init_project(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    begun = client.post("/api/draft-transactions", json={"part_id": "api_sketch_profile"})
    assert begun.status_code == 200
    transaction_token = begun.json()["transaction_token"]
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

    created = client.post(
        f"/api/draft-transactions/{transaction_token}/profile",
        json={
            "part_id": "api_sketch_profile",
            "length": 100.0,
            "width": 65.0,
            "height": 10.0,
            "profile_points": profile_points,
        },
    )
    assert created.status_code == 200
    assert created.json()["draft"]["profile_points"] == profile_points

    hole = client.post(
        f"/api/draft-transactions/{transaction_token}/holes",
        json={"face": "top", "x": 25.0, "y": 32.5, "diameter": 4.0},
    )
    assert hole.status_code == 200
    preview = client.post(f"/api/draft-transactions/{transaction_token}/preview-model")
    assert preview.status_code == 200
    payload = preview.json()
    assert payload["part_id"] == "api_sketch_profile"
    assert payload["draft"]["profile_points"] == profile_points
    assert payload["draft"]["feature_list"][0]["kind"] == "hole"
    assert payload["dimensions"]["length_mm"] == 100.0


def test_viewer_backend_exposes_draft_operation_registry(tmp_path) -> None:
    init_project(tmp_path)
    service = ViewerService(tmp_path)
    client = TestClient(create_app(service=service))

    payload = service.draft_operation_registry()
    response = client.get("/api/draft-operation-registry")

    assert response.status_code == 200
    api_payload = response.json()
    assert api_payload == payload
    operations = {operation["id"]: operation for operation in api_payload["operations"]}
    assert api_payload["source"] == "flow_cad.draft_operations"
    assert operations["add_hole"]["endpoint_slug"] == "holes"
    assert operations["create_sketch_profile"]["endpoint_slug"] == "profile"
    assert operations["create_sketch_profile"]["transaction_tool_name"] == "draft_transaction_create_profile"
    assert operations["create_sketch_profile"]["supports_source_emission"] is True
    assert operations["add_counterbore"]["transaction_tool_name"] == "draft_transaction_add_counterbore"
    assert operations["add_raised_wall"]["feature_kind"] == "raised_wall"
    assert operations["add_raised_wall"]["supports_preview"] is True
    assert operations["add_raised_wall"]["supports_source_emission"] is True
    assert not any(path.is_file() for path in (tmp_path / "exports").rglob("*"))
