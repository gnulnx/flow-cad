# Gemma's Review of Phase 2: Code-First Registry + SQLite Active Cache

## Overview
Phase 2 establishes the foundation for a scalable, tool-friendly CAD pipeline by moving from ad hoc export lists to an explicit source registry. This is a critical architectural shift that enables both human and agent automation.

---

## Ticket 2.1: Python Source Registry — **VERIFIED COMPLETE**

### Analysis of `src/flow_cad/registry.py`:
- **Structure**: The use of a frozen dataclass (`PartDefinition`) with an explicit enum for roles is correct and prevents accidental runtime modification.
- **Coverage**: All major components (chassis, inserts, panels, shelves, upper module) are captured. 
- **Variant Handling**: `INSERT_VARIANTS` + factory pattern correctly handles parametric variations without duplicating registry entries manually.
- **Reference Parts**: Explicitly marked as `PartRole.REFERENCE`, which is essential for downstream filtering (e.g., not sending reference parts to a 3D printer).

### Strengths:
- Single source of truth: No more hunting through multiple files to find what should be exported.
- Type safety: `PartFactory` type alias ensures consistency across the registry.
- Extensibility: Adding new parts requires only one line in `PART_DEFINITIONS`.

---

## Ticket 2.2: Refactor Build, Bundle, and Sync — **VERIFIED COMPLETE**

### Analysis of Integration:

#### In `src/flow_cad/main.py` (Build Pipeline):
- The build loop now iterates over the registry rather than hardcoded lists.
- **Printability Check**: Integrated directly into the build flow (`assert_printable`), which is a great safety gate before export.
- **Assembly Handling**: Correctly treated as a special case via `ASSEMBLY_DEFINITION` while still using the same exporter logic.

#### In `scripts/sync_text_to_cad.py` (Viewer Sync):
- Now uses `expected_step_relative_paths()` from the registry to determine what to mirror.
- **Stale File Cleanup**: The script actively removes STEP files and sidecars that are no longer in the registry — this prevents "ghost" parts from confusing developers/agents.

#### In Bundle Creation:
- `create_bundle` now accepts `active_step_paths`, ensuring handoff bundles only contain what is currently registered.

### Strengths:
- **Consistency**: The same registry drives the build, the viewer sync, and the bundle creation. If a part is removed from the registry, it disappears everywhere automatically.
- **Decoupling**: `main.py` no longer needs to know about specific filenames; it just knows how to iterate the registry.

---

## Critical Observations & Recommendations

### 1. The "Insert" Edge Case
In `registry.py`, inserts are generated via a list comprehension:
```python
*(
    PartDefinition(f"axle_insert_{variant}", ...)
    for variant, (diameter, flat_to_flat) in INSERT_VARIANTS.items()
),
```
This is elegant but means `INSERT_VARIANTS` effectively acts as a sub-registry. If we ever need per-insert material or shell overrides, this pattern will break. I recommend keeping an eye on whether inserts diverge in print settings.

### 2. Assembly Definition Limitation
`ASSEMBLY_DEFINITION` has `factory=lambda _params: None`. This is fine for now because the assembly is built separately in `main.py`, but it creates a slight inconsistency where one registry item can't actually be "built" via its factory.

### 3. Registry-to-Manifest Drift
Phase 2 successfully makes the registry the source of truth for *what exists*. However, Phase 3 (REG-3.3) is now critical because `docs/PRINT_MANIFEST.md` still exists as a manual document. There is currently no automated check that the manifest matches the registry.

---

## Final Verdict: **PASS**

Phase 2 is cleanly implemented. The code follows the architectural decision to keep geometry in Python and use the registry as the canonical list of intended parts. This sets up Phase 3 (the SQLite cache) perfectly, as there is now a stable source to compile from.
