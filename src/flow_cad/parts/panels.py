from __future__ import annotations
from build123d import Compound
from ..core.geometry import (
    box_at, 
    cyl_x, 
    cyl_y,
    cyl_z, 
    panel_dovetail_prism,
    tapered_xz_rect_loft,
    vertical_slot_y,
    fused_shapes,
    safe_chamfer
)
from ..core.utils import (
    front_rear_panel_slot_y_positions,
    front_rear_panel_retention_y_positions
)
from ..params import ChassisParams

SIDE_SCREW_Z_LEVELS = (220.0,)
REAR_SLIDE_TONGUE_LEAD_IN = 2.0

def panel_end_span_rib_depth(params: ChassisParams, total_depth: float) -> float:
    rib_depth = total_depth - params.wall_thickness
    if rib_depth <= 0.0:
        raise ValueError("Panel end span total depth must be greater than wall thickness")
    return rib_depth

def make_end_panel(params: ChassisParams, inward_y: int, cable_panel: bool):
    if inward_y not in (-1, 1):
        raise ValueError("inward_y must be -1 or 1")

    w = params.internal_width
    h = params.front_rear_panel_height
    t = params.wall_thickness

    skin = box_at((w, t, h), (0.0, inward_y * t / 2.0, h / 2.0))

    # Cut openings while the panel skin is still a simple solid.
    for x in params.vent_slot_centers_x:
        skin -= box_at(
            (params.vent_slot_width, t + 2.0, params.vent_slot_height),
            (x, inward_y * t / 2.0, params.vent_slot_center_z),
        )

    if cable_panel:
        for x in params.cable_pass_centers_x:
            skin -= box_at(
                (params.cable_pass_width, t + 2.0, params.cable_pass_height),
                (x, inward_y * t / 2.0, params.cable_pass_center_z),
            )

    components = [skin]
    rail_y = inward_y * (params.front_rear_panel_side_rail_depth / 2.0)

    rail_w = params.front_rear_panel_side_rail_width
    rail_d = params.front_rear_panel_side_rail_depth
    boss_d = params.front_rear_panel_retention_boss_depth
    boss_h = params.front_rear_panel_retention_boss_height
    boss_y = inward_y * (rail_d + boss_d / 2.0 - params.front_rear_panel_retention_boss_rail_overlap)
    for x in (-w / 2.0 + rail_w / 2.0, w / 2.0 - rail_w / 2.0):
        rail = box_at((rail_w, rail_d, h), (x, rail_y, h / 2.0))
        components.append(rail)
        boss = box_at((rail_w, boss_d, boss_h), (x, boss_y, SIDE_SCREW_Z_LEVELS[0]))
        boss -= cyl_x(
            params.m5_heatset_pilot_diameter / 2.0,
            params.front_rear_panel_m5_pilot_cut_length,
            (x, boss_y, SIDE_SCREW_Z_LEVELS[0]),
        )
        components.append(boss)

    for side in (-1, 1):
        components.append(
            panel_dovetail_prism(
                side=side,
                base_x=side * w / 2.0,
                center_y=rail_y,
                depth=params.panel_dovetail_depth,
                neck_width=params.panel_dovetail_neck_width,
                head_width=params.panel_dovetail_head_width,
                z_min=params.panel_dovetail_stop_height,
                z_max=h,
            )
        )

    rib_depth = panel_end_span_rib_depth(params, params.front_rear_panel_end_span_total_depth)
    end_span_y = inward_y * (t + rib_depth / 2.0)
    components.append(box_at((w, rib_depth, 18.0), (0.0, end_span_y, 9.0)))
    components.append(box_at((w, rib_depth, 18.0), (0.0, end_span_y, h - 9.0)))

    panel = components[0]
    for component in components[1:]:
        panel += component

    return safe_chamfer(panel, 0.7)

def make_rear_panel_body_for_bumpout(
    params: ChassisParams,
    dovetail_depth: float | None = None,
    dovetail_neck_width: float | None = None,
    dovetail_head_width: float | None = None,
    lower_span_total_depth: float | None = None,
    upper_span_total_depth: float | None = None,
):
    w = params.internal_width
    h = params.front_rear_panel_height
    t = params.wall_thickness
    inward_y = -1
    dovetail_depth = params.panel_dovetail_depth if dovetail_depth is None else dovetail_depth
    dovetail_neck_width = (
        params.panel_dovetail_neck_width if dovetail_neck_width is None else dovetail_neck_width
    )
    dovetail_head_width = (
        params.panel_dovetail_head_width if dovetail_head_width is None else dovetail_head_width
    )
    lower_span_total_depth = (
        params.front_rear_panel_end_span_total_depth
        if lower_span_total_depth is None
        else lower_span_total_depth
    )
    upper_span_total_depth = (
        params.front_rear_panel_end_span_total_depth
        if upper_span_total_depth is None
        else upper_span_total_depth
    )

    panel = box_at((w, t, h), (0.0, inward_y * t / 2.0, h / 2.0))
    rail_y = inward_y * (params.front_rear_panel_side_rail_depth / 2.0)

    rail_w = params.front_rear_panel_side_rail_width
    rail_d = params.front_rear_panel_side_rail_depth
    boss_d = params.front_rear_panel_retention_boss_depth
    boss_h = params.front_rear_panel_retention_boss_height
    boss_y = inward_y * (rail_d + boss_d / 2.0 - params.front_rear_panel_retention_boss_rail_overlap)
    for x in (-w / 2.0 + rail_w / 2.0, w / 2.0 - rail_w / 2.0):
        rail = box_at((rail_w, rail_d, h), (x, rail_y, h / 2.0))
        panel += rail
        boss = box_at((rail_w, boss_d, boss_h), (x, boss_y, SIDE_SCREW_Z_LEVELS[0]))
        boss -= cyl_x(
            params.m5_heatset_pilot_diameter / 2.0,
            params.front_rear_panel_m5_pilot_cut_length,
            (x, boss_y, SIDE_SCREW_Z_LEVELS[0]),
        )
        panel += boss

    for side in (-1, 1):
        panel += panel_dovetail_prism(
            side=side,
            base_x=side * w / 2.0,
            center_y=rail_y,
            depth=dovetail_depth,
            neck_width=dovetail_neck_width,
            head_width=dovetail_head_width,
            z_min=params.panel_dovetail_stop_height,
            z_max=h,
        )

    lower_span_rib_depth = panel_end_span_rib_depth(params, lower_span_total_depth)
    upper_span_rib_depth = panel_end_span_rib_depth(params, upper_span_total_depth)
    lower_span_y = inward_y * (t + lower_span_rib_depth / 2.0)
    upper_span_y = inward_y * (t + upper_span_rib_depth / 2.0)
    panel += box_at((w, lower_span_rib_depth, 18.0), (0.0, lower_span_y, 9.0))
    panel += box_at((w, upper_span_rib_depth, 18.0), (0.0, upper_span_y, h - 9.0))

    bw = params.rear_bumpout_width
    bh = params.rear_bumpout_height
    fw = params.rear_bumpout_face_width
    fh = params.rear_bumpout_face_height
    bd = params.rear_bumpout_depth
    wall = params.rear_bumpout_wall_thickness
    bz = params.rear_bumpout_center_z
    cavity_min_y = -t - 1.0
    cavity_max_y = bd - wall
    panel -= tapered_xz_rect_loft(
        bw - 2.0 * wall,
        bh - 2.0 * wall,
        cavity_min_y,
        fw - 2.0 * wall,
        fh - 2.0 * wall,
        cavity_max_y,
        bz,
    )

    return safe_chamfer(panel, 0.7)

def make_rear_panel_bumpout_shell(params: ChassisParams):
    bw = params.rear_bumpout_width
    bh = params.rear_bumpout_height
    fw = params.rear_bumpout_face_width
    fh = params.rear_bumpout_face_height
    bd = params.rear_bumpout_depth
    wall = params.rear_bumpout_wall_thickness
    bz = params.rear_bumpout_center_z
    overlap = params.rear_bumpout_body_overlap

    shell = tapered_xz_rect_loft(bw, bh, -overlap, fw, fh, bd, bz)
    shell -= tapered_xz_rect_loft(
        bw - 2.0 * wall,
        bh - 2.0 * wall,
        -params.wall_thickness - 1.0,
        fw - 2.0 * wall,
        fh - 2.0 * wall,
        bd - wall,
        bz,
    )
    return safe_chamfer(shell, 0.7)

def make_rear_panel_bumpout(params: ChassisParams):
    return Compound(
        children=[make_rear_panel_body_for_bumpout(params), make_rear_panel_bumpout_shell(params)],
        label="erb_lower_chassis_rear_panel",
    )

def make_rear_slide_entry_relief_cut(params: ChassisParams, center_x: float):
    z_min = params.rear_slide_channel_z_min
    receiver_z_min = z_min - params.rear_slide_stop_height
    head_slot = params.rear_slide_head_width + 2.0 * params.rear_slide_side_clearance
    neck_slot = params.rear_slide_neck_width + 2.0 * params.rear_slide_side_clearance
    backing_y_min = -params.wall_thickness
    backing_y_max = (
        params.rear_bumpout_detachable_base_gap
        - REAR_SLIDE_TONGUE_LEAD_IN
        - params.rear_slide_face_clearance
    )
    lip_y_min = params.rear_slide_channel_depth - params.rear_slide_lip_depth
    entry_clearance = params.rear_slide_entry_relief_clearance
    entry_z_min = receiver_z_min - entry_clearance
    entry_z_max = z_min + params.rear_slide_entry_relief_height
    entry_z_height = entry_z_max - entry_z_min
    entry_z_center = (entry_z_min + entry_z_max) / 2.0
    head_y_min = backing_y_min - entry_clearance
    relief = box_at(
        (
            head_slot + 2.0 * entry_clearance,
            lip_y_min - head_y_min,
            entry_z_height,
        ),
        (center_x, (head_y_min + lip_y_min) / 2.0, entry_z_center),
    )
    relief += box_at(
        (
            neck_slot + 2.0 * entry_clearance,
            params.rear_slide_channel_depth - lip_y_min + 2.0,
            entry_z_height,
        ),
        (center_x, (lip_y_min + params.rear_slide_channel_depth + 2.0) / 2.0, entry_z_center),
    )
    return relief

def make_rear_bumpout_shell_entry_relief_cut(
    params: ChassisParams,
    center_x: float,
    head_width: float,
):
    z_min = params.rear_slide_channel_z_min
    shell_z_min = params.rear_bumpout_center_z - params.rear_bumpout_height / 2.0
    entry_clearance = params.rear_slide_entry_relief_clearance
    entry_z_max = z_min + params.rear_slide_entry_relief_height
    entry_z_height = entry_z_max - (shell_z_min - entry_clearance)
    entry_z_center = shell_z_min - entry_clearance + entry_z_height / 2.0
    head_y_min = (
        params.rear_bumpout_detachable_base_gap
        - REAR_SLIDE_TONGUE_LEAD_IN
        - entry_clearance
    )
    relief_y_max = (
        params.rear_bumpout_detachable_base_gap
        + params.rear_bumpout_wall_thickness
        + entry_clearance
    )
    return box_at(
        (
            head_width + 2.0 * (params.rear_slide_channel_wall + entry_clearance),
            relief_y_max - head_y_min,
            entry_z_height,
        ),
        (center_x, (head_y_min + relief_y_max) / 2.0, entry_z_center),
    )

def make_rear_slide_receiver(params: ChassisParams, center_x: float):
    z_min = params.rear_slide_channel_z_min
    z_max = params.rear_slide_channel_z_max
    wall = params.rear_slide_channel_wall
    depth = params.rear_slide_channel_depth
    lip_depth = params.rear_slide_lip_depth
    head_slot = params.rear_slide_head_width + 2.0 * params.rear_slide_side_clearance
    neck_slot = params.rear_slide_neck_width + 2.0 * params.rear_slide_side_clearance
    total_w = head_slot + 2.0 * wall
    backing_y_max = (
        params.rear_bumpout_detachable_base_gap
        - REAR_SLIDE_TONGUE_LEAD_IN
        - params.rear_slide_face_clearance
    )
    backing_y_min = -params.wall_thickness
    receiver_z_min = z_min - params.rear_slide_stop_height
    receiver_z_height = z_max - receiver_z_min
    receiver_z_center = (receiver_z_min + z_max) / 2.0
    top_embed_z_height = 8.0
    top_embed_z_center = z_max + top_embed_z_height / 2.0
    shell_clearance_y = params.rear_bumpout_detachable_base_gap
    root_bridge_y_depth = shell_clearance_y - backing_y_max
    slot_z_height = z_max - z_min + 2.0
    slot_z_center = z_min + slot_z_height / 2.0
    lip_y_min = depth - lip_depth
    outer_receiver_x = params.rear_slide_rail_x + head_slot / 2.0 + wall
    weld_width = params.rear_slide_outer_weld_width
    weld_depth = params.rear_slide_outer_weld_depth
    weld_height = z_max - z_min + 2.0 * params.rear_slide_outer_weld_z_extra
    weld_center_z = (z_min + z_max) / 2.0
    weld_y_max = params.rear_bumpout_detachable_base_gap + params.rear_slide_face_clearance / 2.0
    weld_center_y = weld_y_max - weld_depth / 2.0

    receiver = box_at(
        (total_w + 2.0, depth - backing_y_min, receiver_z_height),
        (center_x, (backing_y_min + depth) / 2.0, receiver_z_center),
    )
    receiver += box_at(
        (total_w + 2.0, backing_y_max - backing_y_min, top_embed_z_height),
        (center_x, (backing_y_min + backing_y_max) / 2.0, top_embed_z_center),
    )
    receiver += box_at(
        (wall, root_bridge_y_depth, top_embed_z_height),
        (
            center_x - head_slot / 2.0 - wall / 2.0,
            (backing_y_max + shell_clearance_y) / 2.0,
            top_embed_z_center,
        ),
    )
    receiver += box_at(
        (wall, root_bridge_y_depth, top_embed_z_height),
        (
            center_x + head_slot / 2.0 + wall / 2.0,
            (backing_y_max + shell_clearance_y) / 2.0,
            top_embed_z_center,
        ),
    )
    receiver -= box_at(
        (head_slot, lip_y_min - backing_y_max, slot_z_height),
        (center_x, (backing_y_max + lip_y_min) / 2.0, slot_z_center),
    )
    receiver -= box_at(
        (neck_slot, depth - lip_y_min + 2.0, slot_z_height),
        (center_x, (lip_y_min + depth + 2.0) / 2.0, slot_z_center),
    )
    receiver -= make_rear_slide_entry_relief_cut(params, center_x)
    for side in (-1, 1):
        if center_x * side > 0.0:
            weld_center_x = side * (
                outer_receiver_x + weld_width / 2.0 - params.rear_slide_outer_weld_overlap
            )
            receiver += box_at(
                (weld_width, weld_depth, weld_height),
                (weld_center_x, weld_center_y, weld_center_z),
            )
    return safe_chamfer(receiver, 0.15)

def make_rear_slide_support_webs(params: ChassisParams):
    lower_z_min = params.rear_slide_lower_web_z_min
    lower_z_max = params.rear_slide_lower_web_z_max
    upper_z_min = params.rear_slide_upper_web_z_min
    upper_z_max = params.rear_slide_upper_web_z_max
    top_z_min = params.rear_slide_top_web_z_min
    top_z_max = params.rear_slide_top_web_z_max
    lower = box_at(
        (
            params.rear_slide_lower_web_width,
            params.rear_slide_web_depth,
            lower_z_max - lower_z_min,
        ),
        (
            0.0,
            -params.wall_thickness - params.rear_slide_web_depth / 2.0 + 1.0,
            (lower_z_min + lower_z_max) / 2.0,
        ),
    )
    upper = box_at(
        (
            params.rear_slide_upper_web_width,
            params.rear_slide_web_depth,
            upper_z_max - upper_z_min,
        ),
        (
            0.0,
            -params.rear_slide_web_depth / 2.0,
            (upper_z_min + upper_z_max) / 2.0,
        ),
    )
    top = box_at(
        (
            params.rear_slide_upper_web_width,
            params.rear_slide_web_depth,
            top_z_max - top_z_min,
        ),
        (
            0.0,
            -params.rear_slide_web_depth / 2.0,
            (top_z_min + top_z_max) / 2.0,
        ),
    )
    return safe_chamfer(fused_shapes(lower, upper, top), 0.35)

def make_rear_panel_detachable_body(params: ChassisParams):
    panel = make_rear_panel_body_for_bumpout(
        params,
        dovetail_depth=params.rear_detachable_panel_dovetail_depth,
        dovetail_neck_width=params.rear_detachable_panel_dovetail_neck_width,
        dovetail_head_width=params.rear_detachable_panel_dovetail_head_width,
        lower_span_total_depth=params.rear_detachable_panel_lower_span_total_depth,
    )
    panel += make_rear_slide_support_webs(params)

    for x in (-params.rear_slide_rail_x, params.rear_slide_rail_x):
        panel += make_rear_slide_receiver(params, x)
        panel -= make_rear_slide_entry_relief_cut(params, x)

    boss = box_at(
        (
            params.rear_slide_retain_boss_width,
            params.rear_slide_retain_boss_depth,
            params.rear_slide_retain_boss_height,
        ),
        (
            0.0,
            -params.rear_slide_retain_boss_depth / 2.0,
            params.rear_slide_retain_screw_z,
        ),
    )
    boss -= cyl_y(
        params.m4_heatset_pilot_diameter / 2.0,
        params.rear_slide_retain_boss_depth + 2.0,
        (0.0, -params.rear_slide_retain_boss_depth / 2.0, params.rear_slide_retain_screw_z),
    )
    panel += boss
    return safe_chamfer(panel, 0.45)

def make_rear_panel_detachable_bumpout_shell(
    params: ChassisParams,
    head_width: float | None = None,
    head_depth: float | None = None,
):
    if head_width is None: head_width = params.rear_slide_head_width
    if head_depth is None: head_depth = params.rear_slide_head_depth

    bw = params.rear_bumpout_width
    bh = params.rear_bumpout_height
    fw = params.rear_bumpout_face_width
    fh = params.rear_bumpout_face_height
    bd = params.rear_bumpout_depth
    wall = params.rear_bumpout_wall_thickness
    bz = params.rear_bumpout_center_z
    base_y = params.rear_bumpout_detachable_base_gap

    shell = tapered_xz_rect_loft(bw, bh, base_y, fw, fh, bd, bz)
    shell -= tapered_xz_rect_loft(
        bw - 2.0 * wall,
        bh - 2.0 * wall,
        base_y - 1.0,
        fw - 2.0 * wall,
        fh - 2.0 * wall,
        bd - wall,
        bz,
    )
    shell -= vertical_slot_y(
        params.m4_clearance_diameter / 2.0,
        params.rear_slide_retain_slot_height,
        bd + 6.0,
        (0.0, bd / 2.0, params.rear_slide_retain_screw_z),
    )
    for x in (-params.rear_slide_rail_x, params.rear_slide_rail_x):
        shell -= make_rear_bumpout_shell_entry_relief_cut(params, x, head_width)

    tongue_z = params.rear_bumpout_center_z
    head_y_min = base_y - REAR_SLIDE_TONGUE_LEAD_IN
    head_center_y = head_y_min + head_depth / 2.0
    head_y_max = head_y_min + head_depth
    connector_y_min = head_y_max - 0.2
    connector_y_max = bd - 0.4
    connector_depth = connector_y_max - connector_y_min
    for x in (-params.rear_slide_rail_x, params.rear_slide_rail_x):
        head = box_at(
            (
                head_width,
                head_depth,
                params.rear_slide_tongue_height,
            ),
            (x, head_center_y, tongue_z),
        )
        connector = box_at(
            (
                params.rear_slide_neck_width,
                connector_depth,
                params.rear_slide_tongue_height,
            ),
            (x, (connector_y_min + connector_y_max) / 2.0, tongue_z),
        )
        shell = fused_shapes(shell, head, connector)

    return safe_chamfer(shell, 0.45)

def make_rear_panel_detachable_bumpout(params: ChassisParams):
    return Compound(
        children=[make_rear_panel_detachable_body(params), make_rear_panel_detachable_bumpout_shell(params)],
        label="erb_lower_chassis_rear_panel_detachable",
    )

def make_rear_panel_detachable_bumpout_shell_tpu(params: ChassisParams):
    return make_rear_panel_detachable_bumpout_shell(
        params,
        head_width=params.rear_slide_tpu_head_width,
        head_depth=params.rear_slide_tpu_head_depth,
    )
