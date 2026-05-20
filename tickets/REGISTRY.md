# Project B3: Registry and Active Cache Implementation Tickets

This document defines the structured roadmap and engineering tickets for moving B3 CAD from scattered manual export lists toward an explicit code-first part registry plus a generated SQLite active cache.

The architectural decision for Phase 2 is:

- Geometry, dimensions, structural rules, and intended parts remain source-controlled Python.
- `src/flow_cad/registry.py` becomes the canonical registry of part definitions.
- `b3/registry.db` is a compiled metadata cache written by `flow cad build`, not the source of design truth.
- MCP tools, future web backends, and agent helpers may query the cache for lightweight facts such as bbox, volume, STEP path, print role, and build snapshots.
- Durable user-entered data, such as measured print mass, must not be stored only in a disposable cache unless we explicitly decide to treat the DB as persistent project state.

Why this route:

- Python source and text config are reviewable, diffable, branchable, and testable in git.
- SQLite is poor as the primary source for parametric geometry because silent DB edits can change printed parts without meaningful code review.
- A generated DB still adds value as a fast query surface for agents and tools, avoiding repeated source parsing or heavy geometry evaluation when only compiled facts are needed.
- This keeps the project ready for an MCP server or future web UI without making the database a second source of truth.

---

## Phase 1: Namespace & Directory Refactoring (B3 Overhaul)

### REG-1.1: Refactor Output Directory to Project-Root Layout
* **Goal**: Transition from flat root-level `exports/` folder to project-isolated directories.
* **Requirements**:
  * Set primary output directories relative to `b3/exports/`.
  * STEP files must export to `b3/exports/step/{module_id}/` (e.g. `b3/exports/step/lower_chassis/`, `b3/exports/step/upper_module/`).
  * FreeCAD files must export to `b3/exports/freecad/`.
  * Reports must write to `b3/reports/`.
* **Verification**:
  * Ensure the directories are generated dynamically during the build if they do not exist.
  * Update `AGENTS.md`, `README.md`, and `PRINT_MANIFEST.md` references.

### REG-1.2: Rename Geometry Filenames (Erb to B3)
* **Goal**: Clean up legibility and replace the legacy `erb_` prefix with `b3_`.
* **Requirements**:
  * Rename STEP assets: e.g. `erb_lower_chassis_left_side_plate.step` becomes `b3_lower_chassis_left_side_plate.step`.
  * Retain logical, clean names under modular subdirectories (e.g. `b3/exports/step/lower_chassis/left_side_plate.step`).
  * Switch naming registry key-values in `PART_FILENAMES` inside `src/flow_cad/main.py`.
* **Verification**:
  * Run `verify_modularization.py` (updated to point to the new paths) to guarantee **100% geometric parity** (exact volume and bounding box matching) during the renaming process.

### REG-1.3: Update Validation Scripts for the New Layout
* **Goal**: Keep auxiliary tools and validation suites functional post-refactoring.
* **Requirements**:
  * Update paths in `scripts/check_assembly_interference.py`.
  * Update paths in `scripts/check_mounting_features.py`.
  * Update paths in `scripts/check_upper_hook_geometry.py`.
  * Update paths in `scripts/sync_text_to_cad.py`.
* **Verification**:
  * Run all scripts successfully and confirm they produce clean reports in `b3/reports/`.

---

## Phase 2: Code-First Registry + SQLite Active Cache

### REG-2.1: Python Source Registry - DONE
* **Goal**: Establish the canonical, code-first mapping of intended B3 parts.
* **Requirements**:
  * Create `src/flow_cad/registry.py`.
  * Define a small explicit `PartDefinition` dataclass, with fields such as:
    * `id`
    * `module_id`
    * `filename`
    * `factory`
    * `role` (`printable`, `reference`, `inspection`, or equivalent enum)
    * `material`
    * `shell_count`
    * `infill_density`
  * Centralize all active project parts in a `REGISTRY` mapping or ordered tuple.
  * Move export intent out of `PART_FILENAMES`, `REFERENCE_FILENAMES`, and ad hoc insert loops in `src/flow_cad/main.py`.
  * Keep geometry factories and dimensions in source code; do not move CAD-generation parameters into SQLite.
* **Verification**:
  * Add tests that import `REGISTRY`.
  * Verify every registered factory can be built with `ChassisParams()`.
  * Verify every registered part has a unique id, unique export path, module id, and role.
  * Verify printable parts have print intent metadata.
* **Completed**:
  * Added `src/flow_cad/registry.py` with `PartDefinition`, `PartRole`, `PART_DEFINITIONS`, `REGISTRY`, `INSERT_VARIANTS`, and assembly export metadata.
  * Centralized active part ids, module ids, filenames, roles, material hints, and factory callables in source.
  * Added `tests/test_registry.py` coverage for unique ids/paths, required metadata, role coverage, and factory buildability.

### REG-2.2: Refactor Build, Bundle, and Sync to Use the Source Registry - DONE
* **Goal**: Make `src/flow_cad/registry.py` the single source for intended generated parts.
* **Requirements**:
  * Update `flow cad build` to iterate over registry definitions for exports.
  * Keep `build_parts()` or its replacement aligned with registry ids.
  * Update bundle and text-to-cad sync logic to derive active STEP files from registry output where practical.
  * Keep generated artifacts under `b3/exports/step/{module_id}/`.
* **Verification**:
  * Run `python -m pytest`.
  * Run `flow cad build`.
  * Run `scripts/verify_modularization.py`.
  * Confirm generated STEP filenames and module directories match the existing print handoff intent.
* **Completed**:
  * Refactored `flow cad build` to build, printability-check, and export from registry definitions.
  * Removed duplicate filename/reference/insert export lists from `src/flow_cad/main.py`; `INSERT_VARIANTS` is now re-exported from the source registry for compatibility.
  * Updated text-to-cad sync to copy registry-listed STEP files and assembly metadata instead of recursively mirroring every STEP file.
  * Added optional active STEP filtering to the bundle script while preserving non-STEP export assets.
  * Added tests for registry-derived export paths and bundle stale-STEP filtering.

### REG-2.3: SQLModel Active Cache Schema
* **Goal**: Define a generated SQLite cache of compiled CAD facts without making the DB the design source of truth.
* **Requirements**:
  * Add SQLModel only when the source registry is stable.
  * Write the cache to `b3/registry.db`.
  * Define cache tables such as:
    * `ComponentCache`: `id`, `module_id`, `role`, `step_path`, `volume_mm3`, `bbox_x`, `bbox_y`, `bbox_z`, `compiled_at`, `build_id`.
    * `BuildMetadata`: `build_id`, `git_commit`, `is_dirty`, `parameters_json`, `compiled_at`.
    * `ParameterSnapshot`: resolved `ChassisParams` values used for the successful build, keyed by `build_id`.
  * Treat these tables as rebuildable derived metadata from source and generated geometry.
  * Do not store the only copy of measured print telemetry in these cache tables.
* **Verification**:
  * Database initialization creates `b3/registry.db`.
  * Deleting `b3/registry.db` and rerunning `flow cad build` recreates the cache from source.
  * Tests verify cache rows match registry ids and generated STEP paths.

### REG-2.4: Integrate Cache Writes into `flow cad build`
* **Goal**: Make cache updates a predictable post-process of successful geometry compilation.
* **Requirements**:
  * After successful STEP export, calculate bbox and volume from in-memory build123d shapes.
  * Upsert component cache rows for all registry parts.
  * Snapshot resolved params and build metadata.
  * Fail clearly if cache writing fails, or provide an explicit `--no-cache` option if we want cache writes to be optional.
* **Verification**:
  * `flow cad build` creates or updates `b3/registry.db`.
  * Cache metrics match direct shape bbox/volume calculations in focused tests.
  * Failed builds do not publish misleading successful cache rows.

### REG-2.5: CLI and Agent Query Surface
* **Goal**: Expose lightweight compiled facts to developers, agents, and future MCP/web tooling.
* **Requirements**:
  * Add `flow registry list` to show ids, modules, roles, STEP paths, volumes, and bbox values from the active cache.
  * Add `flow registry show <component_id>` for one component.
  * Defer `flow registry weight <component_id> <grams>` until durable physical telemetry storage is designed.
  * If an MCP server is added, it should read the active cache and return small JSON payloads.
* **Verification**:
  * Commands work after `flow cad build`.
  * Commands report a clear message when `b3/registry.db` is missing or stale.
  * Query output does not require importing or evaluating heavy CAD geometry.

---

## Phase 3: Test-Driven Parity & Verification

### REG-3.2: Cache-Assisted Assembly Clearance Validators
* **Goal**: Let validators consume lightweight compiled facts without making SQLite the source of mating-interface truth.
* **Requirements**:
  * Keep durable mating-interface definitions in source/docs until a better text-config home exists.
  * Optionally mirror compiled mating-interface facts into the active cache for MCP and agent queries.
  * Refactor validation scripts to reuse the source registry and cache snapshots where doing so removes duplicated file/path logic.
* **Verification**:
  * Verify validation output matches baseline calculations.

### REG-3.3: Automatic Print Manifest Sync
* **Goal**: Generate or check `PRINT_MANIFEST.md` from source registry intent plus any approved durable print metadata.
* **Requirements**:
  * Derive printable/reference/inspection classification from `src/flow_cad/registry.py`.
  * Do not depend on disposable cache rows as the only source for handoff intent.
  * Build a synchronization or validation script that flags drift between registry intent and `docs/PRINT_MANIFEST.md`.
* **Verification**:
  * Verify generated manifest files match original baseline records.
