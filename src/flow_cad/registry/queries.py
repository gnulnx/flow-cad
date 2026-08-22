"""Read-only part inventory queries."""

from __future__ import annotations

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
            p.uuid, p.key, p.role, p.status, p.material,
            COUNT(a.kind) AS artifact_count,
            COALESCE(SUM(CASE WHEN a.state = 'missing' THEN 1 ELSE 0 END), 0)
                AS missing_artifact_count
        FROM parts p
        LEFT JOIN artifacts a ON a.part_uuid = p.uuid
        {where}
        GROUP BY p.uuid, p.key, p.role, p.status, p.material
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
        artifacts=artifacts,
    )
