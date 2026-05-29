# Part Interface Registry

This file records the active mechanical mating contracts that agents must check before changing CAD geometry. The authoritative source of truth is the `src/flow_cad/` package (entry point `src/flow_cad/main.py`). Use this registry to identify the mating pair, coordinate frame, critical dimensions, and validation path before editing source.

Global coordinate convention:

- X is robot width / left-right.
- Y is front/rear depth.
- Z is vertical.

When changing any interface below, update this file if the mating contract changes. Keep historical design narrative out of this file; record only current contracts and checks.

## Interface Checklist

For every mating-interface change:

1. Identify fixed part, moving part, STEP files, and source functions.
2. State install/slide direction, capture direction, and clearance or lead-in direction.
3. Define the Clearance Budget (Negative Space): Explicitly state the required gap (e.g., `P.panel_dovetail_clearance`) to ensure the part is printable and assemblable; avoid "perfectly flush" geometry.
4. Measure current feature positions on both parts before editing.
5. Regenerate STEP files after editing.
6. Re-measure the same features after editing.
7. Validate direct part-pair clearance or overlap, not only full assembly interference.
8. Sync viewer assets only after source geometry validates.

## Rear Detachable Panel Slide

Purpose: removable rear cable bumpout slides onto the fixed rear-panel receiver.

Fixed part:

- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_detachable_body.step`
- Source: `make_rear_panel_detachable_body()` in `src/flow_cad/parts/panels.py`
- Nominal bbox: `198.5 W x 41.6 D x 240.0 H mm`

Moving part:

- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_detachable_bumpout.step`
- TPU test variant: `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_detachable_bumpout_TPU.step`
- Source: `make_rear_panel_detachable_bumpout_shell()` in `src/flow_cad/parts/panels.py`
- Nominal bbox: `132.0 W x 23.7 D x 192.0 H mm`

Interface contract:

- Interface type: vertical slide T-slot / receiver.
- Install direction: Z.
- Capture direction: X.
- Proud lead-in direction: Y.
- Rail centers: X `+/- P.rear_slide_rail_x`.
- Receiver side clearance: `P.rear_slide_side_clearance`.
- Front/back capture clearance: `P.rear_slide_face_clearance`.
- Fixed receiver rail roots must have continuous full-height backing to the panel wall and hidden side-wall bridges so the visible T-slot walls are tied into the body at the middle and top of the slide.
- Fixed receiver outer walls also include source-generated weld blocks matching the FreeCAD Part boolean-fuse repair reference `JOHN_reap_panel_body.step`; these blocks must overlap the receiver wall but stay outside the bumpout shell envelope.
- Fixed receiver bottoms include two local T-profile entry reliefs centered on the rail centers. These reliefs open only the lower entry zone so rigid PETG bumpout heads can start into the receiver before the shell perimeter contacts the panel.
- Required behavior: bumpout T heads must protrude in Y past the shell rim enough to enter the rear-panel receiver before the shell perimeter contacts the panel.
- The retaining M4 screw prevents upward sliding only; it must not carry the main alignment load.
- TPU test variant keeps the receiver, neck width, Y proud lead-in, and retaining slot unchanged, but reduces the T-head X capture width from `P.rear_slide_head_width` to `P.rear_slide_tpu_head_width` and the T-head Y capture depth from `P.rear_slide_head_depth` to `P.rear_slide_tpu_head_depth`.

Validation:

- Generate: `flow cad build`
- Pair check: directly intersect `make_rear_panel_detachable_body()` and `make_rear_panel_detachable_bumpout_shell()` in seated position; expected overlap is `0.0 mm^3`.
- Feature check: T-head Y minimum must be proud of the shell rim by the intended lead-in, while the receiver backing leaves at least `P.rear_slide_face_clearance`. For TPU, also confirm the T-head X width is `P.rear_slide_tpu_head_width` and Y depth is `P.rear_slide_tpu_head_depth`.
- Root check: probe the receiver side-wall root at mid-slide and top-slide height; both must contain material while the central T-head channel and lower entry reliefs remain open.
- Viewer files: inspect both individual STEP files and `erb_lower_chassis_rear_panel_detachable.step`.

## Side Plates To Front/Rear Panels

Purpose: front and rear panels slide down into stopped side-plate dovetail slots and are retained by top screws.

Fixed parts:

- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_left_side_plate.step`
- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_right_side_plate.step`
- Source: `make_side_plate()` in `src/flow_cad/parts/chassis.py`
- Nominal bbox each: `52.0 W x 256.0 D x 240.0 H mm`

Moving parts:

- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_front_panel.step`
- Source: `make_end_panel()` in `src/flow_cad/parts/panels.py`
- Nominal bbox: `200.0 W x 36.0 D x 240.0 H mm`
- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel.step`
- Source: `make_rear_panel_bumpout()` in `src/flow_cad/parts/panels.py`
- Nominal bbox: `200.0 W x 58.0 D x 240.0 H mm`
- Alternate rear detachable body: `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_detachable_body.step`

Interface contract:

- Interface type: stopped dovetail panel rails into side-plate slots.
- Install direction: Z.
- Capture direction: X.
- Depth/seat direction: Y.
- Front/rear panel side rails sit at Y `+/- P.box_depth / 2`.
- Dovetail clearance comes from `P.panel_dovetail_clearance`.
- Detachable rear panel uses loosened rear-panel dovetail dimensions: `P.rear_detachable_panel_dovetail_depth`, `P.rear_detachable_panel_dovetail_neck_width`, and `P.rear_detachable_panel_dovetail_head_width`.
- Top M5 retention screws prevent upward motion; dovetails carry alignment.

Validation:

- Generate: `flow cad build`
- Mounting check: `python scripts/check_mounting_features.py`
- Assembly check: `python scripts/check_assembly_interference.py`
- Confirm front/rear top retention hole centers match side-plate top retention holes before changing rail or boss geometry.

## Top Lid Carry Handles

Purpose: two printed handles bolt to the top lid so the chassis is easier to carry.

Fixed part:

- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_top_lid.step`
- Source: `make_top_lid()` in `src/flow_cad/parts/chassis.py`

Moving part:

- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_lid_handle.step`
- Source: `make_lid_handle()` in `src/flow_cad/parts/chassis.py`
- Print quantity: 2

Interface contract:

- Interface type: M5 screw-mounted handle pair.
- Install direction / screw axis: Z.
- Lid handle centers: X `+/- P.top_lid_handle_center_x_abs`, Y `0`.
- Per-handle M5 screw centers: Y `+/- P.top_lid_handle_screw_spacing_y / 2`.
- Both lid and handle use `P.m5_clearance_diameter` through-holes. Handle top counterbores use `P.m5_washer_counterbore_diameter`.
- Clearance budget: screw holes are clearance holes only; the handle is located by the screw shanks and clamping load, not by tight bosses.

Validation:

- Generate: `flow cad build`
- Feature check: confirm four lid M5 through-holes at X `+/- P.top_lid_handle_center_x_abs`, Y `+/- P.top_lid_handle_screw_spacing_y / 2`.
- Pair check: confirm one handle has matching through-holes at Y `+/- P.top_lid_handle_screw_spacing_y / 2`.

## Bottom Tray To Side Plates

Purpose: bottom tray spans the lower chassis, locates between side plates, and bolts into the side structure.

Fixed parts:

- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_left_side_plate.step`
- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_right_side_plate.step`
- Source: `make_side_plate()` in `src/flow_cad/parts/chassis.py`

Moving part:

- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_bottom_tray.step`
- Source: `make_bottom_tray()` in `src/flow_cad/parts/chassis.py`
- Nominal bbox: `180.0 W x 204.0 D x 71.0 H mm`

Interface contract:

- Interface type: tray span and side M5 mounting screws.
- Install direction: Z into the lower chassis envelope.
- Width fit direction: X.
- Depth fit direction: Y.
- Tray uses the fit-safe internal envelope, not the outside side-plate width.
- Mounting holes must remain aligned with side-plate lower floor and raised tower holes.
- The integrated battery cage and center electronics spine must not block the side-plate axle boss zone.

Validation:

- Generate: `flow cad build`
- Mounting check: `python scripts/check_mounting_features.py`
- Assembly check: `python scripts/check_assembly_interference.py`

## Bottom Cable Shelf To Bottom Tray Pads

Purpose: dedicated bottom cable shelf mounts to four raised pads on the bottom tray, creating vertical wire-routing space above the central battery/wire area.

Fixed part:

- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_bottom_tray.step`
- Source: `make_bottom_tray()` in `src/flow_cad/parts/chassis.py`

Moving part:

- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_bottom_cable_shelf.step`
- Source: `make_bottom_cable_shelf()` in `src/flow_cad/parts/shelves.py`
- Nominal bbox: `136.0 W x 188.0 D x 4.0 H mm`

Interface contract:

- Interface type: four raised stand-off pads with M4 screw retention.
- Install direction: Z down onto the pads.
- Width fit direction: X.
- Depth fit direction: Y.
- Pad centers derive from the bottom-tray bridge centerlines: X `+/- P.bottom_cable_pad_x`, Y `+/- bottom_tray_bridge_y(P)`.
- Pads are `P.bottom_cable_pad_size` square and `P.bottom_cable_pad_height` tall.
- Pad pilots use `P.m4_heatset_pilot_diameter`.
- Shelf mounting holes use round `P.m4_clearance_diameter` through-holes; do not use large square/slot cuts here because the shelf must retain M4 screw heads or washers.
- The shelf seats at `bottom_cable_shelf_z(P)`, on the 12 mm pads, and replaces the former lowest floating equipment shelf in the assembly preview.
- The bottom tray center spine includes front/rear USB access notches centered on X `0.0`; they open through Y `+/-` tray ends, stay below the over-battery bridge, and must not intersect the four shelf pads.

Validation:

- Generate: `flow cad build`
- Mounting check: `python src/flow_cad/scripts/check_mounting_features.py`
- Assembly check: `python src/flow_cad/scripts/check_assembly_interference.py`
- Pair check: place `make_bottom_cable_shelf()` at `bottom_cable_shelf_z(P)` and intersect it with `make_bottom_tray()`; expected overlap is `0.0 mm^3`.
- Feature check: confirm pad tops are at the shelf bottom plane, that the four round shelf holes align to the four pad pilot centers, and that the USB notches remain open through both tray ends.

## Equipment Shelves To Side Ledges

Purpose: equipment shelves sit on side-plate ledges and align to M4 mount holes.

Fixed parts:

- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_left_side_plate.step`
- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_right_side_plate.step`
- Source: `make_side_plate()` in `src/flow_cad/parts/chassis.py`

Moving parts:

- STEP: `b3/exports/step/lower_chassis/b3_equipment_shelf.step`
- STEP: `b3/exports/step/lower_chassis/b3_equipment_shelf_service_fit.step`
- STEP: `b3/exports/step/lower_chassis/b3_equipment_shelf_service_fit_four_way.step`
- Source: `make_equipment_shelf()` in `src/flow_cad/parts/shelves.py`
- Service-fit nominal bbox: `170.0 W x 188.0 D x 6.0 H mm`

Interface contract:

- Interface type: shelf resting on side ledges with M4 hole alignment.
- Install direction: Z.
- Width fit direction: X.
- Depth fit direction: Y.
- Shelf mount holes must stay aligned to `P.shelf_side_hole_x` and `P.shelf_side_hole_y`.
- Side ledge levels are defined by `P.shelf_side_ledge_z_levels`.
- Cable notches and side reliefs must not disconnect the shelf or leave unprintably thin bridges.
- `b3_equipment_shelf_service_fit_four_way.step` keeps four perimeter wire/airflow cutouts but leaves the central device-mounting area solid, without the three center wiring channels used by the standard shelf.

Validation:

- Generate: `flow cad build`
- Mounting check: `python scripts/check_mounting_features.py`
- Assembly check: `python scripts/check_assembly_interference.py`
- Future targeted check: shelf connectivity / minimum bridge validator.

## Axle Inserts To Side-Plate Pockets

Purpose: replaceable axle inserts carry the motor shaft profile and bolt into the side-plate reinforced boss pockets.

Fixed parts:

- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_left_side_plate.step`
- STEP: `b3/exports/step/lower_chassis/b3_lower_chassis_right_side_plate.step`
- Source: `make_side_plate()` in `src/flow_cad/parts/chassis.py`

Moving parts:

- STEP: `b3/exports/step/inserts/b3_axle_insert_tight.step`
- STEP: `b3/exports/step/inserts/b3_axle_insert_medium.step`
- STEP: `b3/exports/step/inserts/b3_axle_insert_loose.step`
- Source: `make_axle_insert()` in `src/flow_cad/parts/inserts.py`
- Medium nominal bbox: `36.0 W x 140.0 D x 116.0 H mm`

Interface contract:

- Interface type: replaceable insert in chamfered side-plate pocket with bolt retention.
- Install direction: X.
- Shaft axis: X.
- Bolt-pattern plane: Y/Z.
- The medium insert is the active assembly default.
- Right-side insert is rotated in the assembly so the same printable STEP can be used on both sides with the flange facing outward.
- Tab-washer relief must remain on the washer/nut-side face and clear the double-D shaft profile.

Validation:

- Generate: `flow cad build`
- Mounting check: `python scripts/check_mounting_features.py`
- Assembly check: `python scripts/check_assembly_interference.py`
- FreeCAD-enabled check when available: `python scripts/report_axle_insert_dimensions.py`

## Wheel Box Prototype To Axle Insert

Purpose: isolated rebuild/test-print wheel box for motor mounting and motor-wire coiling while preserving the current axle insert design as the mating constraint.

Fixed part:

- STEP: `b3/exports/step/wheel_box/b3_wheel_box_test_body.step`
- Source: `make_wheel_box_test_body()` in `src/flow_cad/parts/wheel_box/prototype.py`

Moving parts:

- STEP: `b3/exports/step/wheel_box/b3_wheel_box_tight_insert.step`
- Source: `make_wheel_box_tight_insert()` in `src/flow_cad/parts/wheel_box/prototype.py`
- Top lid STEP: `b3/exports/step/wheel_box/b3_wheel_box_test_top_lid.step`
- Top lid source: `make_wheel_box_test_top_lid()` in `src/flow_cad/parts/wheel_box/prototype.py`
- Bottom lid STEP: `b3/exports/step/wheel_box/b3_wheel_box_test_bottom_lid.step`
- Service lid source: `make_wheel_box_test_bottom_lid()` in `src/flow_cad/parts/wheel_box/prototype.py`

Interface contract:

- Interface type: M4-bolted axle insert into a side wheel-box wall, M4 cover screws, and continuous M5 battery-tray mounting rails.
- Insert install direction: X.
- Shaft axis: X.
- Insert bolt-pattern plane: Y/Z.
- Lid install direction: Z.
- Insert body opening uses `P.insert_pocket_size + P.wheel_box_insert_clearance` in Y/Z so the current thick insert body can pass the wheel-box mounting wall.
- The insert-side mounting wall is `P.wheel_box_mount_wall_thickness` thick and grows inward only. It must stay at least 10 mm thick to give the insert flange and four M4 bolts a deeper plastic shear path while preserving at least 5 inches of internal X wire-cavity depth.
- The wheel-box body is 152 mm deep in X. The M5 tray-hole zone covers 5 inches (`P.wheel_box_tray_mount_span_x`) under the future battery tray, leaving roughly 25 mm of wheel-side protrusion outside that tray zone.
- Wheel-box height is minimized around the chamfered insert opening rather than the old full insert flange. Current body/insert height is 99.6 mm, leaving 10 mm above and below the insert window.
- The matching wheel-box insert uses the tight shaft tolerance from `INSERT_VARIANTS["tight"]`, keeps the 30 mm thick insert core, and adds a 6 mm thick old-insert-style mounting flange.
- Insert and body use four M4 mounting holes on the side-lug material around the chamfered opening. The hole centers sit `P.wheel_box_insert_mount_window_margin_y` outward from the insert-window Y edge and `P.wheel_box_insert_mount_edge_margin_z` from the top/bottom outer edges, which keeps the holes clear of the full-height lid-screw pillars and the top mounting shelf so an M4 washer/nut access disk can sit on the inside face of the body. The tight insert uses the same center function so the matching flange holes move with the body.
- The battery tray, top cover, and wheel-box body share one four-hole vertical M5 pattern inside the 5 inch (`P.wheel_box_tray_mount_span_x`) battery-tray mount zone of the 152 mm box width. The bottom cover does not include these M5 battery-tray holes.
- The M5 tray-mount pattern is asymmetric in X: the wheel-side pair is kept at least `P.wheel_box_tray_mount_edge_margin_x` inboard from the future battery-wall line instead of directly on that wall line, and the corner-pillar pair is pulled inward by `P.wheel_box_tray_mount_pillar_pull_in_x` for cover-screw clearance.
- The body has two full-length top mounting shelves near the side walls. M5 holes are centered on these shelves in Y, leaving 20 mm to both shelf edges, and a `P.wheel_box_tray_mount_washer_access_diameter` washer/nut access disk must fit on the shelf and below the through-hole without intersecting side walls or lid towers. These shelves run the full 152 mm body length, tie directly into the side wall/top frame, stay outside the axle-insert clearance window, and carry the four vertical M5 through-holes for screw plus washer/nut hardware instead of heat-set inserts.
- Top and bottom covers use separate M4 corner fasteners. The body has full-height square corner towers for these M4 cover holes, which also stiffen the box.

Validation:

- Generate: `flow cad build`
- Unit checks: `python -m pytest tests/test_wheel_box.py`
- Connectivity check: `python src/flow_cad/scripts/check_wheel_box_connectivity.py`
- Through-mount access check: `python src/flow_cad/scripts/check_through_mount_access.py`
- Feature check: confirm the chamfered insert opening is clear, the four insert M4 holes align to `wheel_box_insert_mount_centers()`, both cover M4 hole patterns align to `wheel_box_lid_screw_centers()`, the top cover M5 holes align to `wheel_box_tray_mount_centers()`, and the bottom cover does not include the battery-tray M5 holes.
- Print-fit group: print `b3_wheel_box_test_body.step`, `b3_wheel_box_test_top_lid.step`, `b3_wheel_box_test_bottom_lid.step`, and `b3_wheel_box_tight_insert.step`.
