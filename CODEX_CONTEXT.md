# Erb Balance Bot Project Context

Project directory: `/Users/jfurr/3DPrintBalanceBot`

This is the active Stage 1 lower chassis design. The older 200 mm-wide baseline has been archived in `/Users/jfurr/3DPrintBalanceBot/legacy_stage1_lower_chassis`.

## Current Goal

Make the lower chassis large enough for three stacked equipment zones:

- Bottom platform: two HRB 6S 6000mAh LiPo batteries
- Lower flat shelf: FLIPSKY Dual 75100 controller
- Upper flat shelf: BOSGAME M4 Oculink mini PC

Do not design the full robot shell, torso, arms, head, tray, or compute stack yet.

## Payload Envelopes

- BOSGAME M4 body: use 129 x 129 x 48 mm as the working body size. Retail package dimensions around 6.5 x 6.5 x 4.1 inches are shipping-box dimensions, not the chassis footprint.
- FLIPSKY Dual 75100: use 107 x 103 x 18.5 mm from Flipsky's listed controller size.
- HRB 6S 6000mAh packs: current measured working footprint is 170 x 50 mm each; earlier listing was 155 x 48 x 54 mm. Keep 54 mm as working height until remeasured.

## Current Dimensions

- Center chassis outside width: 240 mm
- Chassis depth: 240 mm
- Side plate height: 240 mm
- Front/rear panel height: 240 mm
- Assembly height with top cap: 246 mm
- Side plate local reinforced thickness: 30 mm
- Fit-safe internal shelf envelope: 180 mm wide x 200 mm deep
- Generic flat equipment shelf: 180 x 200 x 6 mm
- Bottom battery tray: flush underside with 150 x 204 x 4 mm full-depth central support floor, widened side rails, and inboard rear latch landing pad
- Active assembly shelf: `erb_equipment_shelf_service_fit.step`, a looser shelf with long/deep side reliefs for wheel-side hardware and rounded-square M4 adjustment slots. Older solid, deep side-cable, shallow left/right side-cable, and four-way shallow shelf variants remain exported.
- Front/rear panel retention: one top M5 heat-set pilot per side in inboard keeper bosses, X +/-81 mm, global Y +/-99 mm when assembled, Z 220 mm. These align with matching side-panel M5 clearance/counterbore holes and keep the stopped dovetail panels from sliding upward.
- Battery cassette: 124 x 176 mm body, 124 x 188 mm including rear latch tab, slide-out low-lip sled for two measured 170 x 50 mm 6S packs
- Lower shelf bottom Z: 74 mm
- Upper shelf bottom Z: 122 mm
- Third shelf bottom Z: 183 mm, using four 55 mm printable spacer blocks over the upper shelf holes
- Clear height from bottom tray top to lower shelf underside: 66 mm
- Clear height between lower and upper shelves: 42 mm
- Clear height from upper shelf top to side-plate top plane: 112 mm
- Axle center height from bottom: 58 mm

## Packaging Rationale

The original 200 mm-wide chassis only had a 140 mm fit-safe internal shelf width. That was too tight for the BOSGAME M4 if we budget for the body, cable bend radius, and service handling. This active design increases center chassis width to 240 mm, yielding a 180 mm internal shelf width while still keeping a plausible overall wheel-to-wheel width with two 100 mm-wide tires.

The front-back depth remains 240 mm. An 18 inch / 457 mm chassis depth would make the side plates too long for the roughly 250 mm Bambu build volume unless the side plates were split into multiple bolted sections. This design avoids that extra split for now.

Vertical zones:

- Battery bay: bottom tray to lower shelf, sized around two 155 x 48 x 54 mm packs with strap/cable clearance.
- Controller bay: lower shelf to upper shelf, enough for the thin Dual 75100 controller plus cable and airflow allowance.
- Compute bay: upper shelf to top lid, largest electronics bay, intended for the BOSGAME M4 body, a mounting plate, rubber isolation mounts, and cable/airflow clearance.

## CAD Workflow

Generate STEP files from this project directory:

```bash
/Users/jfurr/text-to-cad/.venv/bin/python cad/erb_lower_chassis.py
```

Run the interference checker:

```bash
/Users/jfurr/text-to-cad/.venv/bin/python scripts/check_assembly_interference.py
```

Run the mounting feature checker after battery tray or shelf-support changes:

```bash
/Users/jfurr/text-to-cad/.venv/bin/python scripts/check_mounting_features.py
```

Run the upper adapter-deck stack geometry checker after changing the wide upper module deck/wing stack:

```bash
/Users/jfurr/text-to-cad/.venv/bin/python scripts/check_upper_hook_geometry.py
```

Export the current full-bot FreeCAD assembly document:

```bash
scripts/export_freecad.sh
```

Generate the native editable FreeCAD bottom tray and battery cassette files:

```bash
freecad/generate_native_parts.sh
```

FreeCAD outputs:

- `exports/freecad/erb_full_current_bot_assembly.FCStd` (current assembled lower chassis, current upper chassis blockout, and wheel/axle reference parts kept as separate FreeCAD objects)
- `exports/freecad/erb_full_current_bot_partdesign_bodies.FCStd` (same current bot layout, but printable/current upper parts are root-level FreeCAD PartDesign `Body` objects with hidden imported base solids so new Sketch/Pad/Pocket/Hole features can be added in a tutorial-style workflow)
- `exports/freecad/native/erb_bottom_tray_native.FCStd` (FreeCAD-native editable boolean construction for the bottom tray; not a STEP import)
- `exports/freecad/native/erb_battery_cassette_native.FCStd` (FreeCAD-native editable boolean construction for the battery cassette; not a STEP import)
- `exports/freecad/erb_lower_chassis_assembly.FCStd`
- `exports/freecad/erb_lower_chassis_print_layout.FCStd`

Mirror this project to text-to-cad:

```bash
/Users/jfurr/text-to-cad/.venv/bin/python scripts/sync_text_to_cad.py
```

Generate the ESP32-WROOM holder accessory:

```bash
/Users/jfurr/text-to-cad/.venv/bin/python cad/erb_esp32_wroom_holder.py
```

Mirror the ESP32-WROOM holder to text-to-cad:

```bash
/Users/jfurr/text-to-cad/.venv/bin/python scripts/sync_esp32_to_text_to_cad.py
```

Viewer URL:

```text
http://127.0.0.1:4178/?dir=models/erb_balance_bot/stage1_lower_chassis&file=erb_lower_chassis_assembly.step
```

## Active STEP Set

- `erb_lower_chassis_left_side_plate.step`
- `erb_lower_chassis_right_side_plate.step`
- `erb_lower_chassis_front_panel.step`
- `erb_lower_chassis_rear_panel.step` (default no-vent rear panel with two-solid colorable tapered hollow cable bump-out)
- `erb_lower_chassis_rear_panel_body.step` (rear panel body only, for multi-color import workflows)
- `erb_lower_chassis_rear_panel_bumpout.step` (separate bump-out shell only, 0.2 mm overlap into body)
- `erb_lower_chassis_rear_panel_detachable.step` (alternate rear panel preview with looser male side dovetails and vertical slide-on removable bump-out)
- `erb_lower_chassis_rear_panel_detachable_body.step` (alternate compatible rear panel body with looser male side dovetails, attached vertical receiver channels, molded support webbing, and M4 retainer boss)
- `erb_lower_chassis_rear_panel_detachable_bumpout.step` (alternate removable bump-out shell with hidden vertical slide tongues and M4 retainer slot)
- `erb_lower_chassis_rear_panel_vented.step` (alternate previous vented rear panel)
- `erb_lower_chassis_bottom_tray.step`
- `erb_battery_cassette.step`
- `erb_lower_chassis_top_lid.step`
- `erb_axle_insert_tight.step`
- `erb_axle_insert_medium.step`
- `erb_axle_insert_loose.step`
- `erb_equipment_shelf.step` (print two copies)
- `erb_equipment_shelf_side_cable.step` (alternate shelf with side-edge cable notches)
- `erb_equipment_shelf_side_cable_shallow.step` (alternate shelf with shallower side-edge cable notches)
- `erb_equipment_shelf_four_way_cable_shallow.step` (previous default shelf with shallow centered cable notches on all four edges)
- `erb_equipment_shelf_service_fit.step` (active assembly shelf, looser 170 x 188 mm with long/deep side reliefs for wheel-side hardware and 14 mm rounded-square M4 adjustment slots)
- `erb_shelf_spacer_block_55mm.step` (optional legacy spacer block; exported but not placed in the active assembly)
- `erb_upper_wide_center_compute_bay.step` (Stage 2 blockout center bay)
- `erb_upper_wide_left_overwheel_pod.step` (Stage 2 blockout left pod)
- `erb_upper_wide_right_overwheel_pod.step` (Stage 2 blockout right pod)
- `erb_upper_wide_center_crossmember.step` (Stage 2 optional printed skeleton center rail; exported but not used in the active assembly)
- `erb_upper_wide_side_crossmember.step` (Stage 2 optional printed skeleton side rail; exported but not used in the active assembly)
- `erb_upper_perception_pod.step` (Stage 2 blockout sensor/perception pod)
- `erb_reference_wheel_pair.step` (non-print wheel envelope reference)
- `erb_reference_axle_pair.step` (non-print double-D shaft reference)
- `erb_reference_wheel_axle_pair.step` (non-print combined wheel/shaft reference)
- `erb_top_dome_plain.step` (visual prototype: hollow half-dome with square mounting flange)
- `erb_top_dome_sensor_mockup.step` (visual prototype: hollow dome with front camera pad, top sensor opening, and side service ports)
- `erb_top_dome_prototypes.step` (side-by-side visual comparison only; not a printable single part)
- `erb_lower_chassis_assembly.step`

## Accessory STEP Set

ESP32-WROOM holder outputs are in `exports/step/esp32_wroom_holder`:

- `erb_esp32_wroom_holder_base.step`
- `erb_esp32_wroom_holder_lid.step`
- `erb_esp32_wroom_holder_assembly.step`

Dovetail tolerance test outputs are in `exports/step/dovetail_tolerance_test`:

- `erb_dovetail_tolerance_female_coupon.step`
- `erb_dovetail_tolerance_male_coupon.step`
- `erb_dovetail_tolerance_test_plate.step`

Kawai-style joint test outputs are in `exports/step/kawai_test_joint`:

- `erb_kawai_test_joint_female_coupon.step`
- `erb_kawai_test_joint_male_coupon.step`
- `erb_kawai_test_joint_plate.step`

## Current Design Notes

- 2026-05-12 full FreeCAD export: `scripts/export_freecad.sh` now writes `exports/freecad/erb_full_current_bot_assembly.FCStd` without overwriting the older lower-only FreeCAD files. The full file imports the current STEP solids as separate FreeCAD `Part::Feature` objects and groups them under `Lower chassis`, `Upper chassis`, and `Reference wheels and axles`, so the whole current robot layout can be inspected and edited in one FreeCAD document.
- 2026-05-14 native FreeCAD part construction: added `freecad/erb_bottom_tray_native.py`, `freecad/erb_battery_cassette_native.py`, and `freecad/generate_native_parts.sh`. These generate `exports/freecad/native/erb_bottom_tray_native.FCStd` and `exports/freecad/native/erb_battery_cassette_native.FCStd` from editable FreeCAD Part boxes/cylinders and boolean cuts instead of importing STEP solids. They are intended for GUI editing/learning and currently omit the global cosmetic chamfers from the build123d STEP versions to keep the feature tree simple and robust.
- 2026-05-15 integrated battery tray redesign: the active `erb_lower_chassis_bottom_tray.step` now replaces the separate battery cassette in the assembly. It has a 180 x 204 x 10 mm flush floor, two 164 x 51 mm battery lanes for the updated 155 x 50 x 50 mm pack envelope, 2 mm outer retaining ribs set 3 mm inside the measured 144 mm bottleneck, and a 32 mm outside-width center electronics spine with 28 mm usable lower pocket width for the ~26 mm ESP32. The low outer retaining ribs are shortened to 148 mm long, ending at Y +/-74, to clear the bottom-tray M5 screw holes at Y +/-82 by about 4.95 mm from hole edge. The center spine now runs the full 204 mm tray length, and the top electronics deck is 30 mm wide x 204 mm long with its top lowered to Z=50 mm for extra Dupont-wire clearance above the ESP32/IMU. Front/rear over-battery bridges are continuous full tray-width 180 mm lateral spans, 37 mm deep to match the full side screw-hole pillar depth. The original screw-hole pillars remain the bridge supports and continue up to the bridge top; no separate inner bridge posts are used. Local center risers lift the center column from the Z=50 electronics deck up to the Z=63 bridge underside only under the front/rear bridges; these center bridge supports are now 13 mm tall. Bridges are 8 mm thick, underside at Z=63 and top at Z=71, leaving 3 mm battery height clearance, 3 mm lower-shelf clearance above the bridge top, and 24 mm clearance from the lowered electronics deck to the lower shelf. The original side M5 tower hole centers remain X +/-81, Y +/-82. The bottom tray no longer applies a cosmetic global chamfer because the continuous full-length deck made the CAD kernel bog down during export; this keeps dimensions literal while iterating. `erb_battery_cassette.step` is no longer exported, placed in the active assembly, or mirrored to text-to-cad. `scripts/check_mounting_features.py` now validates the integrated tray dimensions instead of old cassette access.
- 2026-05-16 bottom tray mount reinforcement: added a second upper M5 mount level for the integrated bottom tray. Each side chassis now has four bottom-tray M5 clearance/counterbore holes, and the bottom tray has matching heat-set pilot cuts: front/rear at Y +/-82 mm, lower Z=16 mm and upper Z=58 mm. This gives 8 total bottom-tray-to-side-chassis screws. The upper Z=58 holes sit in the existing solid front/rear tray towers below the bridge top, leaving about 9.95 mm vertical edge margin to the 71 mm tower top after pilot radius; bottom tray mounts and axle insert mounts remain separate features.
- 2026-05-16 stopped front/rear panel dovetails: the left/right side chassis now have stopped female dovetail slots at the front/rear corner rails, and the front/rear panels have matching male dovetail rails on their side edges. Panels slide down from the top; the side slots stop 8 mm above the bottom to locate the panels vertically. Side chassis depth increased from 240 to 256 mm and front/rear panel side-rail depth increased from 18 to 26 mm while the bottom tray remains 204 mm deep, so the deeper rails meet the bottom-tray ends without overlap. Male rails are 10 mm deep with 9 mm neck / 15 mm head width. Female slots add 0.25 mm clearance per side, giving 10.5 mm slot depth, 9.5 mm neck width, and 15.5 mm head width. The female slot head now has about 5.25 mm material margin to the chassis front/rear edge instead of 1.25 mm. Female slot roots include 1.0 mm vertical relief radii to reduce sharp internal stress/print corners. Current checks confirm no assembly solid overlaps.
- 2026-05-16 front/rear retention-hole cleanup: the front/back panel interface now keeps only one M5 retention screw at the top of each side connection, Z=220 mm. That gives two top screws on the front panel and two top screws on the rear panel to stop the dovetailed panels from sliding upward. The top retention screws were moved off the dovetail centerline into small inboard panel bosses at Y +/-99 mm, while the dovetail slot centers are at Y +/-115 mm. The former lower/mid front/back interface holes at Z=35, 105, and 175 were removed from both the side chassis plates and the front/rear panel dovetail/side-rail connector zones. Bottom tray mounting holes and axle insert retention holes are separate features and remain unchanged.
- 2026-05-16 dovetail tolerance test coupons: added `cad/erb_dovetail_tolerance_test.py`, which exports a small upright male/female coupon pair and a combined single-plate STEP under `exports/step/dovetail_tolerance_test`. The coupons reuse the active chassis dovetail parameters directly from `cad/erb_lower_chassis.py`: 10 mm male rail depth, 9/15 mm male neck/head width, 0.25 mm female clearance per side, 1.0 mm female root relief radius, and 8 mm stopped base. Current single-plate bounding box is 68 x 32 x 60 mm. Text-to-cad viewer sidecars were generated under `/Users/jfurr/text-to-cad/models/erb_balance_bot/dovetail_tolerance_test`.
- 2026-05-17 Kawai-style joint test coupon: added `cad/erb_kawai_test_joint.py`, which exports a small same-plate two-piece Kawai/Tsugite-inspired stepped pinwheel interlock under `exports/step/kawai_test_joint`. The female and male coupons are each 20 x 34 x 26 mm; the combined plate is 64 x 34 x 26 mm. Current fit clearance is 0.25 mm per side in Y/Z with 0.4 mm pocket bottoming clearance in X. Text-to-cad viewer sidecars were generated under `/Users/jfurr/text-to-cad/models/erb_balance_bot/kawai_test_joint`.
- 2026-05-16 shelf support cleanup after integrated tray/dovetails: the active assembly still shows three four-way shallow equipment shelves at Z=74, Z=122, and Z=183, but the side-plate shelf ledges now exist only at Z=122 and Z=183. The former Z=74 side ledges were removed because they overlap the integrated bottom tray; the lower shelf remains a packaging reference until bottom-tray spacer posts are designed. The third shelf is now carried by side-plate ledges at Z=183 rather than by placed spacer blocks. `erb_shelf_spacer_block_55mm.step` remains exported as an optional legacy part but is not placed in the assembly. Shelf width remains 180 mm because a 190 mm shelf caused side-plate overlaps; instead, shelf mounting holes moved inward from X +/-80 to X +/-75 and side ledge depth increased from 38 to 46 mm to improve edge margin and support. Shelf ledge triangular gussets are split around each mounting bolt centerline at Y +/-18 mm from the bolt, leaving about 31 mm of clear screw-driver/bolt access through the center of each shelf bracket. Current mounting-feature and assembly-interference checks pass with zero solid overlaps.
- 2026-05-12 PartDesign bridge export, revised 2026-05-13 after FreeCAD GUI testing: `scripts/export_freecad.sh` now also writes `exports/freecad/erb_full_current_bot_partdesign_bodies.FCStd`. It keeps the same current assembled bot layout, but the 20 printable/current upper design occurrences are exported as root-level PartDesign `Body` objects labeled `LOWER ...` and `UPPER ...`, each with a hidden imported `BaseFeature` seed solid. The seed solid is baked into its assembled world position and each Body placement is identity, so FreeCAD displays the same assembled layout while Sketch/Pad/Pocket/Hole edits happen directly on the visible Body. The wheel/axle references remain ordinary non-print reference solids in a small reference group. Earlier attempts either grouped the BaseFeature seeds in a hidden folder or placed the Body rather than the seed shape; both confused the GUI tree/visibility and were replaced.
- The front panel uses vertical ventilation slots in the central panel field.
- Front and rear panels extend to the 240 mm side-plate top plane so they meet the top cap without a visible top gap.
- 2026-05-11 wide-over-wheel adapter-deck pass: replaced the failed J-hook concept with a stacked upper adapter architecture. `erb_upper_wide_center_adapter_deck.step` is a 240 x 240 x 8 mm second-layer plate at Z 240 mm that sits directly on the lower chassis top plane. `erb_upper_wide_left_overwheel_pod.step` and `erb_upper_wide_right_overwheel_pod.step` are now flat 128 x 240 x 8 mm over-wheel wing decks at Z 248 mm; each keeps the visual outer edge at the 460 mm upper-module envelope and overlaps inward to the existing X +/-102 mm lower side-rail bolt line. The 240 x 226 x 96 mm center compute bay now starts at Z 256 mm, so the clamp stack is upper compute bay -> over-wheel wing where present -> center adapter deck -> lower side-frame heat-set inserts. No active J-hook/drop-leg/saddle geometry remains. `scripts/check_upper_hook_geometry.py` now checks the adapter-deck stack despite the historical filename: center deck at the lower 240 mm top plane, side wing layer at Z 248, compute bay start at Z 256, 240 mm full depth, 8 mm flat plates, and screw-hole edge margins. `erb_upper_wide_center_crossmember.step` and `erb_upper_wide_side_crossmember.step` remain exported as optional rail experiments, but they are not placed in the active assembly. A 172 x 76 x 42 mm perception pod sits above at Z 360 mm with simple camera/LiDAR placeholder openings.
- 2026-05-11 wheel/axle reference geometry: `erb_lower_chassis_assembly.step` now includes non-print wheel and axle references for CAD clearance checks. The reference tires are 260 mm diameter x 100 mm wide at X +/-190 mm, giving a 480 mm overall wheel envelope and 20 mm nominal tire-to-side-plate clearance per side. The reference shafts are 16 mm / 12 mm-flat double-D profiles, 75 mm visible length from the side plate toward the wheel. Printable part STEP files remain clean; `scripts/check_assembly_interference.py` still checks only printable chassis occurrences by default so the intentional axle/reference geometry does not create false failures.
- 2026-05-06 battery service change: redesigned the bottom tray around `erb_battery_cassette.step`. A 10 mm dropped pocket was tested and rejected because its front/back edges would hang below the chassis and could catch on thresholds or patio edges. The current bottom tray has a flush underside with a full-depth 150 x 204 x 4 mm central support floor that reaches the front/rear panel inner rail faces. The bottom-tray side rails were widened from 10 mm to 18 mm so M5 pilots have real edge margin. The M5 side-rail pilots are now 28 mm long through-cuts so they visibly open on the widened rail faces. The cassette is a 124 x 176 mm removable sled body, 124 x 188 mm including the rear latch tab, for two measured 170 x 50 mm 6S packs in series. It rides just above the support floor on side guide rails and uses side lips, split 42 mm front/rear lane lips, 6 mm wide Velcro strap slots, a center divider, and one flat rear latch tab. The front/rear lips leave a 16 mm center channel so the latch screw and front finger notch remain accessible. The bottom tray has an inboard rear latch landing pad and no tall front/rear battery walls.
- 2026-05-07 bottom-tray gap fix: the visible floor span now uses a separate `bottom_tray_depth = 204 mm`, while the shelf/fit-safe envelope remains 200 mm. This makes `erb_lower_chassis_bottom_tray.step` span Y -102..102 so it reaches the front/rear panel inner rail faces instead of stopping at the old 200 mm envelope. `scripts/check_mounting_features.py` now checks this 204 mm target so the front/back floor gap cannot falsely pass.
- 2026-05-07 shelf default change: added `erb_equipment_shelf_four_way_cable_shallow.step`, which applies the same shallow centered cable notch to left, right, front, and rear edges. The default lower/upper shelf occurrences in `erb_lower_chassis_assembly.step` now use this four-way shallow shelf. Existing `erb_equipment_shelf.step`, `erb_equipment_shelf_side_cable.step`, and `erb_equipment_shelf_side_cable_shallow.step` remain available as alternates.
- 2026-05-07 third shelf stack, superseded 2026-05-16: added `erb_shelf_spacer_block_55mm.step`, a 20 x 50 x 55 mm spacer block with a 4.5 mm through-hole matching the existing M4 shelf-hole pattern. This was originally placed as four spacer blocks on the upper shelf at X +/-80 mm and Y +/-75 mm, plus a third four-way shallow shelf at Z=183 mm. On 2026-05-16 the active assembly stopped placing those spacer blocks and instead added side-plate shelf ledges at Z=183. The spacer STEP is kept as an optional legacy part.
- 2026-05-08 front/rear panel mounting fix: front, rear, and alternate vented rear panels now have full through-cut M5 heat-set pilot holes in their side rails. The prior modeled cuts were only 15 mm long inside an 18 mm rail and could leave the holes visually/physically buried near the side faces. New parameter is `front_rear_panel_m5_pilot_cut_length = 24 mm`; `scripts/check_mounting_features.py` now verifies these pilots open through the rail faces and align with the side-panel holes.
- 2026-05-08 top dome visual prototypes: added `cad/erb_top_dome.py`, generating `erb_top_dome_plain.step`, `erb_top_dome_sensor_mockup.step`, and `erb_top_dome_prototypes.step`. Current dome is a 224 mm outside diameter hollow hemisphere with 3.5 mm wall and a 240 x 240 x 6 mm square mounting flange. The sensor mockup adds a 26 mm front camera opening on a flat pad, a 48 mm top sensor/LiDAR opening, and two side service ports. These are non-structural visual/fit studies intended to print flange/open-rim down.
- 2026-05-08 assembly visualization change: `erb_lower_chassis_assembly.step` briefly showed `erb_top_dome_sensor_mockup` as the top cover, placed at Z=240 mm, replacing the flat top lid in the visual assembly. This was superseded on 2026-05-11 by the wide-over-wheel Stage 2 blockout. The standalone printable `erb_lower_chassis_top_lid.step` and dome prototype STEP files remain exported unchanged for reference.
- 2026-05-08 dome fit cleanup: added a 12 mm tall cylindrical rim skirt to the top dome so the shell overlaps into the square mounting flange instead of visually floating above it. Removed the crude external front camera block from the sensor dome; the sensor version now keeps only a 26 mm front aperture plus the 48 mm top sensor opening. A real camera support should be redesigned around the selected camera module rather than using that first-pass slab.
- 2026-05-09 dome connectivity fix: the top sensor boss was only tangent to the sphere and rendered as a floating disk. It is now a 64 mm diameter x 12 mm tall boss embedded 8 mm into the dome, making `erb_top_dome_sensor_mockup.step` a single solid. The lower dome rim band was increased to 22 mm and the shell/flange/rim are explicitly fused so the dome no longer depends on merely touching surfaces in the STEP viewer.
- 2026-05-17 rear panel two-color split: `erb_lower_chassis_rear_panel.step` remains the default no-vent rear panel and keeps the same stopped dovetails, top retention bosses, rear-pocket dimensions, and assembled placement, but it now exports as a two-solid compound: rear body plus separate bump-out shell. The bump-out shell overlaps 0.2 mm into the rear body so Bambu Studio can assign the bump-out a different color while still printing as one fused part. Separate `erb_lower_chassis_rear_panel_body.step` and `erb_lower_chassis_rear_panel_bumpout.step` files are also exported for workflows that prefer importing individual color bodies.
- 2026-05-18 detachable rear bump-out alternate: added `erb_lower_chassis_rear_panel_detachable.step`, `erb_lower_chassis_rear_panel_detachable_body.step`, and `erb_lower_chassis_rear_panel_detachable_bumpout.step`. This alternate changes the cable bump-out into a separate top-down vertical slide-on cartridge. After real PETG fit feedback, the detachable rear body now intentionally shrinks only its male side dovetails to 9.25 mm depth, 8.0 mm neck, and 14.0 mm head while leaving the already-printed side-chassis female slots unchanged; this targets roughly 0.75 mm side clearance and 1.25 mm depth clearance against the current side slots. The rear panel body has two straight receiver channels attached to the panel frame at X +/-46 mm, molded bottom/top support webbing so the rails are visibly tied into the rear plate cutout, bottom stops at Z 40 mm, and one M4 heat-set retainer boss near the top. The removable open-backed shell is a single solid with hidden straight vertical tongues that slide into the receiver channels plus one M4 retainer slot. The detachable shell keeps the same outer bump-out face depth as the default version rather than adding a spacer behind it, and the body/shell engaged pair checks at 0.000000 mm^3 overlap.
- 2026-05-18 service-fit shelf tolerance trial: added `erb_equipment_shelf_service_fit.step`, now a 170 x 188 x 6 mm shelf and used for the lower/upper/third shelf occurrences in the active assembly so clearance is visible in `erb_lower_chassis_assembly.step`. It preserves the nominal side-ledge mount centers at X/Y +/-75 mm but replaces tight round M4 clearance holes with 14 mm rounded-square adjustment slots so real-world side-wall bow, PETG print swell, and slight ledge-hole drift can be tested. After CAD review of the real-fit photo, the service shelf now uses 36 mm deep x 128 mm long side reliefs centered on the left/right edges so the shelf is narrow through the wheel-side hardware zone around Y +/-52 mm, while retaining material around the Y +/-75 mm screw pads.
- 2026-05-06 rear panel change: `erb_lower_chassis_rear_panel.step` became the default no-vent rear panel and is used in the assembly. It has a 22 mm deep outward tapered bump-out, hollow/open on the chassis interior for cable slack, tapering from 132 x 192 mm at the panel to a blank 104 x 164 mm outer face for Bambu Studio text. The top/bottom border matches the left/right border at 24 mm. The previous vented rear panel moved to `erb_lower_chassis_rear_panel_vented.step`.
- 2026-04-30 print feedback: the original front/rear shelf pads printed as detached tree/support islands because they did not overlap the panel skin. This was first fixed with wall-overlapped front/rear bracket pads.
- 2026-05-01 serviceability change: shelf supports moved off the front/rear panels and onto the left/right side plates. Front/rear panels now carry no shelf brackets so they can become removable or hinged service doors. Side plates have two short front/rear ledge pads per shelf level, overlapping 6 mm into the side wall, with the center axle/wheel gap left open.
- 2026-05-03 shelf variant: added `erb_equipment_shelf_side_cable.step` as an alternate shelf. It keeps the current shelf unchanged and adds centered side-edge cable notches on the wheel/side-plate sides while preserving the four side-ledge screw areas.
- 2026-05-03 shelf variant: added `erb_equipment_shelf_side_cable_shallow.step` as a second alternate shelf. It keeps the same 84 mm notch length but cuts only 23 mm inward, preserving more shelf area in the center than the 46 mm deep side-cable version.
- 2026-05-04 ESP32 accessory: added a parametric two-piece ESP32-WROOM holder sized around the HiLetgo ESP-32S board shown in photos. It has M3 shelf-mount ears, side pin-access windows for IMU wiring, a USB opening, an opposite cable opening, and a vented/removable lid. Working board envelope is 55.0 x 28.5 mm with 1.6 mm side clearance.
- 2026-05-04 ESP32 holder fix: moved lid screws off the narrow short-edge rim and onto external end-tab/boss pads. Lid counterbores now have about 2.45 mm short-edge margin; M3 shelf-mount counterbores were moved outward and retain about 2.0 mm side margin.
- 2026-05-04 ESP32 holder pin access fix: revised the base to behave more like the downloaded pinout case. It now has 52 mm long full-height side openings plus 6.2 x 52 mm bottom troughs under both header rows so downward pins and jumper leads can pass through to the outside.
- 2026-04-30 axle redesign: the wheel axle interface is now a replaceable chamfered-square cartridge rather than a thin face insert. Current target is a 76 mm square x 30 mm thick keyed body in a 79 mm chamfered through-pocket, plus a 140 x 116 x 6 mm outside retention flange shifted 8 mm upward. The square pocket is intended to carry motor torque; four M5 flange bolts retain the cartridge axially and land in solid side-plate material outside the pocket.
- 2026-04-30 axle height adjustment: axle center moved from 50 mm to 58 mm above the chassis bottom. This lowers the chassis 8 mm relative to the wheel axle and improves lower axle-cartridge bolt padding.
- 2026-05-14 axle insert tab-washer relief: added a shallow anti-rotation washer tab pocket to all three axle insert variants, then corrected it to sit off one left/right side of the axle profile in the face view, not above or below the double-D opening. Current relief is 12 mm lateral x 12 mm vertical x 3.2 mm deep on the washer/nut-side cartridge face, starting 1.5 mm beyond the side of the axle profile. The intended hardware order is wheel/axle -> through insert hole -> tab washer -> nut, so the relief is on the face opposite the outside retainer flange. This is sized for the latest measured washer-tab width of about 11.09 mm, leaving about 0.9 mm total clearance in either pocket direction. Important generation detail: the tab relief is cut after the global insert chamfer so the exported STEP mouth remains 12 x 12 mm instead of being widened by chamfering. `scripts/report_axle_insert_dimensions.py` measures the exported STEP files and must pass before printing these inserts.
- 2026-05-14 FreeCAD editability pass: added `freecad/erb_bottom_tray_part_design.py`, generating `exports/freecad/native/erb_bottom_tray_part_design.FCStd`. This is a one-Body Part Design editing model with named AdditiveBox/SubtractiveCylinder features and a reference spreadsheet. It is intended for manual FreeCAD edits of the bottom tray, while the Python/text-to-cad generator remains the production source of truth.
- The shelves are intentionally plain flat plates with wiring slots; device-specific retention and vibration-isolation hardware will be added after real component layout is confirmed.

## Text-to-CAD Viewer Notes

- 2026-04-30: FreeCAD was de-prioritized because imported files were awkward to inspect as separate parts.
- Patched `/Users/jfurr/text-to-cad/viewer` so the CAD viewer uses trackball-style rotation instead of orbit-only controls. This is intended to avoid top/bottom gimbal-lock behavior while inspecting chassis parts.
- Added an in-view dimensions overlay showing model XYZ bounds in mm/inches and selected/hovered part bounds when available.
- The viewer now treats Z as the vertical/top axis for the view-plane controls.

## Open Questions

- Confirm the exact BOSGAME M4 body dimensions and preferred cable-exit orientation once it is in hand.
- Confirm the FLIPSKY Dual 75100 board/case variant and real connector/cable bend envelope.
- Confirm battery wiring/strap direction and whether the batteries should sit side-by-side across width or be individually retained in trays.
- Decide whether an 18 inch deep version is worth the extra complexity of split side plates.
