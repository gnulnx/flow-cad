from __future__ import annotations

import shutil
import sqlite3
import sys
import time
from pathlib import Path
from uuid import UUID

from flow_cad.registry import get_part, list_parts, sync_project
from flow_cad.registry.db import database_path
from flow_cad.sdk import (
    ArtifactSpec,
    MassProperties,
    ManifestPart,
    PartRole,
    PartStatus,
    PrintSpec,
    ProjectManifest,
    dump_manifest,
)


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "projects"


def _copy_fixture(tmp_path: Path, name: str = "minimal_alpha") -> Path:
    root = tmp_path / name
    shutil.copytree(FIXTURES / name, root)
    return root


def test_sync_builds_all_contract_tables_without_importing_geometry(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)

    result = sync_project(root)

    assert result.changed
    assert result.part_count == 1
    assert result.occurrence_count == 1
    assert "minimal_alpha.parts" not in sys.modules
    with sqlite3.connect(result.database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "projects",
        "parts",
        "part_aliases",
        "source_definitions",
        "assembly_occurrences",
        "assembly_artifacts",
        "builds",
        "build_jobs",
        "artifacts",
        "artifact_dependencies",
        "validation_results",
        "thread_summaries",
    } <= tables


def test_sync_is_idempotent_and_reconstructs_a_deleted_index(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)

    first = sync_project(root)
    second = sync_project(root)
    first.database_path.unlink()
    rebuilt = sync_project(root)

    assert first.changed
    assert not second.changed
    assert second.revision == first.revision
    assert rebuilt.changed
    assert rebuilt.revision == 1
    assert [part.key for part in list_parts(root)] == ["alpha_panel"]


def test_sync_content_indexes_existing_undeclared_artifacts(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    artifact_path = root / "exports/step/alpha_panel.step"
    artifact_path.parent.mkdir(parents=True)
    artifact_path.write_bytes(b"committed-step-artifact")

    result = sync_project(root)

    with sqlite3.connect(result.database_path) as connection:
        row = connection.execute(
            "SELECT sha256, byte_count, state FROM artifacts WHERE kind = 'step'"
        ).fetchone()
    assert row == (
        "26e8b51881d5970368e02d5ef87176220934b44ee8daa94807d54f5547c3ca6c",
        23,
        "indexed",
    )


def test_part_queries_are_read_only_and_resolve_aliases(tmp_path: Path) -> None:
    root = _copy_fixture(tmp_path)
    sync_project(root)
    index_path = database_path(root)
    before_mtime = index_path.stat().st_mtime_ns

    parts = list_parts(root)
    detail = get_part(root, "original_alpha_panel")

    assert [part.key for part in parts] == ["alpha_panel"]
    assert parts[0].artifact_count == 2
    assert parts[0].missing_artifact_count == 2
    assert detail is not None
    assert detail.key == "alpha_panel"
    assert detail.aliases == ("original_alpha_panel",)
    assert index_path.stat().st_mtime_ns == before_mtime


def test_listing_one_thousand_indexed_parts_stays_below_hard_gate(tmp_path: Path) -> None:
    root = tmp_path / "large_project"
    root.mkdir()
    parts = tuple(
        ManifestPart(
            uuid=UUID(int=index + 1),
            key=f"part_{index:04d}",
            aliases=(),
            generator=f"large_project.parts:make_{index:04d}",
            role=PartRole.PRINTABLE,
            status=PartStatus.ACTIVE,
            artifacts=(ArtifactSpec(kind="step", path=f"exports/step/part_{index:04d}.step"),),
        )
        for index in range(1000)
    )
    manifest = ProjectManifest(
        schema_version=1,
        project_id="large_project",
        python_package="large_project",
        parts=parts,
        assemblies=(),
    )
    (root / "flowcad.project.yaml").write_text(dump_manifest(manifest), encoding="utf-8")
    sync_project(root)

    started = time.perf_counter()
    listed = list_parts(root)
    elapsed = time.perf_counter() - started

    assert len(listed) == 1000
    assert elapsed < 0.250


def test_sync_indexes_project_owned_print_and_physical_metadata(tmp_path: Path) -> None:
    root = tmp_path / "physical_metadata"
    root.mkdir()
    manifest = ProjectManifest(
        schema_version=1,
        project_id="physical_metadata",
        python_package="physical_metadata",
        parts=(
            ManifestPart(
                uuid=UUID("11111111-1111-4111-8111-111111111111"),
                key="measured_part",
                aliases=(),
                generator="physical_metadata.parts:make_measured_part",
                role=PartRole.PRINTABLE,
                status=PartStatus.ACTIVE,
                artifacts=(),
                material="PETG",
                family="compute",
                version="b3_v2",
                compatible_versions=("b3_v1",),
                print=PrintSpec(shell_count=4, infill_density=0.4),
                mass_properties=MassProperties(
                    mass_kg=0.125,
                    center_of_mass_mm=(1.0, 2.0, 3.0),
                    inertia_kg_m2=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0),
                    source="measured",
                    status="complete",
                    notes="Bench measurement",
                ),
            ),
        ),
        assemblies=(),
    )
    (root / "flowcad.project.yaml").write_text(dump_manifest(manifest), encoding="utf-8")

    sync_project(root)
    summary = list_parts(root)[0]
    detail = get_part(root, "measured_part")

    assert summary.family == "compute"
    assert summary.version == "b3_v2"
    assert detail is not None
    assert detail.compatible_versions == ("b3_v1",)
    assert detail.shell_count == 4
    assert detail.infill_density == 0.4
    assert detail.mass_kg == 0.125
    assert detail.center_of_mass_mm == (1.0, 2.0, 3.0)
    assert detail.inertia_kg_m2 == (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
    assert detail.mass_source == "measured"
    assert detail.metadata_status == "complete"
