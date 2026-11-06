"""Review context is explicit project metadata, independent of robot naming."""
from dataclasses import replace
from pathlib import Path

import pytest

from flow_cad.registry import sync_project
from flow_cad.registry.db import connect_writable, database_path
from flow_cad.sdk import AssemblySpec, ManifestError, dump_manifest, load_manifest, loads_manifest
from flow_cad.viewer.services.inventory import InventoryService


FIXTURE = Path(__file__).parents[1] / "fixtures/projects/minimal_alpha/flowcad.project.yaml"


def manifest_with_review():
    source = load_manifest(FIXTURE)
    review = AssemblySpec(key="service_pose", occurrences=source.assemblies[0].occurrences)
    return replace(source, parts=(replace(source.parts[0], review_assembly=review.key),),
                   assemblies=(*source.assemblies, review))


def test_review_relationship_round_trips_and_reaches_the_metadata_only_inventory(tmp_path):
    manifest = manifest_with_review()
    assert loads_manifest(dump_manifest(manifest)) == manifest
    (tmp_path / "flowcad.project.yaml").write_text(dump_manifest(manifest))
    sync_project(tmp_path)
    payload = InventoryService(tmp_path).inventory()
    assert payload["parts"][0]["review_assembly"] == "service_pose"
    assert {occurrence["assembly_key"] for occurrence in payload["parts"][0]["occurrences"]} == {"active", "service_pose"}


@pytest.mark.parametrize("target", ["absent", "empty"])
def test_review_relationship_must_reference_an_assembly_containing_the_part(target):
    source = manifest_with_review()
    invalid = replace(source, parts=(replace(source.parts[0], review_assembly=target),),
                      assemblies=(*source.assemblies, AssemblySpec(key="empty", occurrences=())))
    with pytest.raises(ManifestError, match="must name an assembly containing this part"):
        loads_manifest(dump_manifest(invalid))


def test_older_project_index_remains_readable_without_review_metadata(tmp_path):
    manifest = load_manifest(FIXTURE)
    (tmp_path / "flowcad.project.yaml").write_text(dump_manifest(manifest))
    sync_project(tmp_path)
    with connect_writable(database_path(tmp_path)) as connection:
        connection.execute("ALTER TABLE parts DROP COLUMN review_assembly")
        connection.execute("PRAGMA user_version = 3")
    assert InventoryService(tmp_path).inventory()["parts"][0]["review_assembly"] is None
