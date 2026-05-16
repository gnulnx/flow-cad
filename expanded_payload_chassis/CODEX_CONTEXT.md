# Erb Expanded Payload Chassis Context

Project directory: `/Users/jfurr/3DPrintBalanceBot/expanded_payload_chassis`

This is a separate Stage 1 lower chassis variant. The current baseline Stage 1 design remains in `/Users/jfurr/3DPrintBalanceBot`; this variant explores a wider and taller lower box for real payload packaging.

## Variant Goal

Make the lower chassis large enough for three stacked equipment zones:

- Bottom platform: two HRB 6S 6000mAh LiPo batteries
- Lower flat shelf: FLIPSKY Dual 75100 controller
- Upper flat shelf: BOSGAME M4 Oculink mini PC

Do not design the full robot shell, torso, arms, head, tray, or compute stack yet.

## Payload Envelopes

- BOSGAME M4 body: use 129 x 129 x 48 mm as the working body size. Retail package dimensions around 6.5 x 6.5 x 4.1 inches are shipping-box dimensions, not the chassis footprint.
- FLIPSKY Dual 75100: use 107 x 103 x 18.5 mm from Flipsky's listed controller size.
- HRB 6S 6000mAh packs: use 155 x 48 x 54 mm each, with 0-3 mm manufacturing tolerance.

## Current Variant Dimensions

- Center chassis outside width: 240 mm
- Chassis depth: 240 mm
- Side plate height: 240 mm
- Assembly height with top cap: 246 mm
- Side plate local reinforced thickness: 30 mm
- Fit-safe internal shelf envelope: 180 mm wide x 200 mm deep
- Generic flat equipment shelf: 180 x 200 x 6 mm
- Lower shelf bottom Z: 92 mm
- Upper shelf bottom Z: 146 mm
- Axle center height from bottom: 50 mm

## Packaging Rationale

The original 200 mm-wide chassis only had a 140 mm fit-safe internal shelf width. That was too tight for the BOSGAME M4 if we budget for the body, cable bend radius, and service handling. This variant increases center chassis width to 240 mm, yielding a 180 mm internal shelf width while still keeping a plausible overall wheel-to-wheel width with two 100 mm-wide tires.

The front-back depth remains 240 mm. An 18 inch / 457 mm chassis depth would make the side plates too long for the roughly 250 mm Bambu build volume unless the side plates were split into multiple bolted sections. This variant avoids that extra split for now.

Vertical zones:

- Battery bay: bottom tray to lower shelf, sized around two 155 x 48 x 54 mm packs with strap/cable clearance.
- Controller bay: lower shelf to upper shelf, enough for the thin Dual 75100 controller plus cable and airflow allowance.
- Compute bay: upper shelf to top lid, largest electronics bay, intended for the BOSGAME M4 body plus cable/airflow clearance.

## CAD Workflow

Generate STEP files from this subproject directory:

```bash
/Users/jfurr/text-to-cad/.venv/bin/python cad/erb_lower_chassis.py
```

Run the interference checker:

```bash
/Users/jfurr/text-to-cad/.venv/bin/python scripts/check_assembly_interference.py
```

Mirror this variant to text-to-cad:

```bash
/Users/jfurr/text-to-cad/.venv/bin/python scripts/sync_text_to_cad.py
```

Viewer URL:

```text
http://127.0.0.1:4178/?dir=models/erb_balance_bot/stage1_lower_chassis_expanded_payload&file=erb_lower_chassis_assembly.step
```

## Active STEP Set

- `erb_lower_chassis_left_side_plate.step`
- `erb_lower_chassis_right_side_plate.step`
- `erb_lower_chassis_front_panel.step`
- `erb_lower_chassis_rear_panel.step`
- `erb_lower_chassis_bottom_tray.step`
- `erb_lower_chassis_top_lid.step`
- `erb_axle_insert_tight.step`
- `erb_axle_insert_medium.step`
- `erb_axle_insert_loose.step`
- `erb_equipment_shelf.step` (print two copies)
- `erb_lower_chassis_assembly.step`

## Open Questions

- Confirm the exact BOSGAME M4 body dimensions and preferred cable-exit orientation once it is in hand.
- Confirm the FLIPSKY Dual 75100 board/case variant and real connector/cable bend envelope.
- Confirm battery wiring/strap direction and whether the batteries should sit side-by-side across width or be individually retained in trays.
- Decide whether an 18 inch deep version is worth the extra complexity of split side plates.
