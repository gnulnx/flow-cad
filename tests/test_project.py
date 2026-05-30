import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from flow_cad.cli import flow
from flow_cad.core.metadata import PartDefinition
from flow_cad.project import (
    PROJECT_MANIFEST,
    FlowCadProject,
    ProjectDocs,
    ProjectError,
    ProjectPaths,
    bundled_example_project,
    init_project,
    load_project,
)
from flow_cad.viewer.service import ViewerService


def test_init_project_creates_native_project_layout(tmp_path: Path) -> None:
    changed = init_project(tmp_path)

    assert changed
    assert (tmp_path / PROJECT_MANIFEST).exists()
    assert (tmp_path / "flow" / "params.py").exists()
    assert (tmp_path / "flow" / "parts" / "example.py").exists()
    assert (tmp_path / "flow" / "assemblies" / "robot.py").exists()
    assert (tmp_path / "flow" / "validators" / "project.py").exists()
    assert (tmp_path / "skills" / "flow-cad-project" / "SKILL.md").exists()
    assert (tmp_path / ".flow").is_dir()
    assert ".flow/" in (tmp_path / ".gitignore").read_text()


def test_init_project_is_idempotent_and_preserves_source(tmp_path: Path) -> None:
    init_project(tmp_path)
    params_path = tmp_path / "flow" / "params.py"
    params_path.write_text("# custom params\n", encoding="utf-8")

    init_project(tmp_path)

    assert params_path.read_text(encoding="utf-8") == "# custom params\n"


def test_load_project_manifest_uses_project_local_flow_source(tmp_path: Path) -> None:
    init_project(tmp_path)

    project = load_project(tmp_path, fallback_to_bundled=False)
    params = project.make_params()
    definitions = list(project.iter_part_definitions())
    parts = project.build_parts(params)
    placements = list(project.get_assembly_placements(params))

    assert project.project_id == tmp_path.name
    assert params.project_id == tmp_path.name
    assert [definition.id for definition in definitions] == ["example_block"]
    assert "example_block" in parts
    assert placements[0]["part_key"] == "example_block"
    assert project.paths.exports == tmp_path / "exports"
    assert project.paths.cache == tmp_path / ".flow" / "registry.db"
    assert project.docs.print_manifest == tmp_path / "docs" / "PRINT_MANIFEST.md"
    assert project.docs.part_interfaces == tmp_path / "docs" / "PART_INTERFACES.md"
    assert [name for name, _validator in project.iter_validators()] == ["project"]


def test_project_runtime_imports_do_not_load_external_project_modules() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import flow_cad.project, flow_cad.core.exporter; "
                "loaded = [name for name in ('flow_cad.params', 'flow_cad.registry', 'flow_cad.parts') "
                "if name in sys.modules]; "
                "print(','.join(loaded))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == ""


def test_bundled_example_project_uses_generic_runtime_source(tmp_path: Path) -> None:
    project = bundled_example_project(tmp_path)

    assert project.project_id == "flow_example"
    assert project.paths.exports == tmp_path / "example" / "exports"
    assert project.paths.cache == tmp_path / "example" / "registry.db"
    assert project.source_wrapper_files == ()


def test_load_project_falls_back_to_bundled_example_fixture(tmp_path: Path) -> None:
    project = load_project(tmp_path)

    assert project.project_id == "flow_example"
    assert project.root == tmp_path.resolve()


def test_external_project_viewer_service_uses_manifest_outputs(tmp_path: Path) -> None:
    init_project(tmp_path)
    project = load_project(tmp_path, fallback_to_bundled=False)
    step_path = tmp_path / "exports" / "step" / "example" / "example_block.step"
    step_path.parent.mkdir(parents=True)
    step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")

    service = ViewerService(project=project)
    payload = service.list_parts()
    part = payload["parts"][0]

    assert payload["project_id"] == tmp_path.name
    assert part["id"] == "example_block"
    assert part["artifact_path"] == "exports/step/example/example_block.step"
    assert part["occurrences"][0]["location"] == [0.0, 0.0, 0.0]
    assert service.viewer_cache_dir == tmp_path / ".flow" / "viewer-cache"


def test_project_export_paths_can_include_version_and_family(tmp_path: Path) -> None:
    class Params:
        project_id = "versioned"

    def iter_part_definitions(*, include_references: bool = True):
        _ = include_references
        yield PartDefinition(
            "wheel_box_test_body",
            "wheel_box",
            "body.step",
            lambda _params: object(),
            version="b3_v2",
            family="wheel_box",
        )

    def get_assembly_placements(_params, *, include_references: bool = False):
        _ = include_references
        return []

    project = FlowCadProject(
        root=tmp_path,
        project_id="versioned",
        name="Versioned",
        params_factory=Params,
        part_definitions=iter_part_definitions,
        assembly_placements=get_assembly_placements,
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

    assert project.expected_printable_export_relative_paths() == {
        Path("step/b3_v2/wheel_box/body.step"),
        Path("stl/b3_v2/wheel_box/body.stl"),
        Path("snapshots/b3_v2/wheel_box/body_front.svg"),
        Path("snapshots/b3_v2/wheel_box/body_side.svg"),
        Path("snapshots/b3_v2/wheel_box/body_top.svg"),
    }


def test_viewer_reload_reloads_project_placements(tmp_path: Path, monkeypatch) -> None:
    class Params:
        project_id = "reloadable"

    def make_project(location: tuple[float, float, float]) -> FlowCadProject:
        def iter_part_definitions(*, include_references: bool = True):
            _ = include_references
            yield PartDefinition("example_block", "example", "example_block.step", lambda _params: object())

        def get_assembly_placements(_params, *, include_references: bool = False):
            _ = include_references
            return [
                {
                    "name": "example_block",
                    "part_key": "example_block",
                    "location": location,
                    "rotation": (0.0, 0.0, 0.0),
                }
            ]

        return FlowCadProject(
            root=tmp_path,
            project_id="reloadable",
            name="Reloadable",
            params_factory=Params,
            part_definitions=iter_part_definitions,
            assembly_placements=get_assembly_placements,
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

    step_path = tmp_path / "exports" / "step" / "example" / "example_block.step"
    step_path.parent.mkdir(parents=True)
    step_path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="utf-8")
    service = ViewerService(project=make_project((1.0, 2.0, 3.0)))

    before = service.list_parts()["parts"][0]["occurrences"][0]["location"]
    monkeypatch.setattr("flow_cad.viewer.service.load_project", lambda _root: make_project((4.0, 5.0, 6.0)))
    reload_payload = service.reload()
    after = service.list_parts()["parts"][0]["occurrences"][0]["location"]

    assert before == [1.0, 2.0, 3.0]
    assert reload_payload["revision"] == 1
    assert after == [4.0, 5.0, 6.0]


def test_external_project_source_context_resolves_wrapped_part_file(tmp_path: Path) -> None:
    init_project(tmp_path)
    assembly_path = tmp_path / "flow" / "assemblies" / "robot.py"
    assembly_path.write_text(
        """from __future__ import annotations

from flow_cad.core.metadata import PartDefinition
from flow.parts.example import make_example_block


PART_DEFINITIONS = (
    PartDefinition("example_block", "example", "example_block.step", lambda params: make_example_block(params)),
)


def iter_part_definitions(*, include_references: bool = True):
    yield from PART_DEFINITIONS


def get_assembly_placements(_params, *, include_references: bool = False):
    return [
        {
            "name": "example_block",
            "part_key": "example_block",
            "location": (0.0, 0.0, 0.0),
            "rotation": (0.0, 0.0, 0.0),
        }
    ]
""",
        encoding="utf-8",
    )
    project = load_project(tmp_path, fallback_to_bundled=False)

    source = ViewerService(project=project).source_context("example_block")

    assert source["relative_file_path"] == "flow/parts/example.py"
    assert source["symbol"] == "make_example_block"
    assert "def make_example_block" in source["content"]


def test_invalid_project_manifest_reports_missing_entrypoint(tmp_path: Path) -> None:
    init_project(tmp_path)
    manifest = tmp_path / PROJECT_MANIFEST
    manifest.write_text(
        """schema_version: 1
project_id: broken
name: Broken

python:
  source_root: flow
  params: flow.params:ProjectParams
  registry: flow.assemblies.robot:missing_registry
  assembly: flow.assemblies.robot:get_assembly_placements

outputs:
  exports: exports
  reports: reports
  local_state: .flow
  cache: .flow/registry.db
""",
        encoding="utf-8",
    )

    try:
        load_project(tmp_path, fallback_to_bundled=False)
    except ProjectError as exc:
        assert "missing_registry" in str(exc)
        assert "missing attribute" in str(exc)
    else:
        raise AssertionError("Expected ProjectError for an invalid registry entrypoint")


def test_flow_init_cli_creates_project_layout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(flow, ["init"], catch_exceptions=False)

    assert result.exit_code == 0
    assert "Initialized Flow CAD project" in result.output
    assert (tmp_path / PROJECT_MANIFEST).exists()


def test_flow_start_help_is_registered() -> None:
    result = CliRunner().invoke(flow, ["start", "--help"])

    assert result.exit_code == 0
    assert "Start the Flow CAD workbench" in result.output
    assert "--backend-port" in result.output


def test_flow_cad_build_uses_initialized_external_project(tmp_path: Path, monkeypatch) -> None:
    init_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(
        flow,
        ["cad", "build", "--no-bundle", "--no-cache", "--no-snapshots"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "Exported 2 STEP files" in result.output
    assert (tmp_path / "exports" / "step" / "example" / "example_block.step").exists()
    assert (tmp_path / "exports" / "step" / "assembly" / f"{tmp_path.name}_assembly.step").exists()
    assert (tmp_path / "reports" / f"{tmp_path.name}_cad_report.txt").exists()
