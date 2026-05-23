from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ChassisParams:
    project_id: str = "b3"
    center_box_outer_width: float = 240.0
    box_depth: float = 256.0
    box_height: float = 240.0
    side_plate_thickness: float = 12.0
    wall_thickness: float = 6.0
    bottom_thickness: float = 10.0
    top_lid_thickness: float = 6.0
    axle_center_height_from_bottom: float = 58.0

    wheel_diameter: float = 260.0
    wheel_width: float = 100.0
    wheel_overall_width: float = 480.0
    wheel_side_clearance: float = 20.0
    wheel_reference_hub_diameter: float = 128.0
    wheel_reference_rim_diameter: float = 176.0
    wheel_reference_hub_thickness: float = 22.0
    wheel_reference_axle_visible_length: float = 75.0
    axle_nominal_diameter: float = 16.0
    axle_nominal_flat_to_flat: float = 12.0

    reinforced_boss_total_thickness: float = 30.0
    axle_boss_depth: float = 122.0
    axle_boss_height: float = 96.0
    side_rib_projection: float = 18.0
    side_rail_projection: float = 18.0

    insert_size: float = 76.0
    insert_thickness: float = 30.0
    insert_pocket_size: float = 79.0
    insert_corner_chamfer: float = 7.0
    insert_pocket_corner_chamfer: float = 9.0
    insert_retainer_flange_width: float = 140.0
    insert_retainer_flange_height: float = 116.0
    insert_retainer_flange_center_z: float = 8.0
    insert_retainer_flange_thickness: float = 6.0
    insert_retainer_flange_chamfer: float = 10.0
    insert_bolt_offset_y: float = 52.0
    insert_bolt_offset_z: float = 42.0
    axle_tab_washer_relief_width: float = 12.0
    axle_tab_washer_relief_height: float = 12.0
    axle_tab_washer_relief_depth: float = 3.2
    axle_tab_washer_relief_radial_clearance: float = 1.5

    m5_clearance_diameter: float = 5.5
    m5_heatset_pilot_diameter: float = 6.1
    m5_washer_counterbore_diameter: float = 11.0
    m4_clearance_diameter: float = 4.5
    m4_heatset_pilot_diameter: float = 5.0
    m3_clearance_diameter: float = 3.4

    assembly_clearance: float = 1.0
    internal_width: float = 180.0
    internal_depth: float = 200.0
    bottom_tray_depth: float = 204.0
    front_rear_panel_height: float = 240.0
    top_lid_width: float = 240.0
    top_lid_depth: float = 256.0
    shelf_width: float = 180.0
    shelf_depth: float = 200.0
    shelf_thickness: float = 6.0
    shelf_z_levels: tuple[float, float] = (74.0, 122.0)
    shelf_side_ledge_z_levels: tuple[float, float] = (122.0, 183.0)
    shelf_side_ledge_height: float = 8.0
    shelf_side_ledge_depth: float = 46.0
    shelf_side_ledge_segment_length: float = 54.0
    shelf_side_ledge_wall_overlap: float = 6.0
    shelf_side_gusset_height: float = 22.0
    shelf_side_gusset_thickness: float = 5.0
    shelf_side_gusset_bolt_clearance_offset: float = 18.0
    shelf_side_segment_centers_y: tuple[float, ...] = (-75.0, 75.0)
    shelf_side_hole_x: float = 75.0
    shelf_side_hole_y: float = 75.0
    shelf_side_cable_notch_depth: float = 46.0
    shelf_side_cable_notch_shallow_depth: float = 23.0
    shelf_side_cable_notch_length: float = 84.0

    def validate_params(self):
        """Mechanical contract validation to prevent 'vibe' errors."""
        # 1. Shelf Connectivity Contract (The most critical one)
        half_width = self.shelf_width / 2
        notch_edge = half_width - self.shelf_side_cable_notch_depth
        if notch_edge < (self.shelf_width * 0.1):
             raise ValueError(f"CRITICAL: Shelf side notches too deep ({self.shelf_side_cable_notch_depth}mm). "
                              f"Remaining bridge {notch_edge}mm is below safety threshold.")

        # 2. Chassis Envelope Contract
        if self.center_box_outer_width < self.internal_width + (2 * self.wall_thickness):
            raise ValueError("Chassis outer width must accommodate internal width plus walls.")

        # 3. Axle Height Contract
        if self.axle_center_height_from_bottom < self.bottom_thickness + 5:
            raise ValueError("Axle center is too low; it will collide with the bottom tray.")

        # 4. Battery Cassette Fit
        if hasattr(self, 'battery_cassette_width') and self.battery_cassette_width > self.internal_width:
            raise ValueError("Battery cassette is wider than the internal chassis width.")

        # 5. Rear detachable bumpout TPU variant must still have a real T profile.
        if not self.rear_slide_neck_width < self.rear_slide_tpu_head_width < self.rear_slide_head_width:
            raise ValueError("TPU rear slide head width must be between the neck width and PETG head width.")
        if not 0.0 < self.rear_slide_tpu_head_depth < self.rear_slide_head_depth:
            raise ValueError("TPU rear slide head depth must be positive and less than PETG head depth.")

        print("Mechanical contracts validated successfully.")

    service_shelf_width: float = 170.0
    service_shelf_depth: float = 188.0
    service_shelf_mount_slot_length: float = 14.0
    service_shelf_side_relief_depth: float = 36.0
    service_shelf_side_relief_length: float = 84.0
    shelf_spacer_block_width: float = 20.0
    shelf_spacer_block_depth: float = 50.0
    shelf_spacer_block_height: float = 55.0
    shelf_spacer_block_clearance_diameter: float = 4.5
    front_rear_panel_side_rail_width: float = 18.0
    front_rear_panel_side_rail_depth: float = 26.0
    front_rear_panel_retention_boss_depth: float = 14.0
    front_rear_panel_retention_boss_height: float = 22.0
    front_rear_panel_retention_boss_rail_overlap: float = 4.0
    front_rear_panel_m5_pilot_cut_length: float = 24.0
    front_rear_panel_end_span_total_depth: float = 20.0
    panel_dovetail_depth: float = 10.0
    panel_dovetail_neck_width: float = 9.0
    panel_dovetail_head_width: float = 15.0
    panel_dovetail_clearance: float = 0.25
    rear_detachable_panel_dovetail_depth: float = 9.25
    rear_detachable_panel_dovetail_neck_width: float = 8.0
    rear_detachable_panel_dovetail_head_width: float = 14.0
    rear_detachable_panel_lower_span_total_depth: float = 12.0
    panel_dovetail_stop_height: float = 8.0
    panel_dovetail_root_relief_radius: float = 1.0
    vent_slot_centers_x: tuple[float, ...] = (-38.0, -19.0, 0.0, 19.0, 38.0)
    vent_slot_width: float = 8.0
    vent_slot_height: float = 116.0
    vent_slot_center_z: float = 146.0
    cable_pass_centers_x: tuple[float, ...] = (-28.0, 28.0)
    cable_pass_width: float = 22.0
    cable_pass_height: float = 30.0
    cable_pass_center_z: float = 64.0
    panel_feature_clearance: float = 4.0
    rear_bumpout_width: float = 132.0
    rear_bumpout_height: float = 192.0
    rear_bumpout_face_width: float = 104.0
    rear_bumpout_face_height: float = 164.0
    rear_bumpout_center_z: float = 120.0
    rear_bumpout_depth: float = 22.0
    rear_bumpout_wall_thickness: float = 3.2
    rear_bumpout_body_overlap: float = 0.2
    rear_bumpout_detachable_base_gap: float = 0.35
    rear_slide_rail_x: float = 46.0
    rear_slide_channel_z_min: float = 40.0
    rear_slide_channel_z_max: float = 207.0
    rear_slide_stop_height: float = 4.0
    rear_slide_head_width: float = 10.0
    rear_slide_tpu_head_width: float = 8.0
    rear_slide_head_depth: float = 2.3
    rear_slide_tpu_head_depth: float = 1.75
    rear_slide_neck_width: float = 5.0
    rear_slide_side_clearance: float = 0.45
    rear_slide_face_clearance: float = 0.40
    rear_slide_channel_wall: float = 3.0
    rear_slide_channel_depth: float = 5.6
    rear_slide_lip_depth: float = 2.25
    rear_slide_tongue_height: float = 160.0
    rear_slide_retain_screw_z: float = 206.0
    rear_slide_retain_slot_height: float = 8.0
    rear_slide_retain_boss_depth: float = 12.0
    rear_slide_retain_boss_width: float = 22.0
    rear_slide_retain_boss_height: float = 20.0
    rear_slide_lower_web_width: float = 144.0
    rear_slide_upper_web_width: float = 128.0
    rear_slide_web_depth: float = 10.0
    rear_slide_lower_web_z_min: float = 18.0
    rear_slide_lower_web_z_max: float = 30.0
    rear_slide_upper_web_z_min: float = 30.0
    rear_slide_upper_web_z_max: float = 40.0
    rear_slide_top_web_z_min: float = 207.0
    rear_slide_top_web_z_max: float = 216.0
    rear_slide_outer_weld_width: float = 10.0
    rear_slide_outer_weld_depth: float = 10.0
    rear_slide_outer_weld_overlap: float = 3.25
    rear_slide_outer_weld_z_extra: float = 1.5
    battery_measured_length: float = 155.0
    battery_measured_width: float = 50.0
    battery_measured_height: float = 50.0
    battery_cassette_width: float = 124.0
    battery_cassette_length: float = 176.0
    battery_cassette_floor_thickness: float = 3.0
    battery_cassette_lip_height: float = 7.0
    battery_cassette_lip_thickness: float = 3.0
    battery_cassette_end_lip_width: float = 42.0
    battery_cassette_center_divider_width: float = 4.0
    battery_cassette_strap_slot_width: float = 6.0
    battery_cassette_strap_slot_length: float = 24.0
    battery_cassette_strap_y_positions: tuple[float, ...] = (-48.0, 48.0)
    battery_cassette_latch_tab_width: float = 46.0
    battery_cassette_latch_tab_length: float = 14.0
    battery_cassette_latch_offset_y: float = 5.0
    battery_tray_recess_depth: float = 0.0
    battery_tray_recess_width: float = 180.0
    battery_tray_recess_length: float = 204.0
    battery_tray_recess_floor_thickness: float = 10.0
    battery_tray_recess_wall_thickness: float = 4.0
    battery_tray_recess_side_taper: float = 0.0
    battery_tray_guide_rail_width: float = 4.0
    battery_tray_guide_rail_height: float = 7.0
    battery_tray_guide_rail_length: float = 172.0
    battery_tray_guide_inner_clearance_width: float = 126.0
    bottom_tray_side_rail_width: float = 18.0
    bottom_tray_side_rail_height: float = 71.0
    bottom_tray_mount_hole_length: float = 28.0
    bottom_tray_mount_hole_y_positions: tuple[float, ...] = (-82.0, 82.0)
    bottom_tray_mount_hole_z_levels: tuple[float, ...] = (16.0, 58.0)
    battery_cassette_assembly_z: float = 4.2
    integrated_battery_lane_width: float = 51.0
    integrated_battery_lane_length: float = 164.0
    integrated_battery_outer_rib_length: float = 148.0
    integrated_battery_outer_offset: float = 3.0
    integrated_battery_outer_rib_width: float = 2.0
    integrated_battery_outer_rib_height: float = 7.0
    integrated_center_spine_outer_width: float = 32.0
    integrated_center_spine_wall_thickness: float = 2.0
    integrated_center_spine_height: float = 50.0
    integrated_imu_pad_size: float = 30.0
    integrated_imu_pad_thickness: float = 4.0
    integrated_bridge_underside_z: float = 63.0
    integrated_bridge_thickness: float = 8.0
    integrated_bridge_depth: float = 37.0
    integrated_bridge_span_width: float = 180.0
    integrated_bridge_side_post_width: float = 0.0
    integrated_bridge_cable_slot_width: float = 24.0

    # Simple mounting plate
    simple_mounting_plate_width: float = 36.0
    simple_mounting_plate_length: float = 135.0
    simple_mounting_plate_thickness: float = 10.0
    simple_mounting_plate_hole_offset: float = 10.0
