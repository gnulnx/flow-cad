from __future__ import annotations
from ..core.geometry import box_at, cyl_z, horizontal_slot_z, safe_chamfer
from ..core.utils import bottom_cable_pad_centers
from ..params import ChassisParams

def make_equipment_shelf(
    params: ChassisParams,
    side_cable_notches: bool = False,
    side_cable_notch_depth: float | None = None,
    side_cable_notch_length: float | None = None,
    end_cable_notches: bool = False,
    end_cable_notch_depth: float | None = None,
    end_cable_notch_length: float | None = None,
    width: float | None = None,
    depth: float | None = None,
    mount_slot_length: float | None = None,
    center_wiring_channels: bool = True,
):
    w = params.shelf_width if width is None else width
    d = params.shelf_depth if depth is None else depth
    t = params.shelf_thickness
    shelf = box_at((w, d, t), (0.0, 0.0, t / 2.0))

    # M4 clearance holes align to the side-plate shelf ledges.
    for x in (-params.shelf_side_hole_x, params.shelf_side_hole_x):
        for y in (-params.shelf_side_hole_y, params.shelf_side_hole_y):
            if mount_slot_length is None:
                shelf -= cyl_z(params.m4_clearance_diameter / 2.0, 22.0, (x, y, t / 2.0))
            else:
                shelf -= horizontal_slot_z(
                    params.m4_clearance_diameter / 2.0,
                    mount_slot_length,
                    mount_slot_length,
                    22.0,
                    (x, y, t / 2.0),
                )

    if center_wiring_channels:
        # Open center wiring channels while leaving flat equipment space.
        for x in (-36.0, 0.0, 36.0):
            shelf -= box_at((10.0, 128.0, 20.0), (x, 0.0, t / 2.0))

    if side_cable_notches:
        notch_depth = (
            params.shelf_side_cable_notch_depth
            if side_cable_notch_depth is None
            else side_cable_notch_depth
        )
        notch_length = (
            params.shelf_side_cable_notch_length
            if side_cable_notch_length is None
            else side_cable_notch_length
        )
        for side in (-1, 1):
            shelf -= box_at(
                (notch_depth, notch_length, t + 4.0),
                (side * (w / 2.0 - notch_depth / 2.0), 0.0, t / 2.0),
            )

    if end_cable_notches:
        notch_depth = (
            params.shelf_side_cable_notch_depth
            if end_cable_notch_depth is None
            else end_cable_notch_depth
        )
        notch_length = (
            params.shelf_side_cable_notch_length
            if end_cable_notch_length is None
            else end_cable_notch_length
        )
        for side in (-1, 1):
            shelf -= box_at(
                (notch_length, notch_depth, t + 4.0),
                (0.0, side * (d / 2.0 - notch_depth / 2.0), t / 2.0),
            )

    return safe_chamfer(shelf, 0.5)

def make_bottom_cable_shelf(params: ChassisParams):
    w = params.bottom_cable_shelf_width
    d = params.bottom_cable_shelf_depth
    t = params.bottom_cable_shelf_thickness
    shelf = box_at((w, d, t), (0.0, 0.0, t / 2.0))

    for x, y in bottom_cable_pad_centers(params):
        shelf -= cyl_z(params.m4_clearance_diameter / 2.0, t + 4.0, (x, y, t / 2.0))

    return safe_chamfer(shelf, 0.5)

def make_shelf_spacer_block(params: ChassisParams):
    w = params.shelf_spacer_block_width
    d = params.shelf_spacer_block_depth
    h = params.shelf_spacer_block_height
    block = box_at((w, d, h), (0.0, 0.0, h / 2.0))
    block -= cyl_z(params.shelf_spacer_block_clearance_diameter / 2.0, h + 4.0, (0.0, 0.0, h / 2.0))
    return safe_chamfer(block, 0.8)
