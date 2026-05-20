# Erb Stage 1 Lower Chassis

This project contains the active wider/taller lower chassis for Erb, a two-wheel self-balancing waiter robot.

Current work is Stage 1 only: the lower structural chassis box around the wheels, axle mounts, and two generic flat equipment shelves.

## Project Setup

Use Python 3.11 or newer. A local virtual environment is recommended:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

For a runtime-only editable install without test dependencies:

```bash
python -m pip install -e .
```

Optional machine-specific tool paths can be set in the environment or in a local `.env` copied from `.env.example`:

- `TEXT_TO_CAD_ROOT`
- `TEXT_TO_CAD_PYTHON`
- `FREECAD_CMD`

Run the unit tests after setup and after every code change:

```bash
python -m pytest
```

Generate the active chassis STEP files and create a handoff bundle:

```bash
flow cad build
```

The handoff bundle is created at `handoff/exports.tar.gz`.

Generated files are written to:

- `b3/exports/step/`
- `b3/reports/`

## View In Text-To-CAD

Mirror the generated STEP files into the local text-to-cad app and generate the viewer sidecars:

```bash
python scripts/sync_text_to_cad.py
```

Then start CAD Explorer if it is not already running:

```bash
cd "${TEXT_TO_CAD_ROOT:-$HOME/BLR/text-to-cad}/viewer"
npm run dev:ensure
```

Open:

```text
http://127.0.0.1:4178/?dir=models/b3_balance_bot/stage1_lower_chassis&file=b3_lower_chassis_assembly.step
http://127.0.0.1:4178/?dir=models/b3_balance_bot&file=b3_lower_chassis_assembly.step
```

The Bambu Studio STEP files remain in this project under `b3/exports/step/`. The text-to-cad copy is a viewer mirror.

## Check Part Interference

Run the assembly interference checker before printing:

```bash
python scripts/check_assembly_interference.py
```

It writes:

- `b3/reports/stage1_interference_report.txt`
- `b3/reports/stage1_interference_report.json`
- `b3/reports/interference_step/*.step` for each detected overlap volume

The checker exits non-zero when it finds solid overlaps above the configured threshold.

## Export FreeCAD Assembly

Generate or refresh the STEP files first, then run:

```bash
scripts/export_freecad.sh
```

Set `FREECAD_CMD=/path/to/freecadcmd` if FreeCAD is not discoverable on `PATH`.

The FreeCAD documents are written to:

- `b3/exports/freecad/b3_lower_chassis_assembly.FCStd`
- `b3/exports/freecad/b3_lower_chassis_print_layout.FCStd`

## Local Tool Configuration

The scripts are intended to work on Linux and macOS. Optional machine-specific paths can be set in the environment or in a local `.env` copied from `.env.example`:

- `TEXT_TO_CAD_ROOT`
- `TEXT_TO_CAD_PYTHON`
- `FREECAD_CMD`
