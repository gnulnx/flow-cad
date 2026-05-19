# Print Manifest

This file lists the current STEP handoff intent for Bambu Studio and related print planning. It is not generated source. Update it when the intended print set changes.

Source of truth for geometry remains `cad/erb_lower_chassis.py`. Generated STEP files live under `exports/step/`.

## Active Lower Chassis Print Set

Core chassis parts:

- `exports/step/erb_lower_chassis_left_side_plate.step`
- `exports/step/erb_lower_chassis_right_side_plate.step`
- `exports/step/erb_lower_chassis_front_panel.step`
- `exports/step/erb_lower_chassis_bottom_tray.step`
- `exports/step/erb_lower_chassis_top_lid.step`

Rear-panel options:

- Default two-color rear panel:
  - `exports/step/erb_lower_chassis_rear_panel.step`
  - Optional split color bodies:
    - `exports/step/erb_lower_chassis_rear_panel_body.step`
    - `exports/step/erb_lower_chassis_rear_panel_bumpout.step`
- Detachable rear panel:
  - `exports/step/erb_lower_chassis_rear_panel_detachable_body.step`
  - `exports/step/erb_lower_chassis_rear_panel_detachable_bumpout.step`
  - Inspection preview: `exports/step/erb_lower_chassis_rear_panel_detachable.step`
- Alternate vented panel:
  - `exports/step/erb_lower_chassis_rear_panel_vented.step`

Axle inserts:

- `exports/step/erb_axle_insert_medium.step`
- `exports/step/erb_axle_insert_tight.step`
- `exports/step/erb_axle_insert_loose.step`

Equipment shelves:

- `exports/step/erb_equipment_shelf.step`
- `exports/step/erb_equipment_shelf_side_cable.step`
- `exports/step/erb_equipment_shelf_side_cable_shallow.step`
- `exports/step/erb_equipment_shelf_four_way_cable_shallow.step`
- `exports/step/erb_equipment_shelf_service_fit.step`
- `exports/step/erb_equipment_shelf_service_fit_four_way.step`
- Optional legacy support: `exports/step/erb_shelf_spacer_block_55mm.step`

Upper module / adapter pieces:

- `exports/step/erb_upper_wide_center_adapter_deck.step`
- `exports/step/erb_upper_wide_center_compute_bay.step`
- `exports/step/erb_upper_wide_left_overwheel_pod.step`
- `exports/step/erb_upper_wide_right_overwheel_pod.step`
- `exports/step/erb_upper_wide_center_crossmember.step`
- `exports/step/erb_upper_wide_side_crossmember.step`
- `exports/step/erb_upper_perception_pod.step`

## Inspection Or Reference Only

Do not send these as ordinary printable Bambu parts unless explicitly doing visual fit or reference work:

- `exports/step/erb_lower_chassis_assembly.step`
- `exports/step/erb_reference_wheel_pair.step`
- `exports/step/erb_reference_axle_pair.step`
- `exports/step/erb_reference_wheel_axle_pair.step`
- `exports/step/erb_top_dome_plain.step`
- `exports/step/erb_top_dome_sensor_mockup.step`
- `exports/step/erb_top_dome_prototypes.step`

Assembly STEP files are for inspection and CAD Explorer review. Reference wheel/axle files represent purchased or non-print reference geometry.

## Interface-Sensitive Print Groups

When preparing one of these groups for print, inspect `PART_INTERFACES.md` first and validate the listed mating pair directly.

Rear detachable panel group:

- `exports/step/erb_lower_chassis_rear_panel_detachable_body.step`
- `exports/step/erb_lower_chassis_rear_panel_detachable_bumpout.step`

Front/rear panel dovetail group:

- `exports/step/erb_lower_chassis_left_side_plate.step`
- `exports/step/erb_lower_chassis_right_side_plate.step`
- `exports/step/erb_lower_chassis_front_panel.step`
- one rear panel option from the rear-panel list above

Bottom tray group:

- `exports/step/erb_lower_chassis_left_side_plate.step`
- `exports/step/erb_lower_chassis_right_side_plate.step`
- `exports/step/erb_lower_chassis_bottom_tray.step`

Shelf and side-ledge group:

- `exports/step/erb_lower_chassis_left_side_plate.step`
- `exports/step/erb_lower_chassis_right_side_plate.step`
- selected shelf STEP file

Axle insert group:

- `exports/step/erb_lower_chassis_left_side_plate.step`
- `exports/step/erb_lower_chassis_right_side_plate.step`
- selected axle insert STEP file

Upper adapter group:

- `exports/step/erb_upper_wide_center_adapter_deck.step`
- selected upper module pieces
- side plates for bolt-pattern verification

## Standard Handoff Checks

Before calling a print bundle ready:

1. Run `python cad/erb_lower_chassis.py`.
2. Run `python -m pytest`.
3. Run the validators listed in `AGENTS.md` and `PART_INTERFACES.md` for the changed parts.
4. Confirm the intended STEP files exist in `exports/step/`.
5. Sync viewer assets with `python scripts/sync_text_to_cad.py` when using text-to-cad/CAD Explorer for review.
6. Create a laptop/Bambu bundle with `python scripts/create_exports_bundle.py`.
7. Copy the printed bundle path to the laptop, for example `scp handoff/erb-exports-YYYYMMDD-HHMMSS.tar.gz jfurr@laptop:/Users/jfurr/`.
8. Record any slicer-specific assumptions in this file or a dated bundle note.

On the laptop, unpack the handoff archive from `/Users/jfurr`:

```bash
tar -xzf erb-exports-YYYYMMDD-HHMMSS.tar.gz
```

Then load the intended STEP files from the unpacked `exports/step/` directory into Bambu Studio.
