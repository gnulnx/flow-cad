from flow_cad.preview_commands import (
    PreviewCommandContext,
    parse_panel_command,
)


def test_parse_panel_benchmark_command_with_default_context() -> None:
    result = parse_panel_command(
        "Make this a 120 x 45 x 3 mm panel, add two M4 clearance holes 12 mm from "
        "the front edge, and put five louvers on the outside face."
    )

    assert result.ok is True
    assert result.command.startswith("Make this a 120 x 45 x 3 mm panel")
    assert result.warnings
    assert any("Outside face is ambiguous without context." in warning for warning in result.warnings)
    assert any(
        "Louver width/height unspecified; using 10x3 mm." in assumption
        for assumption in result.assumptions
    )

    create_ops = [op for op in result.operations if op.name == "create_box"]
    hole_ops = [op for op in result.operations if op.name == "add_hole"]
    louver_ops = [op for op in result.operations if op.name == "add_louver_pattern"]

    assert len(create_ops) == 1
    assert create_ops[0].parameters["length"] == 120.0
    assert create_ops[0].parameters["width"] == 45.0
    assert create_ops[0].parameters["height"] == 3.0

    assert len(hole_ops) == 2
    assert hole_ops[0].parameters["diameter"] == 4.0
    assert hole_ops[0].parameters["x"] == 50.0
    assert hole_ops[0].parameters["y"] == 12.0
    assert hole_ops[1].parameters["diameter"] == 4.0
    assert hole_ops[1].parameters["x"] == 70.0
    assert hole_ops[1].parameters["y"] == 12.0
    assert all(op.parameters["face"] == "top" for op in hole_ops)
    assert any("Interpreting 'two holes' as mirrored pair" in assumption for assumption in result.assumptions)

    assert len(louver_ops) == 1
    assert louver_ops[0].parameters["count"] == 5
    assert louver_ops[0].parameters["face"] == "top"
    assert louver_ops[0].parameters["width"] == 10.0
    assert louver_ops[0].parameters["height"] == 3.0


def test_parse_numeric_hole_diameter() -> None:
    result = parse_panel_command(
        "Make this a 60 x 60 x 3 mm panel, add two 6 mm clearance holes 8 mm from the front edge."
    )

    assert result.ok is True
    assert len(result.operations) == 3

    first_hole, second_hole = (
        [op for op in result.operations if op.name == "add_hole"][0],
        [op for op in result.operations if op.name == "add_hole"][1],
    )
    assert first_hole.parameters["diameter"] == 6.0
    assert first_hole.parameters["y"] == 8.0
    assert second_hole.parameters["y"] == 8.0


def test_parse_rejects_unsupported_cad_request() -> None:
    result = parse_panel_command("Generate a fillet around everything and subtract an arbitrary profile from the body.")

    assert result.ok is False
    assert "Unsupported command intent: no supported panel operation found." in result.errors
    assert len(result.operations) == 0


def test_missing_dimensions_use_conservative_defaults() -> None:
    result = parse_panel_command(
        "Add two M4 clearance holes 10 mm from the front edge on the top face."
    )

    assert result.ok is True
    assert any(op.name == "add_hole" for op in result.operations)
    assert len(result.operations) == 2
    assert any(
        "Used default 120x120x3 mm panel extents and conservative face assumptions." in assumption
        for assumption in result.assumptions
    )


def test_ambiguous_face_emits_warning_without_context() -> None:
    result = parse_panel_command(
        "Make this a 80 x 40 x 2 mm panel, and put four louvers on the outside face."
    )

    assert result.ok is True
    assert any("Outside face is ambiguous without context." in warning for warning in result.warnings)
    assert any("Assuming outside = top." in assumption for assumption in result.assumptions)

    louver_ops = [op for op in result.operations if op.name == "add_louver_pattern"]
    assert len(louver_ops) == 1
    assert louver_ops[0].parameters["face"] == "top"


def test_parser_is_deterministic_without_side_effects() -> None:
    command = "Make this a 120 x 45 x 3 mm panel, add two M4 clearance holes 12 mm from the front edge."
    first = parse_panel_command(command)
    second = parse_panel_command(command)

    assert first == second
    assert first.to_payload()["operations"] == second.to_payload()["operations"]


def test_parse_base_plate_dimensions_with_mm_units_on_each_axis() -> None:
    result = parse_panel_command("Please create a base plate that is 100mm x 100mm x 10mm thick")

    assert result.ok is True
    assert len(result.operations) == 1
    operation = result.operations[0]
    assert operation.name == "create_box"
    assert operation.parameters == {
        "length": 100.0,
        "width": 100.0,
        "height": 10.0,
    }


def test_parse_panel_dimensions_with_and_before_thickness() -> None:
    result = parse_panel_command("Please create a panel that is 100mm x 100mm and 10mm thick.")

    assert result.ok is True
    assert len(result.operations) == 1
    operation = result.operations[0]
    assert operation.name == "create_box"
    assert operation.parameters == {
        "length": 100.0,
        "width": 100.0,
        "height": 10.0,
    }


def test_parse_plate_dimensions_with_by_separator_and_common_typo() -> None:
    result = parse_panel_command("create a plate that is 100mm byu 100mm by 10mm")

    assert result.ok is True
    assert len(result.operations) == 1
    operation = result.operations[0]
    assert operation.name == "create_box"
    assert operation.parameters == {
        "length": 100.0,
        "width": 100.0,
        "height": 10.0,
    }


def test_parse_m5_holes_in_each_corner_from_each_side() -> None:
    result = parse_panel_command(
        "Place m5 holes in each corner 10mm from each side",
        context=PreviewCommandContext(part_id="draft_plate", length=100, width=120, thickness=10),
    )

    assert result.ok is True
    hole_operations = [operation for operation in result.operations if operation.name == "add_hole"]
    assert len(hole_operations) == 4
    assert [operation.parameters["diameter"] for operation in hole_operations] == [5.0, 5.0, 5.0, 5.0]
    assert {(operation.parameters["x"], operation.parameters["y"]) for operation in hole_operations} == {
        (10.0, 10.0),
        (90.0, 10.0),
        (10.0, 110.0),
        (90.0, 110.0),
    }
