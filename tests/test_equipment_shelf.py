import pytest

from flow_cad.core.geometry import box_at
from flow_cad.params import ChassisParams
from flow_cad.registry import REGISTRY


P = ChassisParams()


def _shape_volume(shape) -> float:
    if shape is None:
        return 0.0
    if hasattr(shape, "volume"):
        return shape.volume
    return sum(getattr(item, "volume", 0.0) for item in shape)


def _probe_volume(
    shape,
    size: tuple[float, float, float],
    center: tuple[float, float, float],
) -> float:
    return _shape_volume(shape.intersect(box_at(size, center)))


def test_service_fit_four_way_keeps_perimeter_cutouts_but_fills_center() -> None:
    shelf = REGISTRY["equipment_shelf_service_fit_four_way"].factory(P)
    t = P.shelf_thickness

    center_probe = (0.0, 0.0, t / 2.0)
    assert _probe_volume(shelf, (4.0, 4.0, t + 2.0), center_probe) > 40.0

    side_probe_x = P.service_shelf_width / 2.0 - P.service_shelf_side_relief_depth / 2.0
    end_probe_y = P.service_shelf_depth / 2.0 - P.shelf_side_cable_notch_shallow_depth / 2.0
    for side in (-1, 1):
        assert _probe_volume(
            shelf,
            (4.0, 4.0, t + 2.0),
            (side * side_probe_x, 0.0, t / 2.0),
        ) == pytest.approx(0.0, abs=1e-6)
        assert _probe_volume(
            shelf,
            (4.0, 4.0, t + 2.0),
            (0.0, side * end_probe_y, t / 2.0),
        ) == pytest.approx(0.0, abs=1e-6)


def test_standard_equipment_shelf_keeps_center_wiring_channel() -> None:
    shelf = REGISTRY["equipment_shelf"].factory(P)
    t = P.shelf_thickness

    assert _probe_volume(
        shelf,
        (4.0, 4.0, t + 2.0),
        (0.0, 0.0, t / 2.0),
    ) == pytest.approx(0.0, abs=1e-6)
