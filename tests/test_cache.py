import json
from dataclasses import fields

from sqlalchemy import inspect
from sqlmodel import Session, select

from flow_cad.core.cache import (
    BuildMetadata,
    ParameterSnapshot,
    create_cache_engine,
    init_cache,
    registry_db_path,
    write_build_metadata,
)
from flow_cad.params import ChassisParams


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
