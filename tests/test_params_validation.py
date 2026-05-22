import pytest
from dataclasses import replace
from flow_cad.params import ChassisParams
from flow_cad.parts.panels import (
    REAR_SLIDE_TONGUE_LEAD_IN,
    box_at,
    make_rear_panel_detachable_body,
    make_rear_panel_detachable_bumpout_shell,
    make_rear_slide_receiver,
    panel_end_span_rib_depth,
)

P = ChassisParams()

def test_params_valid_default():
    """Ensure the default parameters pass validation."""
    p = ChassisParams()
    # Should not raise any exception
    p.validate_params()

def test_shelf_connectivity_failure():
    """Test that too-deep notches trigger a ValueError."""
    # Default shelf_width is 180, half is 90. 
    # notch_edge = 90 - depth. If depth=85, edge=5. 
    # Safety threshold is 180 * 0.1 = 18.
    p = replace(ChassisParams(), shelf_side_cable_notch_depth=85.0)
    with pytest.raises(ValueError, match="CRITICAL: Shelf side notches too deep"):
        p.validate_params()

def test_chassis_envelope_failure():
    """Test that outer width smaller than internal + walls triggers a ValueError."""
    p = replace(ChassisParams(), center_box_outer_width=100.0, internal_width=180.0)
    with pytest.raises(ValueError, match="Chassis outer width must accommodate"):
        p.validate_params()

def test_axle_height_failure():
    """Test that axle center too low triggers a ValueError."""
    p = replace(ChassisParams(), axle_center_height_from_bottom=2.0, bottom_thickness=10.0)
    with pytest.raises(ValueError, match="Axle center is too low"):
        p.validate_params()

def test_battery_fit_failure():
    """Test that battery cassette wider than internal width triggers a ValueError."""
    p = replace(ChassisParams(), battery_cassette_width=200.0, internal_width=180.0)
    with pytest.raises(ValueError, match="Battery cassette is wider"):
        p.validate_params()


def test_detachable_rear_lower_span_depth_contract():
    assert P.front_rear_panel_end_span_total_depth == 20.0
    assert P.rear_detachable_panel_lower_span_total_depth == 12.0
    assert panel_end_span_rib_depth(P, P.front_rear_panel_end_span_total_depth) == 14.0
    assert panel_end_span_rib_depth(P, P.rear_detachable_panel_lower_span_total_depth) == 6.0


def test_detachable_rear_tpu_head_contract():
    assert P.rear_slide_head_width == 10.0
    assert P.rear_slide_tpu_head_width == 8.0
    assert P.rear_slide_head_depth == 2.3
    assert P.rear_slide_tpu_head_depth == 1.75
    assert P.rear_slide_neck_width < P.rear_slide_tpu_head_width < P.rear_slide_head_width
    assert 0.0 < P.rear_slide_tpu_head_depth < P.rear_slide_head_depth
    assert P.rear_slide_outer_weld_width == 10.0
    assert P.rear_slide_outer_weld_depth == 10.0
    assert P.rear_slide_outer_weld_overlap > 0.0


def _shape_volume(shape) -> float:
    if shape is None:
        return 0.0
    if hasattr(shape, "volume"):
        return shape.volume
    return sum(getattr(item, "volume", 0.0) for item in shape)


def test_detachable_rear_receiver_roots_are_connected_without_blocking_head_slot():
    body = make_rear_panel_detachable_body(P)
    bumpout = make_rear_panel_detachable_bumpout_shell(P)
    assert len(body.solids()) == 1
    assert _shape_volume(body.intersect(bumpout)) == pytest.approx(0.0, abs=1e-6)

    head_slot = P.rear_slide_head_width + 2.0 * P.rear_slide_side_clearance
    backing_y_max = (
        P.rear_bumpout_detachable_base_gap
        - REAR_SLIDE_TONGUE_LEAD_IN
        - P.rear_slide_face_clearance
    )
    root_probe_y = (backing_y_max - 0.25) / 2.0
    head_probe_y = P.rear_bumpout_detachable_base_gap - REAR_SLIDE_TONGUE_LEAD_IN + 0.65

    for rail_x in (-P.rear_slide_rail_x, P.rear_slide_rail_x):
        receiver = make_rear_slide_receiver(P, rail_x)
        rail_side = -1 if rail_x < 0.0 else 1
        outer_receiver_x = rail_side * (
            abs(rail_x) + head_slot / 2.0 + P.rear_slide_channel_wall
        )
        weld_x = rail_side * (
            abs(outer_receiver_x)
            + P.rear_slide_outer_weld_width / 2.0
            - P.rear_slide_outer_weld_overlap
        )
        weld_y = (
            P.rear_bumpout_detachable_base_gap
            + P.rear_slide_face_clearance / 2.0
            - P.rear_slide_outer_weld_depth / 2.0
        )
        outer_weld = receiver.intersect(box_at((1.0, 1.0, 20.0), (weld_x, weld_y, 120.0)))
        assert _shape_volume(outer_weld) > 1.0

        for side in (-1, 1):
            root_x = rail_x + side * (head_slot / 2.0 + P.rear_slide_channel_wall / 2.0)
            mid_root = receiver.intersect(
                box_at((1.0, 1.0, 20.0), (root_x, root_probe_y, 120.0))
            )
            top_root = receiver.intersect(
                box_at((1.0, 1.0, 6.0), (root_x, root_probe_y, 211.0))
            )
            assert _shape_volume(mid_root) > 1.0
            assert _shape_volume(top_root) > 1.0

        head_channel = receiver.intersect(
            box_at((1.0, 1.0, 20.0), (rail_x, head_probe_y, 120.0))
        )
        assert _shape_volume(head_channel) == pytest.approx(0.0, abs=1e-6)
