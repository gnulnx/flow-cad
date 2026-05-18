# Erb Stage 1 Lower Chassis

This project contains the active wider/taller lower chassis for Erb, a two-wheel self-balancing waiter robot.

Current work is Stage 1 only: the lower structural chassis box around the wheels, axle mounts, and two generic flat equipment shelves.

## Generate STEP Files

```bash
~/BLR/text-to-cad/.venv/bin/python cad/erb_lower_chassis.py
```

Generated files are written to:

- `exports/step/`
- `reports/stage1_lower_chassis_report.txt`

## View In Text-To-CAD

Mirror the generated STEP files into the local text-to-cad app and generate the viewer sidecars:

```bash
~/BLR/text-to-cad/.venv/bin/python scripts/sync_text_to_cad.py
```

Then start CAD Explorer if it is not already running:

```bash
cd ~/BLR/text-to-cad/viewer
npm run dev:ensure
```

Open:

```text
http://127.0.0.1:4178/?dir=models/erb_balance_bot/stage1_lower_chassis&file=erb_lower_chassis_assembly.step
http://127.0.0.1:4178/?dir=models/erb_balance_bot&file=erb_lower_chassis_assembly.step
```

The Bambu Studio STEP files remain in this project under `exports/step/`. The text-to-cad copy is a viewer mirror.

## Check Part Interference

Run the assembly interference checker before printing:

```bash
~/BLR/text-to-cad/.venv/bin/python scripts/check_assembly_interference.py
```

It writes:

- `reports/stage1_interference_report.txt`
- `reports/stage1_interference_report.json`
- `reports/interference_step/*.step` for each detected overlap volume

The checker exits non-zero when it finds solid overlaps above the configured threshold.

## Export FreeCAD Assembly

Generate or refresh the STEP files first, then run:

```bash
scripts/export_freecad.sh
```

The FreeCAD documents are written to:

- `exports/freecad/erb_lower_chassis_assembly.FCStd`
- `exports/freecad/erb_lower_chassis_print_layout.FCStd`

The persistent project notes are in `CODEX_CONTEXT.md`.
