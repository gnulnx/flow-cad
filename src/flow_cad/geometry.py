"""Stable, opt-in geometry helpers for downstream Flow CAD projects.

Importing this module intentionally loads Build123d. Metadata-only runtime
paths must depend on :mod:`flow_cad.sdk` instead.
"""

from .core.geometry import (
    add_diagonal_rib,
    box_at,
    chamfered_rect_points,
    chamfered_xy_rect_prism,
    chamfered_yz_rect_prism,
    cyl_x,
    cyl_y,
    cyl_z,
    double_d_points,
    double_d_prism,
    fused_shapes,
    horizontal_slot_z,
    panel_dovetail_points,
    panel_dovetail_prism,
    safe_chamfer,
    solid_shape,
    tapered_xz_rect_loft,
    triangular_xz_prism,
    triangular_yz_prism,
    vertical_slot_y,
    xy_polygon_prism,
    xz_profile_prism,
    xz_rect,
    xz_rects_overlap_with_clearance,
)

__all__ = [
    "add_diagonal_rib",
    "box_at",
    "chamfered_rect_points",
    "chamfered_xy_rect_prism",
    "chamfered_yz_rect_prism",
    "cyl_x",
    "cyl_y",
    "cyl_z",
    "double_d_points",
    "double_d_prism",
    "fused_shapes",
    "horizontal_slot_z",
    "panel_dovetail_points",
    "panel_dovetail_prism",
    "safe_chamfer",
    "solid_shape",
    "tapered_xz_rect_loft",
    "triangular_xz_prism",
    "triangular_yz_prism",
    "vertical_slot_y",
    "xy_polygon_prism",
    "xz_profile_prism",
    "xz_rect",
    "xz_rects_overlap_with_clearance",
]
