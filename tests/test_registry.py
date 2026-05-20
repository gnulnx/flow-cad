from flow_cad.params import ChassisParams
from flow_cad.registry import ASSEMBLY_DEFINITION, PART_DEFINITIONS, PartRole, REGISTRY


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
    assert ASSEMBLY_DEFINITION.role == PartRole.INSPECTION
