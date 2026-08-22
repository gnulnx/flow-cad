"""Metadata-only project and part inventory for the replacement workbench."""

from __future__ import annotations

from collections import defaultdict
from contextlib import closing
from pathlib import Path
from typing import Any

from flow_cad.registry.db import connect_readonly, database_path


_EXACT_CAPABILITIES = {
    "display_model": False,
    "display_mesh": False,
    "mesh_metrics": True,
    "exact_topology": True,
    "exact_snap": True,
    "exact_measurement": True,
    "approximate_measurement": False,
    "exact_editing": False,
    "mesh_only": False,
}
_MESH_CAPABILITIES = {
    "display_model": True,
    "display_mesh": True,
    "mesh_metrics": True,
    "exact_topology": False,
    "exact_snap": False,
    "exact_measurement": False,
    "approximate_measurement": True,
    "exact_editing": False,
    "mesh_only": True,
}
_MISSING_CAPABILITIES = {
    "display_model": False,
    "display_mesh": False,
    "mesh_metrics": False,
    "exact_topology": False,
    "exact_snap": False,
    "exact_measurement": False,
    "approximate_measurement": False,
    "exact_editing": False,
    "mesh_only": False,
}


class InventoryService:
    """Read the disposable SQLite index without loading project Python."""

    def __init__(self, project_root: Path):
        self.project_root = project_root.resolve()
        self.index_path = database_path(self.project_root)

    def project(self) -> dict[str, Any]:
        with closing(connect_readonly(self.index_path)) as connection:
            project = connection.execute(
                """
                SELECT project_id, python_package, manifest_schema_version,
                       manifest_sha256, revision
                FROM projects
                LIMIT 1
                """
            ).fetchone()
            if project is None:
                raise RuntimeError("registry index contains no project row")
            counts = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM parts) AS part_count,
                    (SELECT COUNT(*) FROM assembly_occurrences) AS occurrence_count
                """
            ).fetchone()
        return _project_payload(project, counts)

    def inventory(
        self,
        *,
        include_retired: bool = True,
        search: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        if limit is not None and limit < 0:
            raise ValueError("limit must be non-negative")

        with closing(connect_readonly(self.index_path)) as connection:
            project = connection.execute(
                """
                SELECT project_id, python_package, manifest_schema_version,
                       manifest_sha256, revision
                FROM projects
                LIMIT 1
                """
            ).fetchone()
            if project is None:
                raise RuntimeError("registry index contains no project row")

            clauses: list[str] = []
            parameters: list[object] = []
            if not include_retired:
                clauses.append("p.status != 'retired'")
            if search:
                clauses.append(
                    """(
                        p.key LIKE ? OR EXISTS (
                            SELECT 1 FROM part_aliases pa
                            WHERE pa.part_uuid = p.uuid AND pa.alias LIKE ?
                        )
                    )"""
                )
                pattern = f"%{search}%"
                parameters.extend((pattern, pattern))
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            limit_sql = ""
            if limit is not None:
                limit_sql = " LIMIT ?"
                parameters.append(limit)
            parts = connection.execute(
                f"""
                SELECT p.uuid, p.key, p.generator, p.role, p.status, p.material
                FROM parts p
                {where}
                ORDER BY p.key
                {limit_sql}
                """,
                parameters,
            ).fetchall()
            part_ids = [str(row["uuid"]) for row in parts]
            aliases = _group_rows(
                connection,
                part_ids,
                "SELECT part_uuid, alias FROM part_aliases WHERE part_uuid IN ({}) ORDER BY alias",
            )
            artifacts = _group_rows(
                connection,
                part_ids,
                """
                SELECT part_uuid, kind, relative_path, sha256, byte_count, state
                FROM artifacts WHERE part_uuid IN ({}) ORDER BY kind
                """,
            )
            occurrences = _group_rows(
                connection,
                part_ids,
                """
                SELECT part_uuid, assembly_key, occurrence_id,
                       translation_x_mm, translation_y_mm, translation_z_mm,
                       rotation_x_deg, rotation_y_deg, rotation_z_deg
                FROM assembly_occurrences
                WHERE part_uuid IN ({})
                ORDER BY assembly_key, occurrence_id
                """,
            )
            counts = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM parts) AS part_count,
                    (SELECT COUNT(*) FROM assembly_occurrences) AS occurrence_count
                """
            ).fetchone()

        payload = _project_payload(project, counts)
        payload["parts"] = [
            _part_payload(
                row,
                aliases=aliases.get(str(row["uuid"]), ()),
                artifacts=artifacts.get(str(row["uuid"]), ()),
                occurrences=occurrences.get(str(row["uuid"]), ()),
            )
            for row in parts
        ]
        return payload


def _group_rows(connection, part_ids: list[str], sql: str):
    grouped: dict[str, list[Any]] = defaultdict(list)
    if not part_ids:
        return grouped
    placeholders = ",".join("?" for _ in part_ids)
    for row in connection.execute(sql.format(placeholders), part_ids).fetchall():
        grouped[str(row["part_uuid"])].append(row)
    return grouped


def _project_payload(project, counts) -> dict[str, Any]:
    return {
        "project_id": str(project["project_id"]),
        "python_package": str(project["python_package"]),
        "manifest_schema_version": int(project["manifest_schema_version"]),
        "manifest_sha256": str(project["manifest_sha256"]),
        "revision": int(project["revision"]),
        "part_count": int(counts["part_count"]),
        "occurrence_count": int(counts["occurrence_count"]),
    }


def _part_payload(row, *, aliases, artifacts, occurrences) -> dict[str, Any]:
    artifact_payloads = [
        {
            "kind": str(artifact["kind"]),
            "relative_path": str(artifact["relative_path"]),
            "sha256": str(artifact["sha256"]) if artifact["sha256"] is not None else None,
            "byte_count": int(artifact["byte_count"])
            if artifact["byte_count"] is not None
            else None,
            "state": str(artifact["state"]),
            "content_url": _content_url(artifact),
        }
        for artifact in artifacts
    ]
    exact_artifact = next(
        (
            artifact
            for artifact in artifact_payloads
            if artifact["kind"] == "step"
            and artifact["state"] == "indexed"
            and artifact["sha256"] is not None
        ),
        None,
    )
    display_artifact = next(
        (
            artifact
            for artifact in artifact_payloads
            if artifact["kind"] == "stl"
            and artifact["state"] == "indexed"
            and artifact["sha256"] is not None
        ),
        None,
    )
    warnings: list[str] = []
    if exact_artifact is not None:
        source_kind = "flow_python" if row["generator"] else "step"
        authority = "step_kernel"
        quality = "exact"
        capabilities = dict(_EXACT_CAPABILITIES)
        capabilities["display_model"] = display_artifact is not None
        capabilities["display_mesh"] = display_artifact is not None
        artifact_revision = exact_artifact["sha256"]
        authority_url = exact_artifact["content_url"]
        display_revision = display_artifact["sha256"] if display_artifact else None
        model_url = display_artifact["content_url"] if display_artifact else None
        if display_artifact is None:
            warnings.append(
                "Exact STEP is indexed, but no content-addressed STL display model is available."
            )
    elif display_artifact is not None:
        source_kind = "stl"
        authority = "mesh"
        quality = "approximate"
        capabilities = dict(_MESH_CAPABILITIES)
        artifact_revision = display_artifact["sha256"]
        authority_url = None
        display_revision = display_artifact["sha256"]
        model_url = display_artifact["content_url"]
        warnings.append("STL is mesh-only; exact topology and measurement are unavailable.")
    else:
        source_kind = "missing"
        authority = "missing"
        quality = "missing"
        capabilities = dict(_MISSING_CAPABILITIES)
        artifact_revision = None
        authority_url = None
        display_revision = None
        model_url = None
        warnings.append("No content-addressed STEP artifact is available.")

    return {
        "uuid": str(row["uuid"]),
        "key": str(row["key"]),
        "aliases": [str(alias["alias"]) for alias in aliases],
        "generator": str(row["generator"]),
        "role": str(row["role"]),
        "status": str(row["status"]),
        "material": str(row["material"]) if row["material"] is not None else None,
        "artifacts": artifact_payloads,
        "occurrences": [
            {
                "assembly_key": str(occurrence["assembly_key"]),
                "id": str(occurrence["occurrence_id"]),
                "translation_mm": [
                    float(occurrence["translation_x_mm"]),
                    float(occurrence["translation_y_mm"]),
                    float(occurrence["translation_z_mm"]),
                ],
                "rotation_deg": [
                    float(occurrence["rotation_x_deg"]),
                    float(occurrence["rotation_y_deg"]),
                    float(occurrence["rotation_z_deg"]),
                ],
            }
            for occurrence in occurrences
        ],
        "source_kind": source_kind,
        "geometry_authority": authority,
        "quality_label": quality,
        "capabilities": capabilities,
        "warnings": warnings,
        "artifact_revision": artifact_revision,
        "authority_url": authority_url,
        "display_revision": display_revision,
        "model_url": model_url,
    }


def _content_url(artifact) -> str | None:
    if (
        str(artifact["kind"]) in {"step", "stl"}
        and str(artifact["state"]) == "indexed"
        and artifact["sha256"] is not None
    ):
        return f"/api/models/{artifact['sha256']}"
    return None
