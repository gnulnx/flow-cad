from __future__ import annotations

from flow_cad.sketch_intent import build_sketch_intent_recipe


def _lobed_outline() -> dict:
    return {
        "kind": "freehand",
        "points": [
            {"x": 0.18, "y": 0.5},
            {"x": 0.26, "y": 0.22},
            {"x": 0.43, "y": 0.15},
            {"x": 0.63, "y": 0.16},
            {"x": 0.77, "y": 0.31},
            {"x": 0.9, "y": 0.5},
            {"x": 0.77, "y": 0.68},
            {"x": 0.66, "y": 0.88},
            {"x": 0.49, "y": 0.95},
            {"x": 0.34, "y": 0.84},
            {"x": 0.22, "y": 0.66},
        ],
    }


def test_lobed_outline_and_hole_markers_are_output_as_non_rectangular_profile() -> None:
    annotations = [
        _lobed_outline(),
        {
            "kind": "circle",
            "x": 0.70,
            "y": 0.42,
            "radius": 0.03,
        },
        {
            "kind": "freehand",
            "points": [
                {"x": 0.62, "y": 0.62},
                {"x": 0.64, "y": 0.66},
                {"x": 0.68, "y": 0.62},
                {"x": 0.64, "y": 0.58},
            ],
        },
    ]

    recipe = build_sketch_intent_recipe(
        annotations,
        {"length": 120.0, "width": 80.0, "thickness": 6.0},
        symmetry=True,
    )

    assert recipe["outline"]["kind"] == "closed_polygon_mm"
    points = recipe["outline"]["points"]
    assert points[0] == points[-1], "Outline should be closed."
    assert len(points) > 6

    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    assert min(xs) < 0.0 < max(xs)
    assert min(ys) < 0.0 < max(ys)

    edges = [
        (abs(points[i][0] - points[i - 1][0]), abs(points[i][1] - points[i - 1][1]))
        for i in range(1, len(points))
    ]
    assert any(dx > 1e-6 and dy > 1e-6 for dx, dy in edges), "Expected non-rectangular outline cleanup."

    hole_kinds = {entry["source_kind"] for entry in recipe["holes"]}
    assert hole_kinds == {"circle", "freehand"}
    assert recipe["length"] == 120.0
    assert recipe["width"] == 80.0
    assert any("Selected freehand annotation" in item for item in recipe["assumptions"])


def test_largest_freehand_is_selected_as_outline_and_hole_marks_are_excluded() -> None:
    annotations = [
        {
            "kind": "freehand",
            "points": [
                {"x": 0.12, "y": 0.12},
                {"x": 0.22, "y": 0.18},
                {"x": 0.17, "y": 0.28},
                {"x": 0.06, "y": 0.24},
            ],
        },
        {
            "kind": "freehand",
            "points": [
                {"x": 0.20, "y": 0.20},
                {"x": 0.22, "y": 0.25},
                {"x": 0.30, "y": 0.25},
                {"x": 0.26, "y": 0.20},
                {"x": 0.20, "y": 0.20},
            ],
        },
        {
            "kind": "freehand",
            "points": [
                {"x": 0.22, "y": 0.22},
                {"x": 0.24, "y": 0.27},
                {"x": 0.28, "y": 0.28},
                {"x": 0.26, "y": 0.22},
                {"x": 0.22, "y": 0.22},
            ],
        },
        {
            "kind": "circle",
            "x": 0.15,
            "y": 0.15,
            "radius": 0.03,
        },
        {
            "kind": "note",
            "text": "ignore this",
            "x": 0.50,
            "y": 0.50,
        },
    ]

    recipe = build_sketch_intent_recipe(
        annotations,
        {"length": 100.0, "width": 80.0, "thickness": 5.0},
    )

    assert recipe["part_id"] == "sketch_plate"
    assert recipe["thickness"] == 5.0
    hole_annotations = {entry["source_annotation_index"] for entry in recipe["holes"]}
    assert 3 in hole_annotations
    assert 0 not in hole_annotations
    assert 4 not in hole_annotations
    assert len(recipe["holes"]) >= 2

    points = recipe["outline"]["points"]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    assert min(xs) <= -50.0 and max(xs) >= 50.0
    assert min(ys) <= -40.0 and max(ys) >= 40.0


def test_assumptions_mark_sketch_as_intent_not_exact() -> None:
    recipe = build_sketch_intent_recipe([], {"length": 50.0, "width": 40.0, "thickness": 8.0})

    assert any("not exact" in assumption.lower() for assumption in recipe["assumptions"])
    assert "No usable freehand outline" in "".join(recipe["warnings"])

    outline_points = recipe["outline"]["points"]
    assert outline_points == [
        [-25.0, -20.0],
        [25.0, -20.0],
        [25.0, 20.0],
        [-25.0, 20.0],
        [-25.0, -20.0],
    ]


def test_options_symmetry_key_is_respected() -> None:
    recipe = build_sketch_intent_recipe(
        [_lobed_outline()],
        {"length": 30.0, "width": 40.0, "thickness": 5.0},
        options={"symmetry": "y"},
    )
    xs = [point[0] for point in recipe["outline"]["points"]]
    ys = [point[1] for point in recipe["outline"]["points"]]
    assert min(xs) < 0.0
    assert max(xs) > 0.0
    assert min(ys) < 0.0
    assert max(ys) > 0.0
