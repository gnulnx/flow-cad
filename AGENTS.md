# Agent Operating Guide

This file is the first-stop guide for Codex, Qwen, or any other coding agent working in this repo.

## Project Purpose

This repo contains the parametric CAD source and generated print artifacts for the Erb two-wheel balance bot chassis. The active work is mechanical CAD for printable robot parts, STEP exports, validation reports, and Bambu Studio handoff artifacts.

The repo is authoritative. The workstation is normally the heavy CAD generation and validation machine, but laptop checkouts must remain supported for Codex sessions, source edits, STEP generation, validation, and Bambu Studio handoff.

## Source Of Truth

- Primary active generator: `src/flow_cad/main.py` (Entry point for the `flow cad` command)
- Package root: `src/flow_cad/` (Modular part and core definitions)
- Parameters: `src/flow_cad/params.py` (Source of truth for all dimensions)
- Source part registry: `src/flow_cad/registry.py` (Source of truth for intended parts, export filenames, module ids, roles, and print intent)
- Active cache schema: `src/flow_cad/core/cache.py`
- Active mating-interface registry: `docs/PART_INTERFACES.md`
- Active print handoff manifest: `docs/PRINT_MANIFEST.md`
- Bundled project skills: `skills/`
- Generated STEP outputs: `b3/exports/step/`
- Generated Hand-off bundle: `handoff/exports.tar.gz`
- Validation reports: `b3/reports/`
- Generated active cache: `b3/registry.db` (ignored build artifact; query surface only, not design truth)

Do not treat text-to-cad mirrors, FreeCAD exports, or Bambu Studio files as the source of truth unless the user explicitly says a manual slicer/FreeCAD change must be brought back into source.

## Architecture
 
- **`src/flow_cad/core/`**: Primitives, assembly coordination, and exporter logic.
- **`src/flow_cad/parts/`**: Modular part generators (e.g., `chassis.py`, `panels.py`, `shelves.py`).
- **`src/flow_cad/registry.py`**: Code-first registry of active generated parts and their export metadata.
- **`src/flow_cad/params.py`**: Centralized `ChassisParams` class. Dimensions are injected into generators via this object.
- **`src/flow_cad/cli.py`**: Entry point for the `flow` command-line tool.
- **`scripts/`**: One-off validation and maintenance scripts.
- **`tests/`**: Unit tests for geometry and parameters.
 
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

Initialize a new Flow CAD project:

```bash
flow init
```

`flow init` copies bundled skills from this repo's `skills/` directory into the
new project. Keep those bundled skills generic enough for any Flow CAD project.

Generate the active chassis STEP files and handoff bundle:
 
```bash
flow cad build
```

The `build` command automatically creates `handoff/exports.tar.gz`.

`flow cad build` also updates `b3/registry.db` by default. Use `flow cad build --no-cache` only when intentionally skipping the generated active-cache update.

Query the generated active cache:

```bash
flow registry list
flow registry show <component_id>
```

Run assembly interference validation:

```bash
python scripts/check_assembly_interference.py
```

Run mounting feature validation:

```bash
python scripts/check_mounting_features.py
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

- Run `python -m pytest`.
- Run `scripts/check_mounting_features.py` for tray, shelf, panel, axle insert, or hardware-hole changes.
- Run `scripts/check_assembly_interference.py` for any assembly placement or envelope change.
- Run `src/flow_cad/scripts/validate_print_manifest.py --manifest docs/PRINT_MANIFEST.md` to verify print handoff intent matches registry
- Run `scripts/report_axle_insert_dimensions.py` for axle washer-tab relief or insert geometry changes when FreeCAD is available.

If a command cannot be run because dependencies are missing, say so explicitly and include the command that should be run on the configured machine.

## Skill Ownership

This repo should grow reusable agent skills that make Flow CAD work more
reliable across projects. Add or update a skill in `skills/` when the guidance
is about Flow CAD runtime/tooling behavior rather than one robot's geometry.

Put these in Flow CAD `skills/`:

- Build, export, viewer, reload, active-cache, and handoff workflow.
- Generic placement-review and validator patterns.
- Generic STEP/STL/manifest/cache troubleshooting.
- Reusable instructions for creating project validators.
- Cross-project CAD agent workflow that `flow init` should copy everywhere.

Put these in project-local `skills/`:

- Product or robot-specific part families and mating contracts.
- Project-specific coordinate conventions beyond the generic Flow CAD frame.
- Hardware-specific washer/nut/insert/sensor/actuator access rules.
- Print profiles, material choices, handoff bundles, and shop-specific checks.
- Repeated repair workflows whose facts live in that project source/docs.

When a local project skill becomes useful to multiple Flow CAD projects, promote
the generic portion into this repo's `skills/`, keep the project-specific
contract locally, and add a focused test that `flow init` copies the promoted
skill.

## CAD Interface Change Protocol

For any change involving fit, latch, slide, hook, dovetail, T-slot, receiver, rail, tongue, groove, screw alignment, or collision clearance, treat the mating interface as the unit of work.

Read `docs/PART_INTERFACES.md` before editing any mating-interface geometry. If the interface is listed there, use its fixed/moving part contract, directions, clearances, and validation notes. If the interface is not listed, add or update a concise entry when the task creates a new durable mating contract.

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

- Fixed part: `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_detachable_body.step`
- Moving part: `b3/exports/step/lower_chassis/b3_lower_chassis_rear_panel_detachable_bumpout.step`
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

Read `docs/PRINT_MANIFEST.md` before changing the intended print set, preparing a handoff, or deciding whether a STEP file is printable, reference-only, or inspection-only. Update it whenever the current print handoff intent changes.

- Any part exceeding 256mm in any dimension (256mm x 256mm x 256mm) is an automatic failure (P2S envelope limit).
- STEP files for slicing live under `b3/exports/step/`.
- Reference wheel/axle files are not printable parts.
- Assembly STEP files are for inspection, not direct printing, unless the user explicitly says otherwise.
- `.3mf` files are slicer/project artifacts. Treat them as handoff snapshots, not generated source.
- Prefer a dated print bundle and a short manifest for laptop transfer.
- Use `python scripts/create_exports_bundle.py` to create a local `handoff/*.tar.gz` bundle of the current `b3/exports/` tree. The script prints an `scp` command for copying it to `jfurr@laptop:/Users/jfurr/`.

## Files Not To Edit Directly

Do not hand-edit generated CAD artifacts:

- `b3/exports/step/**/*.step`
- `b3/exports/freecad/*.FCStd`
- `b3/exports/freecad/**/*.FCStd`
- `b3/registry.db`
- generated report files under `b3/reports/`, unless the task is explicitly documentation/report maintenance
- text-to-cad viewer sidecars such as hidden `.step` asset folders

Instead, edit the Python source or validation script that produces the artifact, regenerate, and then report what changed.

Generated STEP files are tracked, but export timestamps are intentionally normalized after generation so unchanged geometry does not churn every commit. If a STEP file still diffs after regeneration, inspect the DATA-section geometry diff before assuming it is metadata-only.

`b3/registry.db` is a generated active cache. It can be deleted and rebuilt with `flow cad build`. Do not treat cache rows as source of truth for geometry, dimensions, mating interfaces, or print handoff intent.

## Context Policy

Do not rely on historical narrative docs as project state. Inspect current source, tests, generated reports, and manifests.

For most tasks:

1. Inspect current source and reports first.
2. Read `docs/PART_INTERFACES.md` when the task touches mating geometry, fit, clearance, or hardware alignment.
3. Read `docs/PRINT_MANIFEST.md` when the task touches print handoff, Bambu Studio artifacts, printable/reference classification, or bundle contents.
4. Read `docs/CODEX_SUGGESTIONS.md` when the task concerns workflow, project structure, tests, validation, or agent/tooling improvements.
5. Preserve concise updates. Avoid creating long running narratives unless the user explicitly asks for one.

## Change Style

- Keep changes small and mechanical.
- Prefer improving the current workflow before large refactors.
- Do not move the monolithic generator until tests and validation protect the current behavior.
- Add tests/validators around existing behavior before extracting modules.
- Run `python -m pytest` for every code change.
- Preserve generated STEP handoff behavior unless the user asks to change it.
- Keep `docs/PART_INTERFACES.md` and `docs/PRINT_MANIFEST.md` current when changing durable mating contracts or print handoff intent.
- Never hardcode a coordinate in the `src/flow_cad/` generators; it must be derived from the `params: ChassisParams` object passed to the function.

## Git Hygiene

The working tree may contain user or other-agent changes.

- Do not revert unrelated changes.
- Do not delete untracked files unless the user asks.
- Treat `QWEN_SUGGESTIONS.md` and other agent-authored docs as user-visible work.
- Separate cleanup of tracked junk, generated files, or ignore rules into its own explicit change when possible.
