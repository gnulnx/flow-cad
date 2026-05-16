# Erb Balance Bot Project Context

Project directory: `/Users/jfurr/3DPrintBalanceBot`

Expanded payload variant directory:

- `/Users/jfurr/3DPrintBalanceBot/expanded_payload_chassis`

The expanded variant keeps its own CAD script, exports, reports, interference checker, and text-to-cad mirror target. It explores a wider/taller lower chassis for the BOSGAME M4 mini PC, FLIPSKY Dual 75100 controller, and two HRB 6S packs without mutating this baseline Stage 1 design.

## Current Scope

Stage 1 is the lower structural chassis module only. Do not design the torso, shell, arms, head, tray, compute stack, cosmetic bodywork, or full waiter robot yet.

The lower chassis is a modular screw-together 3D-printable box for:

- Battery retention from top access
- Two generic flat equipment shelves above the bottom battery platform
- Structural axle mounting for two 10 inch hub motor wheels
- Replaceable bolt-in axle inserts for M16 / double-D axle fit tuning

## Key Dimensions

- Wheel diameter: 260 mm
- Wheel/tire width: 100 mm
- Target center chassis outer width: 200 mm
- Target total robot width: about 457 mm / 18 inches
- Chassis depth: 240 mm
- Chassis height: 220 mm
- Side plate base thickness: 12 mm
- Wall thickness: 6 mm
- Bottom thickness: 8 mm
- Top lid thickness: 6 mm
- Axle center height from bottom: 50 mm
- Fit-safe cross-part envelope after interference refactor: 140 mm wide x 200 mm deep
- Top lid face plate: 200 mm wide x 240 mm deep; underside locating lip stays inside the fit-safe envelope
- Generic flat equipment shelf: 140 mm wide x 200 mm deep x 6 mm thick
- Shelf levels: lower shelf bottom at Z=76 mm, upper shelf bottom at Z=146 mm
- The top lid is a top cap sitting above the 220 mm side plates; overall assembly height is 226 mm.
- Replaceable axle inserts are 12 mm thick to match the side wall thickness and sit flush in the side wall pocket.
- Front/rear panels now provide 8 total M4 shelf support brackets for the two flat shelves.

## CAD Approach

Use a source-controlled parametric Python CAD generator. The initial generator is:

- `cad/erb_lower_chassis.py`

The generator uses `build123d` from the local environment:

- `/Users/jfurr/text-to-cad/.venv/bin/python`

The generated STEP files are exported under:

- `exports/step/`

The generated report is:

- `reports/stage1_lower_chassis_report.txt`

## Text-To-CAD Viewer Mirror

The project can be mirrored into the local text-to-cad CAD Explorer app for visual iteration while keeping the Bambu Studio STEP exports in this project.

Sync command from `/Users/jfurr/3DPrintBalanceBot`:

```bash
/Users/jfurr/text-to-cad/.venv/bin/python scripts/sync_text_to_cad.py
```

The sync script:

- Regenerates this project's STEP files by default.
- Copies the STEP files to `/Users/jfurr/text-to-cad/models/erb_balance_bot/stage1_lower_chassis/`.
- Runs text-to-cad `gen_step_part` / `gen_step_assembly` to create package-local `.glb` and topology sidecars for CAD Explorer.

Viewer URL:

```text
http://127.0.0.1:4178/?dir=models/erb_balance_bot/stage1_lower_chassis&file=erb_lower_chassis_assembly.step
```

The text-to-cad copy is a generated viewer mirror, not the source of truth.

If CAD Explorer shows `Unexpected token '<', '<!doctype' is not valid JSON` while loading a part, it is usually stale browser persistence pointing at a retired STEP file or sidecar path. Reset the viewer state with:

```text
http://127.0.0.1:4178/?resetPersistence=1&dir=models/erb_balance_bot/stage1_lower_chassis&file=erb_lower_chassis_assembly.step
```

## Assembly Interference Checking

Use the interference checker before printing newly generated parts:

```bash
/Users/jfurr/text-to-cad/.venv/bin/python scripts/check_assembly_interference.py
```

The checker imports `cad/erb_lower_chassis.py`, builds the same part solids and assembly transforms used for STEP export, checks all pairwise solid intersections, and writes:

- `reports/stage1_interference_report.txt`
- `reports/stage1_interference_report.json`
- `reports/interference_step/*.step`

It exits with status 1 when it finds real overlap volume above the threshold. Face-to-face contact without volume is ignored.

## Stage 1 Part Set

Requested STEP exports:

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

## Current Design Decisions

- Coordinate convention: X is robot width, Y is front/rear depth, Z is vertical.
- Side plates are the primary structural parts.
- Side plates include a 12 mm base plate plus internal axle boss/block geometry for 30 mm total reinforced thickness in the axle zone.
- Axle inserts are recessed flush into the side plate outer faces so the nominal 200 mm center chassis width is preserved.
- Side plates use an oversize round clearance through-hole behind the insert; the replaceable insert defines the actual axle fit.
- Insert profiles are modeled as double-D holes using the requested diameter and flat-to-flat values.
- The assembly STEP uses the medium axle insert variant by default.
- Cross panels and trays now use a 140 x 200 mm fit-safe envelope so they clear side-plate rails and axle bosses.
- The top lid face plate is now a full top cap spanning the 200 x 240 mm chassis footprint, while its underside locating lip remains within the fit-safe envelope.
- Top lid screw holes align over side-wall top-rail M4 heat-set pilot pockets.
- Replaceable axle inserts match the 12 mm side-wall thickness so their external and internal faces are flush with the side wall pocket.
- Axle bosses, diagonal ribs, and side rails are capped at the same 30 mm total local side-plate thickness so the support stack is flush with the raised side-wall rails when viewed/printed flat.
- The old special battery tray and VESC-specific shelf mounts are removed from the active design.
- The generic flat shelf fills the 140 x 200 mm fit-safe envelope, has M4 support holes near X +/-58 mm and Y +/-92 mm, and keeps three long center slots open for wiring.
- The same shelf part is used twice in the assembly: lower shelf for the VESC/controller zone and upper shelf for the mini PC zone. The bottom tray remains the battery platform.
- Front/rear panels include 8 total shelf bracket pads: 2 X positions x 2 shelf levels x 2 panels.
- The bottom tray raised side rails are split into front/rear segments to avoid the central axle boss zone.
- Battery/controller/mini PC retention features remain provisional until real component dimensions are measured.
- As of the current refactor, `scripts/check_assembly_interference.py` reports zero solid overlaps above 0.05 mm^3.

## Open Mechanical Questions

- Confirm the real hub motor axle profile with calipers: diameter, flat-to-flat, thread length, shoulder geometry, and washer/nut stack.
- Confirm battery dimensions, mass, and strap/clamp preference.
- Confirm exact dual VESC controller dimensions, mounting hole spacing, capacitor clearance, and cable bend radius.
- Confirm mini PC dimensions and cable exit clearance.
- Decide whether axle inserts should eventually be metal, printed PETG-CF, or printed prototypes followed by machined plates.
- Confirm final heat-set insert part numbers before locking pilot hole diameters.

## Regeneration Command

From `/Users/jfurr/3DPrintBalanceBot`:

```bash
/Users/jfurr/text-to-cad/.venv/bin/python cad/erb_lower_chassis.py
```
