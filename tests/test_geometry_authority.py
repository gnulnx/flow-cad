from flow_cad.viewer.geometry_authority import geometry_for_artifact, geometry_for_edit_source


def test_flow_python_step_geometry_is_exact_but_not_directly_editable() -> None:
    geometry = geometry_for_artifact("step")

    assert geometry.source_kind == "flow_python"
    assert geometry.geometry_authority == "step_kernel"
    assert geometry.capabilities.exact_topology is True
    assert geometry.capabilities.exact_editing is False


def test_flow_document_geometry_is_exact_and_editable() -> None:
    geometry = geometry_for_edit_source("flow_document")

    assert geometry.source_kind == "flow_document"
    assert geometry.geometry_authority == "step_kernel"
    assert geometry.capabilities.exact_topology is True
    assert geometry.capabilities.exact_editing is True
    assert geometry.capabilities.mesh_only is False


def test_mesh_only_geometry_stays_exact_edit_disabled() -> None:
    geometry = geometry_for_edit_source("stl")

    assert geometry.source_kind == "stl"
    assert geometry.geometry_authority == "mesh"
    assert geometry.capabilities.exact_editing is False
    assert geometry.capabilities.mesh_only is True
