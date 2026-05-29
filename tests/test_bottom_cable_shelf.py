import pytest
from build123d import Location

from flow_cad.core.geometry import box_at
from flow_cad.core.utils import (
    bottom_cable_pad_centers,
    bottom_cable_shelf_z,
    center_spine_usb_access_y_centers,
    center_spine_usb_access_z,
)
from flow_cad.params import ChassisParams
from flow_cad.parts.chassis import make_bottom_tray
from flow_cad.parts.shelves import make_bottom_cable_shelf


P = ChassisParams()


def _shape_volume(shape) -> float:
    if shape is None:
        return 0.0
    if hasattr(shape, "volume"):
        return shape.volume
    return sum(getattr(item, "volume", 0.0) for item in shape)


def test_bottom_cable_pad_contract() -> None:
    assert P.bottom_cable_pad_height == 12.0
    assert len(bottom_cable_pad_centers(P)) == 4
    assert {abs(x) for x, _y in bottom_cable_pad_centers(P)} == {P.bottom_cable_pad_x}


def test_bottom_cable_shelf_seats_without_intersection() -> None:
    tray = make_bottom_tray(P)
    shelf = make_bottom_cable_shelf(P).moved(Location((0.0, 0.0, bottom_cable_shelf_z(P))))

    overlap = tray.intersect(shelf)
    assert _shape_volume(overlap) == pytest.approx(0.0, abs=1e-6)


def test_bottom_cable_shelf_stays_inside_tray_footprint() -> None:
    shelf = make_bottom_cable_shelf(P)
    bb = shelf.bounding_box()

    assert bb.min.X > -P.internal_width / 2.0
    assert bb.max.X < P.internal_width / 2.0
    assert bb.min.Y > -P.bottom_tray_depth / 2.0
    assert bb.max.Y < P.bottom_tray_depth / 2.0


def test_center_spine_usb_access_cutouts_are_open() -> None:
    tray = make_bottom_tray(P)
    cut_z = center_spine_usb_access_z(P)

    for y in center_spine_usb_access_y_centers(P):
        probe = box_at(
            (
                P.integrated_center_spine_usb_access_width - 2.0,
                P.integrated_center_spine_usb_access_depth - 2.0,
                P.integrated_center_spine_usb_access_height - 2.0,
            ),
            (0.0, y, cut_z),
        )
        assert _shape_volume(tray.intersect(probe)) == pytest.approx(0.0, abs=1e-6)
