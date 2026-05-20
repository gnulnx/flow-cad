# Project B3: Registry Implementation Tickets

This document defines the structured roadmap and engineering tickets to transition B3 CAD from a manual manifest configuration to a SQLite-driven SQLModel part registry.

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
  * Switch naming registry key-values in `PART_FILENAMES` inside `erb_cad/main.py`.
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

## Phase 2: SQLModel Core Modeling & Database Integration

### REG-2.1: Establish SQLModel Schema & Tables
* **Goal**: Define the data models for projects, modules, components, and print specs.
* **Requirements**:
  * Create `erb_cad/core/registry.py`.
  * Define `Project` class: `id` (PK, "b3"), `name`, `description`.
  * Define `Component` class: `id` (PK), `project_id` (FK), `module`, `name`, `step_path`, `volume_mm3`, `bbox_x`, `bbox_y`, `bbox_z`.
  * Define `PrintSpecification` class: `id` (PK), `component_id` (FK), `material` (PLA/TPU/PETG), `infill_density`, `shell_count`, `nozzle_diameter`, `weight_actual_g` (measured physical mass).
* **Verification**:
  * Write SQLite table generation logic (`SQLModel.metadata.create_all()`).

### REG-2.2: Add CLI Interface for Registry Management
* **Goal**: Expose database operations via the `flow` CLI.
* **Requirements**:
  * Add click command: `flow project init <project_id> --name <name> --desc <desc>`.
  * Add click command: `flow registry list` (displays a rich-styled table of registered components, materials, and volumes).
  * Add click command: `flow registry weight <component_id> <weight_in_grams>` (allows physical print telemetry to be entered directly).
* **Verification**:
  * Command line execution checks via local environment.

### REG-2.3: Integrate Registry Writes into the CAD Build Pipeline
* **Goal**: Automatically update database records on successful geometry compilation.
* **Requirements**:
  * Integrate database sessions into `flow cad build`.
  * On run, calculate geometry statistics (volume, bounding box) in memory for all constructed `build123d` parts.
  * Upsert records in the `Component` table to match the current successful design state.
* **Verification**:
  * Confirm database file `b3/registry.db` is created/updated upon running `flow cad build`.

---

## Phase 3: Test-Driven Parity & Verification

### REG-3.2: DB-Backed Assembly Clearance Validators
* **Goal**: Convert file-based validation checks into database-driven checks.
* **Requirements**:
  * Define a `MatingInterface` relational table mapping component pairs and design clearances (e.g. `dovetail_clearance = 0.15`).
  * Refactor validation scripts to query the SQLite registry for target clearances instead of hardcoding python lists.
* **Verification**:
  * Verify validation output matches baseline calculations.

### REG-3.3: Automatic Print Manifest Sync
* **Goal**: Auto-generate `PRINT_MANIFEST.md` directly from the database.
* **Requirements**:
  * Build a synchronization script that translates registered `PrintSpecification` records into markdown files for slicer handoff.
* **Verification**:
  * Verify generated manifest files match original baseline records.
