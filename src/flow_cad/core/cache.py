from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Field, SQLModel, Session, create_engine, select

from flow_cad.core.metadata import PartDefinition


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


def registry_db_path(project_root: Path, params: Any) -> Path:
    return project_root / params.project_id / "registry.db"


def create_cache_engine(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_cache(db_path: Path) -> None:
    engine = create_cache_engine(db_path)
    SQLModel.metadata.create_all(engine)


def params_as_json(params: Any) -> str:
    return json.dumps(asdict(params), sort_keys=True)


def _json_value(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


def write_build_metadata(
    db_path: Path,
    *,
    build_id: str,
    params: Any,
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


def get_component_cache(db_path: Path, component_id: str) -> ComponentCache | None:
    engine = create_cache_engine(db_path)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        return session.get(ComponentCache, component_id)


def latest_build_metadata(db_path: Path) -> BuildMetadata | None:
    engine = create_cache_engine(db_path)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        return session.exec(select(BuildMetadata).order_by(BuildMetadata.compiled_at.desc()).limit(1)).first()


def new_build_id() -> str:
    return uuid4().hex


def git_state(project_root: Path) -> tuple[str | None, bool]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=project_root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return commit, bool(status.strip())
    except (OSError, subprocess.CalledProcessError):
        return None, True


def bbox_dimensions(shape) -> tuple[float, float, float]:
    bbox = shape.bounding_box()
    return (
        float(bbox.max.X - bbox.min.X),
        float(bbox.max.Y - bbox.min.Y),
        float(bbox.max.Z - bbox.min.Z),
    )


def shape_volume(shape) -> float:
    try:
        return float(shape.volume or 0.0)
    except Exception:
        return 0.0


def _relative_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def write_active_cache(
    db_path: Path,
    *,
    project_root: Path,
    params: Any,
    components: list[tuple[PartDefinition, object, Path]],
    build_id: str | None = None,
    git_commit: str | None = None,
    is_dirty: bool | None = None,
    compiled_at: datetime | None = None,
) -> str:
    engine = create_cache_engine(db_path)
    SQLModel.metadata.create_all(engine)

    resolved_build_id = build_id or new_build_id()
    resolved_compiled_at = compiled_at or utc_now()
    if git_commit is None or is_dirty is None:
        detected_commit, detected_dirty = git_state(project_root)
        git_commit = detected_commit if git_commit is None else git_commit
        is_dirty = detected_dirty if is_dirty is None else is_dirty

    with Session(engine) as session:
        metadata = BuildMetadata(
            build_id=resolved_build_id,
            git_commit=git_commit,
            is_dirty=bool(is_dirty),
            parameters_json=params_as_json(params),
            compiled_at=resolved_compiled_at,
        )
        session.merge(metadata)

        for name, value in asdict(params).items():
            session.merge(ParameterSnapshot(build_id=resolved_build_id, name=name, value_json=_json_value(value)))

        for existing in session.exec(select(ComponentCache)).all():
            session.delete(existing)
        session.flush()

        for definition, shape, step_path in components:
            bbox_x, bbox_y, bbox_z = bbox_dimensions(shape)
            session.add(
                ComponentCache(
                    id=definition.id,
                    module_id=definition.module_id,
                    role=str(definition.role),
                    step_path=_relative_path(step_path, project_root),
                    volume_mm3=shape_volume(shape),
                    bbox_x=bbox_x,
                    bbox_y=bbox_y,
                    bbox_z=bbox_z,
                    compiled_at=resolved_compiled_at,
                    build_id=resolved_build_id,
                )
            )
        session.commit()
    return resolved_build_id
