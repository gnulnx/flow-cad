# CAD Skills & Agent Standard Operating Procedures (SOPs)

This document is a living brainstorming repository for structured agent "Skills" (recipes, execution templates, and SOPs) designed to run seamlessly alongside the SQLModel registry and the `flow` tool suite.

---

## 1. What is an LLM "Skill"?
An **LLM Skill** is a highly descriptive, durable system recipe or process template. It outlines the exact series of research, design, coding, validation, and documentation steps necessary to successfully execute a specific category of mechanical CAD modification.

By standardizing these workflows, local models (like Gemma) do not need to guess the correct operational sequence or make logical leaps; they follow a structured roadmap.

---

## 2. Initial Skill Frameworks

### Skill A: Modifying Mating Clearances & Fits
* **When to invoke**: When adapting dovetails, sliders, T-slots, or slide receivers to fit differently.
* **Logical Pipeline**:
  ```mermaid
  graph TD
      A[Identify mating components in registry] --> B[Retrieve clearances via MCP get_mating_interface]
      B --> C[Locate parameters in params.py]
      C --> D[Modify clearance parameters]
      D --> E[Run compile & collision check]
      E --> F[Record new values in registry]
  ```
* **Step-by-Step Procedure**:
  1. **Research**: Query the registry for the target components. Locate the matching mating parameters in `PART_INTERFACES.md`.
  2. **Retrieve Baseline**: Call the database (or interface registry) to find the existing clearance value (e.g. `P.panel_dovetail_clearance`).
  3. **Modify**: Update `src/flow_cad/params.py` (or project parameters) with the new clearance target. Never hardcode coordinates inside part code.
  4. **Compile**: Execute `flow cad build` to compile the new geometry.
  5. **Intersect Verify**: Call the localized collision checking tool (`check_component_interference`) on the seated part pair. Verify that overlapping volume is precisely `0.0 mm^3`.
  6. **Document**: Update the clearances in `PART_INTERFACES.md` and log the update.

---

### Skill B: Hardware Hole & Mounting Alignment
* **When to invoke**: When changing, shifting, or adding screw mounting holes, heat-set insert bosses, or nut pockets across mating components.
* **Step-by-Step Procedure**:
  1. **Locate Axis**: Identify the structural plane (X/Y, Y/Z, X/Z) and projection axis where the fasteners align.
  2. **Lock Coordinates**: Ensure both the source component (e.g. side plate upper ledge) and destination component (e.g. center adapter deck) derive hole coordinates from the **exact same registry parameters** (e.g. `P.shelf_side_hole_x`).
  3. **Compile**: Execute the model generator to refresh all STEP models.
  4. **Align Verify**: Run the projection validation tool (`scripts/check_mounting_features.py`) to verify that circle profiles perfectly overlap along the normal mounting vector.
  5. **Check Clearances**: Ensure counterbore depth and heat-set boss wall thicknesses leave at least `1.2 mm` of printable perimeter.

---

### Skill C: Print Handoff Manifest Preparation
* **When to invoke**: When compiling structural models into sliceable Bambu Studio handoff assets.
* **Step-by-Step Procedure**:
  1. **Envelope Check**: Query component dimensions in the database. Ensure no axis exceeds the `256 mm` build envelope boundary.
  2. **Generate Bundle**: Run the bundler script to create `handoff/exports.tar.gz` and normalize timestamps.
  3. **Write Manifest**: Auto-generate `PRINT_MANIFEST.md` detailing material types (PLA vs PETG vs TPU), nozzle sizes, shell counts, and estimated filament weights.
  4. **Log State**: Output the precise shell commands and scp copy targets so the human engineer can transfer files to the printing workstation.

---

## 3. Next Steps
* After completing the SQLModel database integration (Phase 2), we will formalize these markdown files into executable CLI guidance templates that the agent loader can dynamically inject as system contexts.
