from flow_cad.params import ChassisParams
from pathlib import Path

from flow_cad.registry import (
    ASSEMBLY_DEFINITION,
    PART_DEFINITIONS,
    PartRole,
    REGISTRY,
    expected_printable_export_relative_paths,
    expected_printable_step_relative_paths,
    expected_step_relative_paths,
)


def test_registry_ids_and_export_paths_are_unique() -> None:
    ids = [definition.id for definition in PART_DEFINITIONS]
    export_paths = [definition.module_id + "/" + definition.filename for definition in PART_DEFINITIONS]

    assert len(ids) == len(set(ids))
    assert len(export_paths) == len(set(export_paths))
    assert set(REGISTRY) == set(ids)


def test_registry_definitions_have_required_metadata() -> None:
    for definition in PART_DEFINITIONS:
        assert definition.id
        assert definition.module_id
        assert definition.filename.endswith(".step")
        assert definition.role in PartRole
        if definition.role == PartRole.PRINTABLE:
            assert definition.material
            assert definition.shell_count > 0
            assert 0.0 < definition.infill_density <= 1.0


def test_registry_factories_build_shapes() -> None:
    params = ChassisParams()

    for definition in PART_DEFINITIONS:
        shape = definition.factory(params)
        assert shape is not None, definition.id
        assert shape.bounding_box() is not None, definition.id


def test_registry_includes_expected_roles() -> None:
    roles = {definition.role for definition in PART_DEFINITIONS}

    assert PartRole.PRINTABLE in roles
    assert PartRole.REFERENCE in roles
    assert REGISTRY["rear_panel_detachable"].role == PartRole.INSPECTION
    assert REGISTRY["rear_panel_detachable_body"].role == PartRole.PRINTABLE
    assert REGISTRY["rear_panel_detachable_bumpout"].role == PartRole.PRINTABLE
    assert ASSEMBLY_DEFINITION.role == PartRole.INSPECTION


def test_expected_step_relative_paths_include_parts_and_assembly() -> None:
    paths = expected_step_relative_paths()

    assert Path("step/lower_chassis/b3_lower_chassis_left_side_plate.step") in paths
    assert Path("step/lower_chassis/b3_lower_chassis_assembly.step") in paths
    assert len(paths) == len(PART_DEFINITIONS) + 1


def test_expected_printable_step_relative_paths_exclude_inspection_previews() -> None:
    paths = expected_printable_step_relative_paths()

    assert Path("step/lower_chassis/b3_lower_chassis_rear_panel_detachable_body.step") in paths
    assert Path("step/lower_chassis/b3_lower_chassis_rear_panel_detachable_bumpout.step") in paths
    assert Path("step/lower_chassis/b3_lower_chassis_rear_panel_detachable.step") not in paths
    assert Path("step/lower_chassis/b3_lower_chassis_assembly.step") not in paths


def test_expected_printable_export_relative_paths_exclude_inspection_artifacts() -> None:
    paths = expected_printable_export_relative_paths()

    assert Path("step/lower_chassis/b3_lower_chassis_rear_panel_detachable_bumpout.step") in paths
    assert Path("stl/lower_chassis/b3_lower_chassis_rear_panel_detachable_bumpout.stl") in paths
    assert Path("snapshots/lower_chassis/b3_lower_chassis_rear_panel_detachable_bumpout_front.svg") in paths
    assert Path("step/lower_chassis/b3_lower_chassis_rear_panel_detachable.step") not in paths
    assert Path("stl/lower_chassis/b3_lower_chassis_rear_panel_detachable.stl") not in paths
    assert Path("snapshots/lower_chassis/b3_lower_chassis_rear_panel_detachable_front.svg") not in paths
