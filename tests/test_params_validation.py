import pytest
from dataclasses import replace
from flow_cad.params import ChassisParams
from flow_cad.parts.panels import panel_end_span_rib_depth

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
