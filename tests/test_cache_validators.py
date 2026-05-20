from __future__ import annotations
import pytest
from pathlib import Path
from sqlmodel import Session, select
from flow_cad.params import ChassisParams
from flow_cad.registry import PartDefinition, PartRole
from flow_cad.core.cache import (
    create_cache_engine,
    get_component_cache,
    list_component_cache,
    latest_build_metadata,
    write_active_cache,
)

def test_validators_can_consume_cache(tmp_path) -> None:
    """
    Verify that validation scripts can use the active cache to retrieve 
    compiled facts without needing to re-evaluate geometry.
    """
    params = ChassisParams()
    db_path = tmp_path / params.project_id / "registry.db"

    # Mock a build with known values
    definition = PartDefinition(
        id="test_part",
        module_id="test_mod",
        filename="test.step",
        factory=lambda p: None,  # Not needed for cache-only test
        role=PartRole.PRINTABLE,
    )
    mock_shape = type("MockShape", (), {
        "bounding_box": lambda self: type("BBox", (), {
            "min": type("Point", (), {"X": 0.0, "Y": 0.0, "Z": 0.0}),
            "max": type("Point", (), {"X": 10.0, "Y": 20.0, "Z": 30.0})
        })(),
        "volume": 6000.0,
    })()


    write_active_cache(
        db_path,
        project_root=tmp_path,
        params=params,
        components=[(definition, mock_shape, tmp_path / "exports/step/test_mod/test.step")],
    )

    # Validator-style queries using the cache
    comp = get_component_cache(db_path, "test_part")
    assert comp is not None
    assert comp.volume_mm3 == 6000.0
    assert (comp.bbox_x, comp.bbox_y, comp.bbox_z) == (10.0, 20.0, 30.0)
    assert comp.role == "printable"

    # Verify we can list all printable parts from cache for batch validation
    all_cached = list_component_cache(db_path)
    printables = [c for c in all_cached if c.role == "printable"]
    assert len(printables) == 1
    assert printables[0].id == "test_part"

def test_validators_detect_stale_cache(tmp_path) -> None:
    """
    Verify that validators can detect when the cache is stale relative to source.
    """
    params = ChassisParams()
    db_path = tmp_path / params.project_id / "registry.db"

    # Build 1: old geometry
    write_active_cache(
        db_path,
        project_root=tmp_path,
        params=params,
        components=[],  # empty for simplicity
        build_id="old-build",
    )

    # Build 2: new geometry (simulated by different build_id)
    write_active_cache(
        db_path,
        project_root=tmp_path,
        params=params,
        components=[],
        build_id="new-build",
    )

    latest = latest_build_metadata(db_path)
    assert latest is not None
    assert latest.build_id == "new-build"

def test_cache_contains_all_registry_parts(tmp_path) -> None:
    """
    Verify that the cache contains exactly what's in the registry after a build.
    """
    from flow_cad.registry import REGISTRY, PartDefinition

    params = ChassisParams()
    db_path = tmp_path / params.project_id / "registry.db"

    # Mock shapes for all registered parts
    mock_shape = type("MockShape", (), {
        "bounding_box": lambda self: type("BBox", (), {
            "min": type("Point", (), {"X": 0.0, "Y": 0.0, "Z": 0.0}),
            "max": type("Point", (), {"X": 1.0, "Y": 1.0, "Z": 1.0})
        })(),
        "volume": 1.0,
    })

    components: list[tuple[PartDefinition, object, Path]] = [
        (def_obj, mock_shape(), tmp_path / f"{def_obj.filename}")
        for def_obj in REGISTRY.values()
    ]

    write_active_cache(
        db_path,
        project_root=tmp_path,
        params=params,
        components=components,
    )

    cached = {c.id for c in list_component_cache(db_path)}
    assert cached == set(REGISTRY.keys())
