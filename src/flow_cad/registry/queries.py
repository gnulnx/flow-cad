"""Read-only part inventory queries."""

from __future__ import annotations

import json
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

from .db import connect_readonly, database_path


@dataclass(frozen=True, slots=True)
class PartSummary:
    uuid: str
    key: str
    role: str
    status: str
    material: str | None
    family: str | None
    version: str | None
    artifact_count: int
    missing_artifact_count: int


@dataclass(frozen=True, slots=True)
class PartDetail:
    uuid: str
    key: str
    aliases: tuple[str, ...]
    generator: str
    role: str
    status: str
    material: str | None
    family: str | None
    version: str | None
    compatible_versions: tuple[str, ...]
    shell_count: int | None
    infill_density: float | None
    mass_kg: float | None
    center_of_mass_mm: tuple[float, float, float] | None
    inertia_kg_m2: tuple[float, float, float, float, float, float] | None
    mass_source: str | None
    metadata_status: str | None
    metadata_notes: str | None
    artifacts: tuple[tuple[str, str, str], ...]


def list_parts(
    project_root: Path,
    *,
    include_retired: bool = True,
    search: str | None = None,
    limit: int | None = None,
) -> tuple[PartSummary, ...]:
    clauses: list[str] = []
    parameters: list[object] = []
    if not include_retired:
        clauses.append("p.status != 'retired'")
    if search:
        clauses.append("(p.key LIKE ? OR EXISTS (SELECT 1 FROM part_aliases pa WHERE pa.part_uuid = p.uuid AND pa.alias LIKE ?))")
        pattern = f"%{search}%"
        parameters.extend((pattern, pattern))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_sql = ""
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        limit_sql = " LIMIT ?"
        parameters.append(limit)
    sql = f"""
        SELECT
            p.uuid, p.key, p.role, p.status, p.material, p.family, p.version,
            COUNT(a.kind) AS artifact_count,
            COALESCE(SUM(CASE WHEN a.state = 'missing' THEN 1 ELSE 0 END), 0)
                AS missing_artifact_count
        FROM parts p
        LEFT JOIN artifacts a ON a.part_uuid = p.uuid
        {where}
        GROUP BY p.uuid, p.key, p.role, p.status, p.material, p.family, p.version
        ORDER BY p.key
        {limit_sql}
    """
    with closing(connect_readonly(database_path(project_root))) as connection:
        rows = connection.execute(sql, parameters).fetchall()
    return tuple(
        PartSummary(
            uuid=str(row["uuid"]),
            key=str(row["key"]),
            role=str(row["role"]),
            status=str(row["status"]),
            material=str(row["material"]) if row["material"] is not None else None,
            family=str(row["family"]) if row["family"] is not None else None,
            version=str(row["version"]) if row["version"] is not None else None,
            artifact_count=int(row["artifact_count"]),
            missing_artifact_count=int(row["missing_artifact_count"]),
        )
        for row in rows
    )


def get_part(project_root: Path, key_or_alias: str) -> PartDetail | None:
    with closing(connect_readonly(database_path(project_root))) as connection:
        row = connection.execute(
            """
            SELECT DISTINCT p.*
            FROM parts p
            LEFT JOIN part_aliases pa ON pa.part_uuid = p.uuid
            WHERE p.key = ? OR pa.alias = ?
            """,
            (key_or_alias, key_or_alias),
        ).fetchone()
        if row is None:
            return None
        aliases = tuple(
            str(value["alias"])
            for value in connection.execute(
                "SELECT alias FROM part_aliases WHERE part_uuid = ? ORDER BY alias",
                (row["uuid"],),
            ).fetchall()
        )
        artifacts = tuple(
            (str(value["kind"]), str(value["relative_path"]), str(value["state"]))
            for value in connection.execute(
                """
                SELECT kind, relative_path, state
                FROM artifacts WHERE part_uuid = ? ORDER BY kind
                """,
                (row["uuid"],),
            ).fetchall()
        )
    return PartDetail(
        uuid=str(row["uuid"]),
        key=str(row["key"]),
        aliases=aliases,
        generator=str(row["generator"]),
        role=str(row["role"]),
        status=str(row["status"]),
        material=str(row["material"]) if row["material"] is not None else None,
        family=str(row["family"]) if row["family"] is not None else None,
        version=str(row["version"]) if row["version"] is not None else None,
        compatible_versions=tuple(json.loads(str(row["compatible_versions_json"]))),
        shell_count=int(row["shell_count"]) if row["shell_count"] is not None else None,
        infill_density=float(row["infill_density"])
        if row["infill_density"] is not None
        else None,
        mass_kg=float(row["mass_kg"]) if row["mass_kg"] is not None else None,
        center_of_mass_mm=_tuple_or_none(row["center_of_mass_mm_json"], 3),
        inertia_kg_m2=_tuple_or_none(row["inertia_kg_m2_json"], 6),
        mass_source=str(row["mass_source"]) if row["mass_source"] is not None else None,
        metadata_status=str(row["metadata_status"])
        if row["metadata_status"] is not None
        else None,
        metadata_notes=str(row["metadata_notes"])
        if row["metadata_notes"] is not None
        else None,
        artifacts=artifacts,
    )


def _tuple_or_none(value: object, expected_length: int):
    if value is None:
        return None
    decoded = tuple(float(component) for component in json.loads(str(value)))
    if len(decoded) != expected_length:
        raise ValueError(f"indexed metadata vector has {len(decoded)} components")
    return decoded
