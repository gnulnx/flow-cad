from dataclasses import dataclass

from click.testing import CliRunner

from flow_cad.cli import flow
from flow_cad.core.cache import write_active_cache
from flow_cad.core.metadata import PartDefinition, PartRole


@dataclass(frozen=True)
class ExampleParams:
    project_id: str = "flow_example"


class _Point:
    def __init__(self, x: float, y: float, z: float):
        self.X = x
        self.Y = y
        self.Z = z


class _BBox:
    def __init__(self):
        self.min = _Point(0.0, 0.0, 0.0)
        self.max = _Point(10.0, 20.0, 30.0)


class _Shape:
    volume = 1234.5

    def bounding_box(self):
        return _BBox()


def _write_sample_cache(project_root):
    params = ExampleParams()
    definition = PartDefinition(
        id="sample_part",
        module_id="lower_chassis",
        filename="sample_part.step",
        factory=lambda _params: _Shape(),
        role=PartRole.PRINTABLE,
    )
    return write_active_cache(
        project_root / "example" / "registry.db",
        project_root=project_root,
        params=params,
        components=[
            (
                definition,
                _Shape(),
                project_root / "example" / "exports" / "step" / "lower_chassis" / "sample_part.step",
            )
        ],
        build_id="build-cli",
        git_commit="abc123",
        is_dirty=False,
    )


def test_registry_list_reports_missing_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("flow_cad.registry_cli.PROJECT_ROOT", tmp_path)

    result = CliRunner().invoke(flow, ["registry", "list"])

    assert result.exit_code != 0
    assert "Active cache not found" in result.output
    assert "flow cad build" in result.output


def test_registry_list_reads_active_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("flow_cad.registry_cli.PROJECT_ROOT", tmp_path)
    _write_sample_cache(tmp_path)

    result = CliRunner().invoke(flow, ["registry", "list"])

    assert result.exit_code == 0
    assert "sample_part" in result.output
    assert "lower_chassis" in result.output
    assert "10.0 x 20.0 x 30.0" in result.output
    assert "Build: build-cli" in result.output


def test_registry_show_reads_component(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("flow_cad.registry_cli.PROJECT_ROOT", tmp_path)
    _write_sample_cache(tmp_path)

    result = CliRunner().invoke(flow, ["registry", "show", "sample_part"])

    assert result.exit_code == 0
    assert "id: sample_part" in result.output
    assert "step_path: example/exports/step/lower_chassis/sample_part.step" in result.output
    assert "volume_mm3: 1234.500" in result.output


def test_registry_show_reports_missing_component(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("flow_cad.registry_cli.PROJECT_ROOT", tmp_path)
    _write_sample_cache(tmp_path)

    result = CliRunner().invoke(flow, ["registry", "show", "missing"])

    assert result.exit_code != 0
    assert "Component not found" in result.output
