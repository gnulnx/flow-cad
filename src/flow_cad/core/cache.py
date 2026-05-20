from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlmodel import Field, SQLModel, Session, create_engine, select

from flow_cad.params import ChassisParams


def utc_now() -> datetime:
    return datetime.now(UTC)


class ComponentCache(SQLModel, table=True):
    id: str = Field(primary_key=True)
    module_id: str
    role: str
    step_path: str
    volume_mm3: float
    bbox_x: float
    bbox_y: float
    bbox_z: float
    compiled_at: datetime
    build_id: str = Field(index=True)


class BuildMetadata(SQLModel, table=True):
    build_id: str = Field(primary_key=True)
    git_commit: str | None = Field(default=None)
    is_dirty: bool
    parameters_json: str
    compiled_at: datetime


class ParameterSnapshot(SQLModel, table=True):
    build_id: str = Field(primary_key=True)
    name: str = Field(primary_key=True)
    value_json: str


def registry_db_path(project_root: Path, params: ChassisParams) -> Path:
    return project_root / params.project_id / "registry.db"


def create_cache_engine(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_cache(db_path: Path) -> None:
    engine = create_cache_engine(db_path)
    SQLModel.metadata.create_all(engine)


def params_as_json(params: ChassisParams) -> str:
    return json.dumps(asdict(params), sort_keys=True)


def _json_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def write_build_metadata(
    db_path: Path,
    *,
    build_id: str,
    params: ChassisParams,
    git_commit: str | None,
    is_dirty: bool,
    compiled_at: datetime | None = None,
) -> None:
    engine = create_cache_engine(db_path)
    SQLModel.metadata.create_all(engine)
    timestamp = compiled_at or utc_now()
    param_values = asdict(params)
    metadata = BuildMetadata(
        build_id=build_id,
        git_commit=git_commit,
        is_dirty=is_dirty,
        parameters_json=json.dumps(param_values, sort_keys=True),
        compiled_at=timestamp,
    )
    snapshots = [
        ParameterSnapshot(build_id=build_id, name=name, value_json=_json_value(value))
        for name, value in param_values.items()
    ]
    with Session(engine) as session:
        session.merge(metadata)
        for snapshot in snapshots:
            session.merge(snapshot)
        session.commit()


def list_component_cache(db_path: Path) -> list[ComponentCache]:
    engine = create_cache_engine(db_path)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        return list(session.exec(select(ComponentCache).order_by(ComponentCache.module_id, ComponentCache.id)))
