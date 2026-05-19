# Agent Operating Guide

This file is the first-stop guide for Codex, Qwen, or any other coding agent working in this repo.

## Project Purpose

This repo contains the parametric CAD source and generated print artifacts for the Erb two-wheel balance bot chassis. The active work is mechanical CAD for printable robot parts, STEP exports, validation reports, and Bambu Studio handoff artifacts.

The repo is authoritative. The workstation is normally the heavy CAD generation and validation machine, but laptop checkouts must remain supported for Codex sessions, source edits, STEP generation, validation, and Bambu Studio handoff.

## Source Of Truth

- Primary active generator: `cad/erb_lower_chassis.py`
- Current improvement proposal: `CODEX_SUGGESTIONS.md`
- Active mating-interface registry: `PART_INTERFACES.md`
- Active print handoff manifest: `PRINT_MANIFEST.md`
- Generated STEP outputs: `exports/step/`
- Validation reports: `reports/`

Do not treat text-to-cad mirrors, FreeCAD exports, or Bambu Studio files as the source of truth unless the user explicitly says a manual slicer/FreeCAD change must be brought back into source.

## Path Rules

Keep the repo portable across workstation and laptop.

- Prefer repo-relative paths derived from `Path(__file__).resolve()`.
- Do not hardcode `/home/gnulnx/...`, `/Users/jfurr/...`, or `/Applications/FreeCAD.app/...` in new code.
- External tool paths should come from CLI args, environment variables, ignored local config, or clear discovery.
- Suggested environment variables:
  - `TEXT_TO_CAD_ROOT`
  - `TEXT_TO_CAD_PYTHON`
  - `FREECAD_CMD`
- If an optional dependency is missing, fail with a clear message explaining exactly what to install or which variable to set.

## Standard Commands

Generate the active chassis STEP files:

```bash
python cad/erb_lower_chassis.py
```

Run assembly interference validation:

```bash
python scripts/check_assembly_interference.py
```

Run mounting feature validation:

```bash
python scripts/check_mounting_features.py
```

Run upper adapter-deck stack validation:

```bash
python scripts/check_upper_hook_geometry.py
```

Mirror STEP files to text-to-cad viewer:

```bash
python scripts/sync_text_to_cad.py
```

Create a laptop/Bambu handoff tarball:

```bash
python scripts/create_exports_bundle.py
```

Export FreeCAD documents when FreeCAD is available:

```bash
scripts/export_freecad.sh
```

Use `.env`, `TEXT_TO_CAD_ROOT`, `TEXT_TO_CAD_PYTHON`, or `FREECAD_CMD` when a machine needs non-default external tool paths.

## Validation Rules

For any code change, always run the unit test suite before reporting the work as complete:

```bash
python -m pytest
```

Before claiming a printable CAD change is ready, run the relevant checks:

- Always run the generator for changes to `cad/erb_lower_chassis.py`.
- Run `scripts/check_mounting_features.py` for tray, shelf, panel, axle insert, or hardware-hole changes.
- Run `scripts/check_assembly_interference.py` for any assembly placement or envelope change.
- Run `scripts/check_upper_hook_geometry.py` for upper adapter-deck or upper blockout changes.
- Run `scripts/report_axle_insert_dimensions.py` for axle washer-tab relief or insert geometry changes when FreeCAD is available.

If a command cannot be run because dependencies are missing, say so explicitly and include the command that should be run on the configured machine.

## CAD Interface Change Protocol

For any change involving fit, latch, slide, hook, dovetail, T-slot, receiver, rail, tongue, groove, screw alignment, or collision clearance, treat the mating interface as the unit of work.

Read `PART_INTERFACES.md` before editing any mating-interface geometry. If the interface is listed there, use its fixed/moving part contract, directions, clearances, and validation notes. If the interface is not listed, add or update a concise entry when the task creates a new durable mating contract.

Before editing source:

1. Identify the exact mating files and source functions.
2. State the fixed part, moving part, slide/install direction, capture direction, and proud/lead-in direction.
3. Map ambiguous words such as "out", "taller", "wider", "deeper", "stick out", and "extend" to X/Y/Z before changing code.
4. Measure the current bbox or feature positions for both mating parts.

Use this repo's global coordinate convention unless a source function explicitly defines a local frame:

- X is robot width / left-right.
- Y is front/rear depth.
- Z is vertical.

For paired printable parts, inspect and validate the pair directly. Do not rely only on the whole assembly if the assembly view makes two mating pieces look like one solid.

Example rear detachable panel contract:

- Fixed part: `exports/step/erb_lower_chassis_rear_panel_detachable_body.step`
- Moving part: `exports/step/erb_lower_chassis_rear_panel_detachable_bumpout.step`
- Source functions: `make_rear_panel_detachable_body()` and `make_rear_panel_detachable_bumpout_shell()`
- Slide/install direction: Z
- Capture direction: X
- Proud/lead-in direction: Y
- Required behavior: bumpout T heads must protrude in Y past the shell rim enough to enter the rear-panel receiver before the shell perimeter contacts the panel.

Before reporting a mating-geometry change as complete:

- Regenerate STEP files from source.
- Re-measure the relevant before/after feature positions.
- Check direct body-to-body overlap or clearance for the mating pair.
- Run any targeted validator that applies; if no targeted validator exists, report the manual measurement used.
- Sync text-to-cad only after the source geometry validates.

## Print Handoff Rules

Bambu Studio should receive intentional print artifacts, not the whole working tree.

Read `PRINT_MANIFEST.md` before changing the intended print set, preparing a handoff, or deciding whether a STEP file is printable, reference-only, or inspection-only. Update it whenever the current print handoff intent changes.

- STEP files for slicing live under `exports/step/`.
- Reference wheel/axle files are not printable parts.
- Assembly STEP files are for inspection, not direct printing, unless the user explicitly says otherwise.
- `.3mf` files are slicer/project artifacts. Treat them as handoff snapshots, not generated source.
- Prefer a dated print bundle and a short manifest for laptop transfer.
- Use `python scripts/create_exports_bundle.py` to create a local `handoff/*.tar.gz` bundle of the current `exports/` tree. The script prints an `scp` command for copying it to `jfurr@laptop:/Users/jfurr/`.

## Files Not To Edit Directly

Do not hand-edit generated CAD artifacts:

- `exports/step/*.step`
- `exports/freecad/*.FCStd`
- `exports/freecad/**/*.FCStd`
- generated report files under `reports/`, unless the task is explicitly documentation/report maintenance
- text-to-cad viewer sidecars such as hidden `.step` asset folders

Instead, edit the Python source or validation script that produces the artifact, regenerate, and then report what changed.

Generated STEP files are tracked, but export timestamps are intentionally normalized after generation so unchanged geometry does not churn every commit. If a STEP file still diffs after regeneration, inspect the DATA-section geometry diff before assuming it is metadata-only.

## Context Policy

Do not rely on historical narrative docs as project state. Inspect current source, tests, generated reports, and manifests.

For most tasks:

1. Inspect current source and reports first.
2. Read `PART_INTERFACES.md` when the task touches mating geometry, fit, clearance, or hardware alignment.
3. Read `PRINT_MANIFEST.md` when the task touches print handoff, Bambu Studio artifacts, printable/reference classification, or bundle contents.
4. Read `CODEX_SUGGESTIONS.md` when the task concerns workflow, project structure, tests, validation, or agent/tooling improvements.
5. Preserve concise updates. Avoid creating long running narratives unless the user explicitly asks for one.

## Change Style

- Keep changes small and mechanical.
- Prefer improving the current workflow before large refactors.
- Do not move the monolithic generator until tests and validation protect the current behavior.
- Add tests/validators around existing behavior before extracting modules.
- Run `python -m pytest` for every code change.
- Preserve generated STEP handoff behavior unless the user asks to change it.
- Keep `PART_INTERFACES.md` and `PRINT_MANIFEST.md` current when changing durable mating contracts or print handoff intent.

## Git Hygiene

The working tree may contain user or other-agent changes.

- Do not revert unrelated changes.
- Do not delete untracked files unless the user asks.
- Treat `QWEN_SUGGESTIONS.md` and other agent-authored docs as user-visible work.
- Separate cleanup of tracked junk, generated files, or ignore rules into its own explicit change when possible.
