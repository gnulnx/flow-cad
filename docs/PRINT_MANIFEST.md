# Print Manifest

This file lists the current STEP handoff intent for Bambu Studio and related print planning. It is not generated source. Update it when the intended print set changes.

Source of truth for geometry is the `src/flow_cad/` package (entry point `src/flow_cad/main.py`). Generated STEP files live under `b3/exports/step/`.

## Active Lower Chassis Print Set

Core chassis parts:

- `b3/exports/step/lower_chassis/b3_lower_chassis_left_side_plate.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_right_side_plate.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_front_panel.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_bottom_tray.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_bottom_cable_shelf.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_top_lid.step`
- Lid carry handles, print two copies: `b3/exports/step/lower_chassis/b3_lower_chassis_lid_handle.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_simple_mounting_plate.step`

Rear-panel options:

- Default two-color rear panel:
  - `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel.step`
  - Optional split color bodies:
    - `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_body.step`
    - `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_bumpout.step`
- Detachable rear panel:
  - `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_detachable_body.step`
  - `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_detachable_bumpout.step`
  - TPU fit-test bumpout: `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_detachable_bumpout_TPU.step`
- Alternate vented panel:
  - `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_vented.step`

Axle inserts:

- `b3/exports/step/inserts/b3_axle_insert_medium.step`
- `b3/exports/step/inserts/b3_axle_insert_tight.step`
- `b3/exports/step/inserts/b3_axle_insert_loose.step`

Equipment shelves:

- `b3/exports/step/lower_chassis/b3_equipment_shelf.step`
- `b3/exports/step/lower_chassis/b3_equipment_shelf_side_cable.step`
- `b3/exports/step/lower_chassis/b3_equipment_shelf_side_cable_shallow.step`
- `b3/exports/step/lower_chassis/b3_equipment_shelf_four_way_cable_shallow.step`
- `b3/exports/step/lower_chassis/b3_equipment_shelf_service_fit.step`
- `b3/exports/step/lower_chassis/b3_equipment_shelf_service_fit_four_way.step`
- Optional legacy support: `b3/exports/step/lower_chassis/b3_shelf_spacer_block_55mm.step`

Fit test coupons:

- Push-button threaded body fit test, 20 mm x 20 mm x 10 mm with 12.1 mm through-hole: `b3/exports/step/test_coupons/b3_push_button_hole_test_coupon_12p1mm.step`
- Push-button recessed top-plate fit test, 40 mm x 40 mm x 10 mm with centered 20 mm x 20 mm area thinned to 5 mm and a 12.1 mm through-hole: `b3/exports/step/test_coupons/b3_push_button_recess_test_coupon_12p1mm.step`

Wheel-box rebuild test prints:

- `b3/exports/step/wheel_box/b3_wheel_box_test_body.step`
- `b3/exports/step/wheel_box/b3_wheel_box_test_top_lid.step`
- `b3/exports/step/wheel_box/b3_wheel_box_test_bottom_lid.step`
- Matching tight insert for this prototype: `b3/exports/step/wheel_box/b3_wheel_box_tight_insert.step`

## Inspection Or Reference Only

Do not send these as ordinary printable Bambu parts unless explicitly doing visual fit or reference work:

- `b3/exports/step/lower_chassis/b3_lower_chassis_assembly.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_detachable.step`
- `b3/exports/step/reference/b3_reference_wheel_pair.step`
- `b3/exports/step/reference/b3_reference_axle_pair.step`
- `b3/exports/step/reference/b3_reference_wheel_axle_pair.step`

Assembly and detachable-preview STEP files are for inspection and CAD Explorer review. Use the separate detachable body and bumpout STEP files for Bambu slicing. Reference wheel/axle files represent purchased or non-print reference geometry.

## Interface-Sensitive Print Groups

When preparing one of these groups for print, inspect `PART_INTERFACES.md` first and validate the listed mating pair directly.

Rear detachable panel group:

- `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_detachable_body.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_detachable_bumpout.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_detachable_bumpout_TPU.step` for TPU fit testing only

## Material Fit Notes

- TPU flexible slide features can bind even when PETG fits cleanly. Start with an explicit material variant rather than changing the proven PETG geometry.
- Current TPU rear detachable bumpout test keeps the fixed receiver unchanged, reduces the bumpout T-head X capture width from 10.0 mm to 8.0 mm, and reduces the T-head Y capture depth from 2.30 mm to 1.75 mm.

Front/rear panel dovetail group:

- `b3/exports/step/lower_chassis/b3_lower_chassis_left_side_plate.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_right_side_plate.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_front_panel.step`
- one rear panel option from the rear-panel list above

Bottom tray group:

- `b3/exports/step/lower_chassis/b3_lower_chassis_left_side_plate.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_right_side_plate.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_bottom_tray.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_bottom_cable_shelf.step`

Top lid handle group:

- `b3/exports/step/lower_chassis/b3_lower_chassis_top_lid.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_lid_handle.step`, printed twice

Shelf and side-ledge group:

- `b3/exports/step/lower_chassis/b3_lower_chassis_left_side_plate.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_right_side_plate.step`
- selected shelf STEP file

Axle insert group:

- `b3/exports/step/lower_chassis/b3_lower_chassis_left_side_plate.step`
- `b3/exports/step/lower_chassis/b3_lower_chassis_right_side_plate.step`
- selected axle insert STEP file

Wheel-box prototype group:

- `b3/exports/step/wheel_box/b3_wheel_box_test_body.step`
- `b3/exports/step/wheel_box/b3_wheel_box_test_top_lid.step`
- `b3/exports/step/wheel_box/b3_wheel_box_test_bottom_lid.step`
- `b3/exports/step/wheel_box/b3_wheel_box_tight_insert.step`

## Standard Handoff Checks

Before calling a print bundle ready:

1. Run `flow cad build`.
2. Run `python -m pytest`.
3. Run the validators listed in `AGENTS.md` and `PART_INTERFACES.md` for the changed parts.
   103|  4. Run `scripts/check_mounting_features.py`.
   104|  5. Run `scripts/check_assembly_interference.py`.
   105|  6. Run `src/flow_cad/scripts/validate_print_manifest.py --manifest docs/PRINT_MANIFEST.md` to verify print handoff intent matches registry.
   106|  7. Copy the printed bundle path to the laptop, for example:
   107|    ```bash
   108|    scp handoff/exports.tar.gz jfurr@laptop:/Users/jfurr/
   109|    ```
   110|  8. Record any slicer-specific assumptions in this file or a dated bundle note.

On the laptop, unpack the handoff archive from `/Users/jfurr`:

```bash
tar -xzf exports.tar.gz
```

Then load the intended STEP files from the unpacked `b3/exports/step/` directory into Bambu Studio.
