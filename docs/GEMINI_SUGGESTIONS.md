# Erb CAD Project: Gemini's Modernization & Efficiency Strategy

Generated: 2026-05-19

## Executive Summary

The Erb CAD project has made significant strides in moving from "Vibe Coding" to "Engineering CAD." The extraction of `params.py`, the creation of `AGENTS.md`, and the formalization of the `PRINT_MANIFEST.md` have provided much-needed guardrails.

However, the project is currently hitting a **"Context Ceiling."** The 1,879-line monolithic generator in `cad/erb_lower_chassis.py` is now the primary bottleneck for both human developers and AI agents. Every modification requires re-parsing a massive context, making sessions expensive and error-prone.

The next evolution must focus on **Component-Oriented CAD (CO-CAD)** and **Sim2Real Alignment**.

---

## 1. The Monolith Crisis: Breaking the Context Ceiling

The current 1,879-line `erb_lower_chassis.py` is too large for efficient agentic workflows. When an agent needs to change a single shelf relief, it shouldn't have to reason through the dovetail logic of the rear panel.

### The Move: `erb_cad/` Package
I suggest migrating to a modular package structure immediately. This isn't just for "clean code"—it's for **Agent Productivity**.

```text
erb_cad/
├── __init__.py
├── params.py              # (Already done - good job!)
├── registry.py            # Central mapping of part names to factory functions
├── parts/
│   ├── side_plate.py      # make_side_plate()
│   ├── bottom_tray.py     # make_bottom_tray()
│   ├── shelves.py         # all make_shelf_* variants
│   ├── panels.py          # front/rear/detachable panel logic
│   └── inserts.py         # axle insert variants
└── core/
    ├── builder.py         # High-level assembly & export logic
    └── validation.py      # Importable geometric invariant checks
```

**Immediate Benefit:** An agent can be told to "fix the shelf" and only load `params.py` and `parts/shelves.py`. This reduces token usage by ~70% per turn.

---

## 2. Registry-Driven Workflow

Stop maintaining hardcoded lists in `sync_text_to_cad.py`, `PRINT_MANIFEST.md`, and the generator itself.

### The Move: The Authoritative Part Registry
Create a central `registry.py` that defines what a "part" is.

```python
# erb_cad/registry.py
@dataclass
class PartDefinition:
    name: str
    factory: Callable
    is_printable: bool = True
    is_reference: bool = False
    material_hint: str = "PETG"

REGISTRY = {
    "left_side_plate": PartDefinition(name="left_side_plate", factory=make_side_plate),
    ...
}
```

**Outcome:** `sync_text_to_cad.py` and `scripts/create_exports_bundle.py` can simply iterate over the registry. If a part isn't in the registry, it doesn't exist to the toolchain.

---

## 3. "Vibe" Validation: Visual Regression Snapshots

Currently, "vibing" a change requires generating a STEP file and opening a viewer. This is too slow.

### The Move: Automatic Orthographic Previews
Modify the export pipeline to generate 2D snapshots (SVG or PNG) of the X/Y, Y/Z, and X/Z planes for every part.

**Outcome:** An agent can generate a change and the user can immediately see a thumbnail in the file explorer (or a diff of the SVG) to confirm the "vibe" before committing to a full print.

---

## 4. Sim2Real Alignment (Dojo V2)

The project memories mention `Dojo V2` URDF support limits. The CAD project should be the "Master of Reality."

### The Move: URDF Fragment Generation
Since `params.py` already contains the ground truth for bounding boxes and axle centers, add a utility to `erb_cad/core/` that generates URDF `<link>` and `<joint>` snippets.

**Goal:** When you change `P.axle_center_height_from_bottom`, the simulation's collision box and joint origin should update automatically. This prevents the "It works in Sim but the real motor doesn't fit" failure mode.

---

## 5. Immediate Technical Debt "Paper-Cuts"

1. **`sys.path` Hacks:** Remove the `sys.path.insert` calls in `erb_lower_chassis.py`. Use a proper `pip install -e .` (editable install) for the `erb_cad` package.
2. **Normalized Exports:** The `normalize_step_file` utility is great. Ensure it's run as a post-process for *every* export to keep git diffs clean from metadata noise.
3. **Validation as CI:** Move `scripts/validate_all.py` to a GitHub Action. No PR should be merged if `check_assembly_interference.py` reports a collision.

---

## Summary of Priorities

| Priority | Task | Why? |
| :--- | :--- | :--- |
| 🔴 **Critical** | **Modularize Parts** | Fixes the Context Crisis; enables faster agent turns. |
| 🟠 **High** | **Part Registry** | Eliminates duplicate lists and "missing file" bugs. |
| 🟡 **Medium** | **URDF Sync** | Connects CAD to Dojo V2 simulation (Sim2Real). |
| 🔵 **Low** | **Visual Snapshots** | Speeds up "vibe" checks for human-in-the-loop review. |

---
*Gemini 3.5 Flash (High) | May 19, 2026*
