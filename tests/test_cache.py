import json
from dataclasses import fields

from sqlalchemy import inspect
from sqlmodel import Session, select

from flow_cad.core.cache import (
    BuildMetadata,
    ComponentCache,
    ParameterSnapshot,
    create_cache_engine,
    get_component_cache,
    init_cache,
    latest_build_metadata,
    list_component_cache,
    registry_db_path,
    write_active_cache,
    write_build_metadata,
)
from flow_cad.params import ChassisParams
from flow_cad.registry import PartDefinition, PartRole


class _Point:
    def __init__(self, x: float, y: float, z: float):
        self.X = x
        self.Y = y
        self.Z = z


class _BBox:
    def __init__(self):
        self.min = _Point(0.0, 0.0, 0.0)
        self.max = _Point(1.0, 2.0, 3.0)


class _Shape:
    volume = 42.0

    def bounding_box(self):
        return _BBox()


def test_registry_db_path_uses_project_namespace(tmp_path) -> None:
    params = ChassisParams(project_id="test_project")

    assert registry_db_path(tmp_path, params) == tmp_path / "test_project" / "registry.db"


def test_init_cache_creates_sqlmodel_tables(tmp_path) -> None:
    db_path = tmp_path / "b3" / "registry.db"

    init_cache(db_path)

    engine = create_cache_engine(db_path)
    table_names = set(inspect(engine).get_table_names())

    assert {"componentcache", "buildmetadata", "parametersnapshot"} <= table_names


def test_write_build_metadata_snapshots_params(tmp_path) -> None:
    params = ChassisParams()
    db_path = tmp_path / params.project_id / "registry.db"

    write_build_metadata(
        db_path,
        build_id="build-1",
        params=params,
        git_commit="abc123",
        is_dirty=True,
    )

    engine = create_cache_engine(db_path)
    with Session(engine) as session:
        metadata = session.get(BuildMetadata, "build-1")
        assert metadata is not None
        assert metadata.git_commit == "abc123"
        assert metadata.is_dirty is True
        assert json.loads(metadata.parameters_json)["project_id"] == params.project_id

        snapshots = session.exec(select(ParameterSnapshot).where(ParameterSnapshot.build_id == "build-1")).all()
        snapshot_names = {snapshot.name for snapshot in snapshots}

    assert snapshot_names == {field.name for field in fields(ChassisParams)}


def test_write_active_cache_upserts_current_component_snapshot(tmp_path) -> None:
    params = ChassisParams()
    db_path = tmp_path / params.project_id / "registry.db"
    definition = PartDefinition(
        id="sample",
        module_id="module",
        filename="sample.step",
        factory=lambda _params: _Shape(),
        role=PartRole.PRINTABLE,
    )

    build_id = write_active_cache(
        db_path,
        project_root=tmp_path,
        params=params,
        components=[(definition, _Shape(), tmp_path / params.project_id / "exports" / "step" / "module" / "sample.step")],
        build_id="build-2",
        git_commit="def456",
        is_dirty=False,
    )

    assert build_id == "build-2"
    engine = create_cache_engine(db_path)
    with Session(engine) as session:
        component = session.get(ComponentCache, "sample")
        metadata = session.get(BuildMetadata, "build-2")

    assert component is not None
    assert component.module_id == "module"
    assert component.role == "printable"
    assert component.step_path == "b3/exports/step/module/sample.step"
    assert component.volume_mm3 == 42.0
    assert (component.bbox_x, component.bbox_y, component.bbox_z) == (1.0, 2.0, 3.0)
    assert component.build_id == "build-2"
    assert metadata is not None
    assert metadata.git_commit == "def456"
    assert metadata.is_dirty is False

    listed = list_component_cache(db_path)
    assert [row.id for row in listed] == ["sample"]
    assert get_component_cache(db_path, "sample") is not None
    assert get_component_cache(db_path, "missing") is None
    latest = latest_build_metadata(db_path)
    assert latest is not None
    assert latest.build_id == "build-2"
