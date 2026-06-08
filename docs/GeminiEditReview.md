# Principal Engineer Review: Flow CAD Simple Editing Plan

**Review Date:** 2026-06-07  
**Reviewer:** Principal Engineer (AI Cohort)  
**Status:** Approved with architectural adjustments  
**Target Document:** [docs/PartEditing.md](file:///home/gnulnx/flow-cad/docs/PartEditing.md)  
**Related Architecture Docs:**
- [docs/GEOMETRY_FOUNDATION.md](file:///home/gnulnx/flow-cad/docs/GEOMETRY_FOUNDATION.md)
- [docs/FlowArchitecture.md](file:///home/gnulnx/flow-cad/docs/FlowArchitecture.md)
- [docs/FlowReview.md](file:///home/gnulnx/flow-cad/docs/FlowReview.md)
- [docs/JOHN_VIEWER.md](file:///home/gnulnx/flow-cad/docs/JOHN_VIEWER.md)

---

## 1. Executive Summary

The proposed part editing plan in [docs/PartEditing.md](file:///home/gnulnx/flow-cad/docs/PartEditing.md) is **architecturally sound, pragmatic, and highly aligned** with the project's design philosophy. By utilizing a serialized JSON operation graph overlay rather than attempting to build a fully parametric CAD system or a heavy constraint solver, the plan keeps Flow CAD lightweight, portable, and "CAD-as-code" focused.

However, several critical engineering boundaries must be strictly enforced during implementation to prevent regression, interaction latency, and coordinate drift. 

### PE Recommendation
**Proceed to implementation with a focus on Milestone 0 and 1 immediately.** The plan is sound to execute, provided that the architectural corrections outlined in this review are adopted.

---

## 2. Core Architecture & Design Analysis

### 2.1. The Python/JSON Source Boundary
Flow CAD's core strength is that Python is the authoritative source of geometry. Introducing a JSON operation graph ([flow/flow_document.json](file:///home/gnulnx/flow-cad/docs/PartEditing.md#L173)) introduces a hybrid source model. 
*   **The Hazard:** If the JSON document overrides or modifies base Python parts inline, we risk silent cache mismatch, complex merge conflicts, and code-sync drift.
*   **The Fix:** We must treat Python parts as read-only base layers. The JSON document must store edits as **additive overlays** or **derived child entities** (e.g., `part_id_working`) that consume the base STEP export and apply kernel-level operations. Under no circumstances should the backend write or modify Python source files (`.py`) automatically.

### 2.2. The Topological Naming Problem
The plan notes that topological naming after booleans is out of scope for V1. This is a very wise constraint.
*   **The Hazard:** If a user places a hole relative to "Face 3" of a box, and a later change in the Python source splits or alters that box (generating 5 faces instead of 6), the face index will shift, causing the hole to appear in the wrong place or fail to compile.
*   **The PE Constraint:** V1 must strictly operate on **absolute coordinate placements** within the target part's local coordinate space, or using project-wide exact [SnapFeature](file:///home/gnulnx/flow-cad/src/flow_cad/viewer/geometry_authority.py#L25) points projected into coordinates. Edits must not reference topological sub-element IDs (face indices, edge loops) of Python-generated parts.

### 2.3. Viewport Performance and Commits
*   **The Hazard:** Rebuilding the BRep kernel using `build123d`/OCP and regenerating STL display meshes on every mouse-move event during a drag gesture will choke the viewer and degrade performance.
*   **The PE Constraint:** The frontend must perform *purely local, lightweight Three.js matrix transforms* on the display mesh during drag operations in [viewer/stl-viewer/src/components/Viewer.tsx](file:///home/gnulnx/flow-cad/viewer/stl-viewer/src/components/Viewer.tsx). Only on `pointerup` (mouse release) should the final parameters be committed via a `POST` or `PATCH` request to the backend service.

---

## 3. Resolution of Open Decisions

To ensure clean implementation, we resolve the seven open decisions outlined in [docs/PartEditing.md](file:///home/gnulnx/flow-cad/docs/PartEditing.md#L660) as follows:

### 1. Saved Edit Source Path
*   **Recommendation:** Default to `flow/document.json`.
*   **Rationale:** Placing this under the `flow/` source directory keeps the JSON operation graph alongside `flow/params.py` and the registry, indicating it is version-controlled source code. Allowing customization in [flowcad.project.yaml](file:///home/gnulnx/flow-cad/src/flow_cad/project.py#L18) is acceptable but optional.

### 2. Working-Copy Entity vs. Direct Overlay
*   **Recommendation:** Explicit working-copy entities (e.g., `base_part_id_working`).
*   **Rationale:** Mutating the original part definition ID in-place creates severe cache invalidation challenges. By defining a working-copy wrapper, the base part remains intact in the registry [src/flow_cad/project.py](file:///home/gnulnx/flow-cad/src/flow_cad/project.py), allowing it to be used for reference, comparison, or in other assemblies without the edits applied.

### 3. New Cube Role Default
*   **Recommendation:** `reference` or `inspection`.
*   **Rationale:** Primitives added via the viewer must not default to `printable` to prevent accidental inclusion in automated print bundlers or reports until the user has explicitly declared their intent or fused them into a parent printable part.

### 4. Hole Axis for Free Points
*   **Recommendation:** Default to the parent part's local Z-axis, with toolbar overrides.
*   **Rationale:** Free points do not have face normal vectors. Defaulting to camera direction is highly dynamic and unpredictable, leading to misalignment. A static default (Z-axis) paired with an explicit toolbar selector (X, Y, Z) is robust and matches standard engineering workflows.

### 5. Boolean Cut Tool Body Retention
*   **Recommendation:** Keep the tool body, but switch its role to `construction` or `hidden_tool`.
*   **Rationale:** Deleting the tool body breaks parameters if the user wants to adjust the cut dimensions later. Hiding it by default in the assembly view keeps the viewport clean while maintaining the integrity of the operation graph.

### 6. Split V1 Scope
*   **Recommendation:** Plane-only splits.
*   **Rationale:** Tool-body splitting introduces complex multi-body management, naming, and result tracking (e.g., deciding which split half is deleted, kept, or renamed). Plane-only splits are mathematically simple and cover 90% of rapid prototyping needs.

### 7. Undo/Redo History Location
*   **Recommendation:** Local session history only.
*   **Rationale:** Keep the undo/redo stack in the browser state or in `.flow/edit-sessions/`. Saving undo history to `flow/document.json` would bloat version control with intermediate edit drafts.

---

## 4. Milestone Critique & Enhancements

The proposed milestone plan is logical, but we recommend adding the following enhancements:

### Milestone 0: Editing Readiness
*   **Critical Fix:** We must address the selection ambiguity identified in [docs/FlowReview.md](file:///home/gnulnx/flow-cad/docs/FlowReview.md#L114). Clean up `selectedIds` vs `activeName` semantics in [viewer/stl-viewer/src/App.tsx](file:///home/gnulnx/flow-cad/viewer/stl-viewer/src/App.tsx) so the viewport and model list behave consistently before edit states are layered on top.

### Milestone 3: Persistent Points
*   **Critical Fix:** Ensure that when a point is dropped from an STL mesh-only model, it is marked as `approximate` in [PartGeometry](file:///home/gnulnx/flow-cad/src/flow_cad/viewer/geometry_authority.py#L34). The UI must warn the user if they try to align a precise clearance hole (M4/M5) to an approximate point.

### Milestone 7: Build Integration
*   **Critical Fix:** The headless CLI build pipeline [src/flow_cad/main.py](file:///home/gnulnx/flow-cad/src/flow_cad/main.py) must be able to load `flow/document.json` and apply the edit graph *without* requiring the fast-api server [src/flow_cad/viewer/app.py](file:///home/gnulnx/flow-cad/src/flow_cad/viewer/app.py) or browser to be active.

---

## 5. Technical Risk Matrix

| Risk | Impact | Likelihood | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **Topological Drift** | High | High | Restrict point references to coordinates relative to the component's local frame. Avoid face/edge index linkage. |
| **OCP Kernel Latency** | Med | High | Throttle edit requests. Run local matrix translations in Three.js during mouse drag; compile BRep on mouse-release (`pointerup`). |
| **Stale Snap Features** | High | Med | Invalidate and rebuild cache when `flow/document.json` revision bumps, exactly matching the cache metadata checks in [ViewerService.snap_features](file:///home/gnulnx/flow-cad/src/flow_cad/viewer/service.py#L188). |
| **Mesh-Only Editing** | Med | Med | Reject boolean operations and cuts on STL-only parts. Require STEP representation for exact boolean operations. |
