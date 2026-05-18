# Agent Operating Guide

This file is the first-stop guide for Codex, Qwen, or any other coding agent working in this repo.

## Project Purpose

This repo contains the parametric CAD source and generated print artifacts for the Erb two-wheel balance bot chassis. The active work is mechanical CAD for printable robot parts, STEP exports, validation reports, and Bambu Studio handoff artifacts.

The repo is authoritative. The workstation is normally the heavy CAD generation and validation machine, but laptop checkouts must remain supported for Codex sessions, source edits, STEP generation, validation, and Bambu Studio handoff.

## Source Of Truth

- Primary active generator: `cad/erb_lower_chassis.py`
- Active design history and mechanical rationale: `CODEX_CONTEXT.md`
- Current improvement proposal: `CODEX_SUGGESTIONS.md`
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
~/BLR/text-to-cad/.venv/bin/python cad/erb_lower_chassis.py
```

Run assembly interference validation:

```bash
~/BLR/text-to-cad/.venv/bin/python scripts/check_assembly_interference.py
```

Run mounting feature validation:

```bash
~/BLR/text-to-cad/.venv/bin/python scripts/check_mounting_features.py
```

Run upper adapter-deck stack validation:

```bash
~/BLR/text-to-cad/.venv/bin/python scripts/check_upper_hook_geometry.py
```

Mirror STEP files to text-to-cad viewer:

```bash
~/BLR/text-to-cad/.venv/bin/python scripts/sync_text_to_cad.py
```

Export FreeCAD documents when FreeCAD is available:

```bash
scripts/export_freecad.sh
```

These commands should be made more portable over time. Until then, inspect existing scripts before assuming the command works unchanged on every machine.

## Validation Rules

Before claiming a printable CAD change is ready, run the relevant checks:

- Always run the generator for changes to `cad/erb_lower_chassis.py`.
- Run `scripts/check_mounting_features.py` for tray, shelf, panel, axle insert, or hardware-hole changes.
- Run `scripts/check_assembly_interference.py` for any assembly placement or envelope change.
- Run `scripts/check_upper_hook_geometry.py` for upper adapter-deck or upper blockout changes.
- Run `scripts/report_axle_insert_dimensions.py` for axle washer-tab relief or insert geometry changes when FreeCAD is available.

If a command cannot be run because dependencies are missing, say so explicitly and include the command that should be run on the configured machine.

## Print Handoff Rules

Bambu Studio should receive intentional print artifacts, not the whole working tree.

- STEP files for slicing live under `exports/step/`.
- Reference wheel/axle files are not printable parts.
- Assembly STEP files are for inspection, not direct printing, unless the user explicitly says otherwise.
- `.3mf` files are slicer/project artifacts. Treat them as handoff snapshots, not generated source.
- Prefer a dated print bundle and a short manifest for laptop transfer.

## Files Not To Edit Directly

Do not hand-edit generated CAD artifacts:

- `exports/step/*.step`
- `exports/freecad/*.FCStd`
- `exports/freecad/**/*.FCStd`
- generated report files under `reports/`, unless the task is explicitly documentation/report maintenance
- text-to-cad viewer sidecars such as hidden `.step` asset folders

Instead, edit the Python source or validation script that produces the artifact, regenerate, and then report what changed.

## Context Policy

`CODEX_CONTEXT.md` is useful but long. Do not read it end-to-end by default.

For most tasks:

1. Inspect current source and reports first.
2. Search `CODEX_CONTEXT.md` only for the relevant part name, date, or design topic.
3. Read `CODEX_SUGGESTIONS.md` when the task concerns workflow, project structure, tests, validation, or agent/tooling improvements.
4. Preserve concise updates. Avoid appending long running narratives unless the user asks for a design-history update.

## Change Style

- Keep changes small and mechanical.
- Prefer improving the current workflow before large refactors.
- Do not move the monolithic generator until tests and validation protect the current behavior.
- Add tests/validators around existing behavior before extracting modules.
- Preserve generated STEP handoff behavior unless the user asks to change it.

## Git Hygiene

The working tree may contain user or other-agent changes.

- Do not revert unrelated changes.
- Do not delete untracked files unless the user asks.
- Treat `QWEN_SUGGESTIONS.md` and other agent-authored docs as user-visible work.
- Separate cleanup of tracked junk, generated files, or ignore rules into its own explicit change when possible.
