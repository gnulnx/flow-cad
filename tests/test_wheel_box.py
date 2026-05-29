import pytest

from math import pi

from flow_cad.core.geometry import box_at, chamfered_yz_rect_prism, cyl_x, cyl_z, double_d_prism
from flow_cad.params import ChassisParams
from flow_cad.parts.wheel_box.prototype import (
    wheel_box_axle_center_z,
    wheel_box_insert_mount_centers,
    wheel_box_insert_window_size,
    wheel_box_lid_screw_centers,
    wheel_box_outer_size,
    wheel_box_tray_mount_centers,
    wheel_box_tray_mount_rails,
    wheel_box_tray_mount_zone_x,
)
from flow_cad.registry import REGISTRY


P = ChassisParams()


def _shape_volume(shape) -> float:
    if shape is None:
        return 0.0
    if hasattr(shape, "volume"):
        return shape.volume
    return sum(getattr(item, "volume", 0.0) for item in shape)


def test_wheel_box_body_is_one_connected_solid() -> None:
    body = REGISTRY["wheel_box_test_body"].factory(P)
    assert len(list(body.solids())) == 1


def test_wheel_box_test_body_uses_insert_height_and_printable_envelope() -> None:
    body = REGISTRY["wheel_box_test_body"].factory(P)
    bbox = body.bounding_box()
    outer_x, outer_y, outer_z = wheel_box_outer_size(P)
    wire_cavity_x = outer_x - P.wheel_box_mount_wall_thickness - P.wheel_box_wall_thickness

    assert bbox.size.X == pytest.approx(outer_x)
    assert bbox.size.Y == pytest.approx(outer_y)
    assert bbox.size.Z == pytest.approx(outer_z)
    assert bbox.size.X == pytest.approx(152.0)
    assert bbox.size.Z == pytest.approx(99.6)
    assert bbox.size.Z < 101.6
    assert P.wheel_box_mount_wall_thickness >= 10.0
    assert wire_cavity_x >= 5.0 * 25.4
    assert max(bbox.size.X, bbox.size.Y, bbox.size.Z) < 256.0


def test_wheel_box_test_body_has_chamfered_insert_window_and_side_m5_pattern() -> None:
    body = REGISTRY["wheel_box_test_body"].factory(P)
    outer_x, _, _ = wheel_box_outer_size(P)
    window_y, window_z = wheel_box_insert_window_size(P)

    insert_air_probe = chamfered_yz_rect_prism(
        P.insert_size,
        P.insert_size,
        P.insert_corner_chamfer,
        P.wheel_box_mount_wall_thickness + 1.0,
        (
            -outer_x / 2.0 + P.wheel_box_mount_wall_thickness / 2.0,
            0.0,
            wheel_box_axle_center_z(P),
        ),
    )
    assert _shape_volume(body.intersect(insert_air_probe)) == pytest.approx(0.0, abs=1e-6)

    square_corner_probe = chamfered_yz_rect_prism(
        window_y + 4.0,
        window_z + 4.0,
        0.1,
        P.wheel_box_mount_wall_thickness,
        (
            -outer_x / 2.0 + P.wheel_box_mount_wall_thickness / 2.0,
            0.0,
            wheel_box_axle_center_z(P),
        ),
    )
    assert _shape_volume(body.intersect(square_corner_probe)) > 1.0

    insert_travel_probe = chamfered_yz_rect_prism(
        window_y,
        window_z,
        P.insert_pocket_corner_chamfer,
        outer_x - P.wheel_box_wall_thickness - 2.0,
        (-P.wheel_box_wall_thickness / 2.0, 0.0, wheel_box_axle_center_z(P)),
    )
    assert _shape_volume(body.intersect(insert_travel_probe)) < 10.0

    hole_x = -outer_x / 2.0 + P.wheel_box_mount_wall_thickness / 2.0
    for y, z in wheel_box_insert_mount_centers(P):
        air_probe = cyl_x(
            P.m4_clearance_diameter / 2.0 - 0.05,
            P.wheel_box_mount_wall_thickness + 2.0,
            (hole_x, y, z),
        )
        material_probe = cyl_x(
            P.m4_clearance_diameter / 2.0 + 0.35,
            P.wheel_box_mount_wall_thickness,
            (hole_x, y, z),
        )
        assert _shape_volume(body.intersect(air_probe)) < 1.0
        assert _shape_volume(body.intersect(material_probe)) > 1.0


def test_wheel_box_body_has_five_inch_mount_zone_and_full_length_tray_rails() -> None:
    body = REGISTRY["wheel_box_test_body"].factory(P)
    outer_x, outer_y, _ = wheel_box_outer_size(P)
    centers = wheel_box_tray_mount_centers(P)
    rail_min_x, rail_max_x = wheel_box_tray_mount_zone_x(P)
    zone_center_x = (rail_min_x + rail_max_x) / 2.0
    edge_x = rail_min_x + P.wheel_box_tray_mount_edge_margin_x
    pillar_x = zone_center_x + P.wheel_box_tray_mount_hole_offset_x - P.wheel_box_tray_mount_pillar_pull_in_x
    mount_y = outer_y / 2.0 - P.wheel_box_tray_mount_rail_depth_y / 2.0

    assert len(centers) == 4
    assert sorted({round(x, 6) for x, _y, _z in centers}) == pytest.approx([edge_x, pillar_x])
    assert pillar_x - edge_x > 45.0
    assert rail_min_x - (-outer_x / 2.0) == pytest.approx(outer_x - P.wheel_box_tray_mount_span_x)
    assert rail_min_x - (-outer_x / 2.0) == pytest.approx(25.0, abs=0.5)
    assert edge_x - rail_min_x >= P.wheel_box_tray_mount_edge_margin_x
    for x, y, z in centers:
        assert abs(x - zone_center_x) < P.wheel_box_tray_mount_span_x / 2.0
        assert abs(y) == pytest.approx(mount_y)
        assert outer_y / 2.0 - abs(y) == pytest.approx(P.wheel_box_tray_mount_rail_depth_y / 2.0)
        for lid_x, lid_y in wheel_box_lid_screw_centers(P):
            distance = ((x - lid_x) ** 2 + (y - lid_y) ** 2) ** 0.5
            assert distance > P.m5_clearance_diameter / 2.0 + P.m4_clearance_diameter / 2.0 + 5.0

        air_probe = cyl_z(
            P.m5_clearance_diameter / 2.0 - 0.2,
            P.wheel_box_tray_mount_rail_height_z + 2.0,
            (x, y, z),
        )
        assert _shape_volume(body.intersect(air_probe)) < 1.0

    for center, size in wheel_box_tray_mount_rails(P):
        assert size[0] == pytest.approx(outer_x)
        assert abs(center[1]) - size[1] / 2.0 > wheel_box_insert_window_size(P)[0] / 2.0 + 2.0
        rail_probe = box_at(
            (
                size[0] - 1.0,
                size[1] - 1.0,
                size[2] - 1.0,
            ),
            center,
        )
        expected = (size[0] - 1.0) * (size[1] - 1.0) * (size[2] - 1.0)
        assert _shape_volume(body.intersect(rail_probe)) > expected * 0.85


def test_wheel_box_tray_mount_holes_are_centered_on_usable_rail_landings() -> None:
    body = REGISTRY["wheel_box_test_body"].factory(P)
    access_radius = P.wheel_box_tray_mount_washer_access_diameter / 2.0
    hole_radius = P.m5_clearance_diameter / 2.0
    rail_min_x, _rail_max_x = wheel_box_tray_mount_zone_x(P)

    for x, y, z in wheel_box_tray_mount_centers(P):
        assert x - rail_min_x >= P.wheel_box_tray_mount_edge_margin_x
        matching_rail = next(
            (center, size)
            for center, size in wheel_box_tray_mount_rails(P)
            if center[1] * y > 0.0
        )
        rail_center, rail_size = matching_rail
        rail_min_y = abs(rail_center[1]) - rail_size[1] / 2.0
        rail_max_y = abs(rail_center[1]) + rail_size[1] / 2.0

        assert abs(y) == pytest.approx(abs(rail_center[1]))
        assert abs(y) - rail_min_y >= access_radius
        assert rail_max_y - abs(y) >= access_radius

        landing_height = P.wheel_box_tray_mount_rail_height_z - 1.0
        landing_probe = cyl_z(access_radius, landing_height, (x, y, z))
        expected_ring_volume = pi * (access_radius**2 - hole_radius**2) * landing_height
        assert _shape_volume(body.intersect(landing_probe)) > expected_ring_volume * 0.95


def test_wheel_box_top_and_bottom_lids_match_body_screw_pattern() -> None:
    outer_x, outer_y, _ = wheel_box_outer_size(P)

    for part_id in ("wheel_box_test_top_lid", "wheel_box_test_bottom_lid"):
        lid = REGISTRY[part_id].factory(P)
        bbox = lid.bounding_box()

        assert bbox.size.X == pytest.approx(outer_x)
        assert bbox.size.Y == pytest.approx(outer_y)
        assert bbox.size.Z == pytest.approx(2.0 * P.wheel_box_lid_thickness)

        for x, y in wheel_box_lid_screw_centers(P):
            air_probe = cyl_z(P.m4_clearance_diameter / 2.0 - 0.05, bbox.size.Z + 2.0, (x, y, bbox.size.Z / 2.0))
            assert _shape_volume(lid.intersect(air_probe)) == pytest.approx(0.0, abs=1e-6)


def test_top_lid_has_battery_mount_clearance_but_bottom_lid_does_not() -> None:
    top_lid = REGISTRY["wheel_box_test_top_lid"].factory(P)
    bottom_lid = REGISTRY["wheel_box_test_bottom_lid"].factory(P)
    lid_z = P.wheel_box_lid_thickness

    for x, y, _z in wheel_box_tray_mount_centers(P):
        air_probe = cyl_z(P.m5_clearance_diameter / 2.0 - 0.05, 3.0 * lid_z, (x, y, lid_z))
        material_probe = cyl_z(P.m5_clearance_diameter / 2.0 + 0.5, 2.0 * lid_z, (x, y, lid_z))

        assert _shape_volume(top_lid.intersect(air_probe)) == pytest.approx(0.0, abs=1e-6)
        assert _shape_volume(bottom_lid.intersect(material_probe)) > 1.0


def test_wheel_box_tight_insert_uses_tight_shaft_and_four_m4_mounts() -> None:
    insert = REGISTRY["wheel_box_tight_insert"].factory(P)
    bbox = insert.bounding_box()
    window_y, window_z = wheel_box_insert_window_size(P)
    expected_y = window_y + 2.0 * P.wheel_box_side_mount_lug_width_y
    expected_z = window_z + 2.0 * P.wheel_box_top_bottom_mount_lug_height_z

    assert bbox.size.X == pytest.approx(P.insert_thickness + P.insert_retainer_flange_thickness)
    assert bbox.size.Y == pytest.approx(expected_y)
    assert bbox.size.Z == pytest.approx(expected_z)

    shaft_probe = double_d_prism(15.5, 11.5, P.insert_thickness + 2.0, (P.insert_thickness / 2.0, 0.0, 0.0))
    assert _shape_volume(insert.intersect(shaft_probe)) == pytest.approx(0.0, abs=1e-6)

    axle_z = wheel_box_axle_center_z(P)
    assert len(wheel_box_insert_mount_centers(P)) == 4
    y_centers = sorted({round(abs(y), 6) for y, _ in wheel_box_insert_mount_centers(P)})
    z_centers = sorted({round(abs(z - axle_z), 6) for _, z in wheel_box_insert_mount_centers(P)})
    assert y_centers == pytest.approx([window_y / 2.0 + P.wheel_box_insert_mount_window_margin_y])
    assert z_centers == pytest.approx([wheel_box_axle_center_z(P) - P.wheel_box_insert_mount_edge_margin_z])
    for y, z in wheel_box_insert_mount_centers(P):
        assert z > P.wheel_box_insert_mount_edge_margin_z - 1e-6
        assert bbox.size.Z - z > P.wheel_box_insert_mount_edge_margin_z - 1e-6
        air_probe = cyl_x(
            P.m4_clearance_diameter / 2.0 - 0.05,
            P.insert_retainer_flange_thickness + 2.0,
            (-P.insert_retainer_flange_thickness / 2.0, y, z - axle_z),
        )
        assert _shape_volume(insert.intersect(air_probe)) == pytest.approx(0.0, abs=1e-6)
