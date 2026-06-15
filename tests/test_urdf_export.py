from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from build123d import Box
from click.testing import CliRunner
from fastapi.testclient import TestClient

from flow_cad.cli import flow
from flow_cad.core.metadata import PartDefinition, PartRole
from flow_cad.project import FlowCadProject, ProjectDocs, ProjectPaths, init_project, load_project
from flow_cad.urdf_export import (
    UrdfExportError,
    UrdfExportService,
    UrdfExportTarget,
    compute_assembly_mass_properties,
)
from flow_cad.viewer.app import create_app
from flow_cad.viewer.service import ViewerService


class Params:
    project_id = "mass_test"


def _project(
    tmp_path: Path,
    *,
    definitions: tuple[PartDefinition, ...],
    placements: tuple[dict[str, object], ...],
    urdf_targets=None,
) -> FlowCadProject:
    def iter_part_definitions(*, include_references: bool = True):
        for definition in definitions:
            if include_references or definition.role != PartRole.REFERENCE:
                yield definition

    def get_assembly_placements(_params, *, include_references: bool = False, assembly_id: str | None = None):
        _ = include_references, assembly_id
        return list(placements)

    return FlowCadProject(
        root=tmp_path,
        project_id="mass_test",
        name="Mass Test",
        params_factory=Params,
        part_definitions=iter_part_definitions,
        assembly_placements=get_assembly_placements,
        urdf_targets_factory=urdf_targets,
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


def test_mass_properties_use_explicit_and_geometry_estimated_com(tmp_path: Path) -> None:
    definitions = (
        PartDefinition(
            "explicit",
            "test",
            "explicit.step",
            lambda _params: Box(2, 2, 2),
            mass_kg=2.0,
            center_of_mass_mm=(1.0, 0.0, 0.0),
            mass_source="measured_scale",
        ),
        PartDefinition(
            "estimated",
            "test",
            "estimated.step",
            lambda _params: Box(2, 2, 2),
            mass_kg=2.0,
            mass_source="estimated_material",
        ),
        PartDefinition("missing", "test", "missing.step", lambda _params: Box(2, 2, 2)),
    )
    placements = (
        {"name": "explicit_occ", "part_key": "explicit", "location": (10.0, 0.0, 0.0), "rotation": (0.0, 0.0, 90.0)},
        {"name": "estimated_occ", "part_key": "estimated", "location": (0.0, 0.0, 10.0), "rotation": (0.0, 0.0, 0.0)},
        {"name": "missing_occ", "part_key": "missing", "location": (0.0, 0.0, 0.0), "rotation": (0.0, 0.0, 0.0)},
    )
    project = _project(tmp_path, definitions=definitions, placements=placements)

    mass = compute_assembly_mass_properties(project, project.make_params())

    assert mass.total_mass_kg == pytest.approx(4.0)
    assert mass.center_of_mass_mm == pytest.approx((5.0, 0.5, 5.0))
    assert mass.known_mass_occurrence_count == 2
    assert mass.total_occurrence_count == 3
    assert mass.missing_mass_occurrences == ("missing_occ:missing",)
    assert mass.missing_inertia_occurrences == ("explicit_occ:explicit", "estimated_occ:estimated")
    contributions = {item.part_id: item for item in mass.contributions}
    assert contributions["explicit"].center_source == "explicit_metadata"
    assert contributions["estimated"].center_source == "geometry_estimate"


def test_urdf_export_validates_paths_and_overwrite(tmp_path: Path) -> None:
    output_dir = tmp_path / "urdf"
    output_dir.mkdir()
    output_path = output_dir / "robot.urdf"
    output_path.write_text("<robot name='existing'><link name='base_link'/></robot>", encoding="utf-8")

    def targets(params=None):
        _ = params
        yield UrdfExportTarget("dojo", default_output_path=output_path)

    project = _project(
        tmp_path,
        definitions=(PartDefinition("body", "test", "body.step", lambda _params: Box(2, 2, 2), mass_kg=1.0),),
        placements=({"name": "body", "part_key": "body", "location": (0.0, 0.0, 0.0), "rotation": (0.0, 0.0, 0.0)},),
        urdf_targets=targets,
    )
    service = UrdfExportService(project)

    with pytest.raises(UrdfExportError, match="already exists"):
        service.export(target_name="dojo")
    with pytest.raises(UrdfExportError, match="must end with .urdf"):
        service.export(target_name="dojo", output_path=output_dir / "robot.xml", overwrite=True)
    with pytest.raises(UrdfExportError, match="parent directory does not exist"):
        service.export(target_name="dojo", output_path=tmp_path / "missing" / "robot.urdf", overwrite=True)


def test_urdf_export_writes_dojo_template_and_report(tmp_path: Path) -> None:
    output_dir = tmp_path / "urdf"
    output_dir.mkdir()
    output_path = output_dir / "robot.urdf"

    definitions = (
        PartDefinition("body", "test", "body.step", lambda _params: Box(100, 60, 80), mass_kg=4.0),
        PartDefinition(
            "reference_wheel",
            "reference",
            "wheel.step",
            lambda _params: Box(10, 10, 10),
            role=PartRole.REFERENCE,
            mass_kg=1.5,
        ),
    )
    placements = (
        {"name": "body", "part_key": "body", "location": (0.0, 0.0, 40.0), "rotation": (0.0, 0.0, 0.0)},
        {"name": "left_reference_wheel", "part_key": "reference_wheel", "location": (-120.0, 0.0, 0.0), "rotation": (0.0, 0.0, 0.0)},
        {"name": "right_reference_wheel", "part_key": "reference_wheel", "location": (120.0, 0.0, 0.0), "rotation": (0.0, 0.0, 0.0)},
    )

    def targets(params=None):
        _ = params
        yield UrdfExportTarget("dojo", default_output_path=output_path, robot_name="test_bot")

    service = UrdfExportService(_project(tmp_path, definitions=definitions, placements=placements, urdf_targets=targets))

    result = service.export(target_name="dojo")

    assert Path(result["output_path"]) == output_path
    assert Path(result["report_path"]).exists()
    root = ET.fromstring(output_path.read_text(encoding="utf-8"))
    assert root.attrib["name"] == "test_bot"
    assert root.find(".//joint[@name='left_wheel_joint']") is not None
    assert root.find(".//joint[@name='right_wheel_joint']") is not None
    xml_text = output_path.read_text(encoding="utf-8")
    assert "{CHASSIS_MASS}" in xml_text
    assert "{COM_X}" in xml_text
    report = json.loads(Path(result["report_path"]).read_text(encoding="utf-8"))
    assert report["wheel_base_m"] == pytest.approx(0.24)
    assert report["mass_properties"]["missing_inertia_occurrences"]
    assert report["recommended_dojo_config"]["embodiment"]["wheel_base_m"] == pytest.approx(0.24)


def test_urdf_export_api_lists_targets_and_writes_file(tmp_path: Path) -> None:
    output_dir = tmp_path / "urdf"
    output_dir.mkdir()
    output_path = output_dir / "robot.urdf"

    definitions = (
        PartDefinition("body", "test", "body.step", lambda _params: Box(20, 20, 20), mass_kg=1.0),
    )
    placements = (
        {"name": "body", "part_key": "body", "location": (0.0, 0.0, 0.0), "rotation": (0.0, 0.0, 0.0)},
    )

    def targets(params=None):
        _ = params
        yield UrdfExportTarget("dojo", label="Dojo", default_output_path=output_path)

    project = _project(tmp_path, definitions=definitions, placements=placements, urdf_targets=targets)
    client = TestClient(create_app(service=ViewerService(project=project)))

    listed = client.get("/api/exports/urdf/targets")
    assert listed.status_code == 200
    assert listed.json()["targets"][0]["name"] == "dojo"
    assert listed.json()["targets"][0]["default_output_path"] == str(output_path)

    written = client.post(
        "/api/exports/urdf",
        json={"target": "dojo", "output_path": str(output_path), "overwrite": False},
    )
    assert written.status_code == 200
    payload = written.json()
    assert payload["ok"] is True
    assert Path(payload["output_path"]) == output_path
    assert Path(payload["report_path"]).exists()
    assert output_path.exists()


def test_cli_urdf_uses_project_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    init_project(tmp_path)
    manifest = tmp_path / "flowcad.project.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "  assembly: flow.assemblies.robot:get_assembly_placements\n",
            "  assembly: flow.assemblies.robot:get_assembly_placements\n  urdf_targets: flow.urdf:iter_urdf_targets\n",
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "assets"
    output_dir.mkdir()
    (tmp_path / "flow" / "urdf.py").write_text(
        f"""from flow_cad.urdf_export import UrdfExportTarget


def iter_urdf_targets(params=None):
    yield UrdfExportTarget("dojo", default_output_path=r"{output_dir / 'robot.urdf'}")
""",
        encoding="utf-8",
    )
    project = load_project(tmp_path, fallback_to_bundled=False)
    assert [target.name for target in project.iter_urdf_targets(params=project.make_params())] == ["dojo"]

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(flow, ["cad", "urdf", "--target", "dojo"], catch_exceptions=False)

    assert result.exit_code == 0
    assert (output_dir / "robot.urdf").exists()
    assert "Wrote URDF to" in result.output
