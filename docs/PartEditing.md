# Part Editing Plan

Date: 2026-06-07

## Purpose

Flow CAD now has the basic STEP-first geometry foundation needed for exact
snapping, measurement, display-mesh generation, and kernel-backed topology.
This plan describes how to add the first serious part-editing workflow without
turning Flow CAD into a full parametric CAD program or breaking the current
Python/project-source workflow.

The first usable goal is intentionally small:

- Put a cube on the screen.
- Select it directly in the 3D viewport.
- Translate it and resize it from viewport handles with no unrelated tool
  interference.
- Drop exact points from measurements or coordinate input.
- Select a point, choose a hole preset, and cut a through-hole.
- Add basic boolean fuse, cut, and split operations once primitive and hole
  editing are stable.

## Current Request Restated

The requested direction matches the older `docs/JOHN_VIEWER.md` product notes
and moves beyond the milestone boundary in `docs/GEOMETRY_FOUNDATION.md`.

Flow CAD should start supporting simple direct editing inside the workbench:

1. Add a cube primitive.
2. Move and resize the cube from the 3D viewport.
3. Drop a point from measurement, or type exact point coordinates.
4. Select a point and punch a standard hole through a selected part.
5. Support basic boolean operations: fuse, cut, and split.
6. Keep the workflow simple and closer to a rapid robot-design tool than a
   full FreeCAD-style parametric workbench.

## Current System Review

### Docs

- `docs/GEOMETRY_FOUNDATION.md` defines the current source hierarchy:
  Python/params are the editable source for generated project parts, STEP is
  the exact geometry authority, and STL is mesh-only.
- `docs/FlowArchitecture.md` is the earlier foundation plan. It explicitly
  deferred editable primitives, booleans, hole creation, and GUI direct
  modeling.
- `docs/measurements.txt` defines the smart tape behavior that part editing
  should reuse: exact STEP snap targets, free-space endpoints, persistent tape
  callouts, and edge-to-edge shortest-distance resolution.
- `docs/JOHN_VIEWER.md` already describes the target product shape: a cube or
  sphere at origin, viewport translate/resize handles, point dropping, M4/M5
  holes, fuse/cut buttons, delete, undo, assembled view, and visible Python
  source.
- `docs/FlowReview.md` identified viewer risks that matter more once editing
  starts: selection semantics, stale reload state, snap authority, and
  testable picking/ranking behavior.
- `docs/BLP_READINESS_WORKFLOW.md` reinforces a useful boundary: mesh metrics
  are useful, but STL mesh data is not CAD-authoritative.

### Backend

- `src/flow_cad/project.py` loads project manifests, params, part definitions,
  assembly placements, and validators. Project repos own actual CAD source.
- `src/flow_cad/main.py` builds project parts by calling registered Python
  factories, exports STEP/STL, writes reports, and updates the active cache.
- `src/flow_cad/core/exporter.py` exports build123d/OCP shapes to STEP/STL.
- `src/flow_cad/core/geometry.py` already has reusable primitive helpers such
  as boxes, cylinders, slots, and fusing.
- `src/flow_cad/viewer/geometry_authority.py` owns the current geometry
  capability model and STEP snap extraction. `exact_editing` is currently
  false for all source kinds.
- `src/flow_cad/viewer/service.py` exposes registry parts, display models,
  source context, snap features, and reload state. There are no edit document
  routes and no backend mutation path yet.
- `src/flow_cad/viewer/app.py` exposes read-oriented API routes:
  `/api/parts`, `/api/parts/{id}/model`, `/api/parts/{id}/source`,
  `/api/parts/{id}/snap-features`, and `/api/reload`.

### Frontend

- `viewer/stl-viewer/src/App.tsx` owns loaded parts, models, selected ids,
  active part id, source panel state, reload polling, color mode, and local
  metadata drafts.
- `viewer/stl-viewer/src/types.ts` defines the viewer contract. It has geometry
  capabilities and snap features, but no edit document, edit entity, operation,
  point, or boolean-result types.
- `viewer/stl-viewer/src/measurement.ts` is the best existing place to build
  from for edit anchors. It already converts backend snap features into world
  measurement targets and separates exact STEP targets from mesh fallbacks.
- `viewer/stl-viewer/src/components/Viewer.tsx` owns the R3F scene, model
  rendering, active highlighting, tape measurement, snap selection, and a small
  context menu. It has measurement state, but no edit mode or transform gizmo.
- `viewer/stl-viewer/src/components/ModelList.tsx` already separates selected
  parts from expanded part details and local metadata drafts. Editing should
  not overload this panel with every viewport operation, but it can show edit
  entities and final operation summaries later.
- `viewer/stl-viewer/src/components/Toolbar.tsx` is the natural place for
  explicit mode controls: Select, Cube, Move/Resize, Point, Hole, Fuse, Cut,
  Split.

### Tests

- `tests/test_viewer_service.py` already covers viewer contracts, source
  context, route registration, STEP-vs-STL authority, display-mesh cache
  metadata, and snap feature extraction.
- `viewer/stl-viewer/src/measurement.test.ts` covers measurement math and
  exact-vs-mesh snap feature selection.
- `viewer/stl-viewer/src/components/Viewer.behavior.test.ts` covers pure viewer
  behavior helpers such as snap scoring, tape resolve mode, and label dragging.
- `viewer/stl-viewer/src/App.test.tsx` covers backend payload wiring, revision
  changes, exact snap-feature passing, and mesh-only warnings.

The current test shape is good. Editing should add backend contract tests and
pure frontend interaction tests before depending on manual viewport testing.

## Design Principles

1. STEP and OCP stay authoritative.
   STL can be viewed and measured approximately, but STL must not become the
   source for exact editing, holes, booleans, or coordinates.

2. GUI edits are an operation graph, not hand-edited exports.
   Generated `exports/` files remain outputs. Editing should change a project
   source document, then rebuild or preview generated artifacts from that
   document.

3. Python source remains first-class.
   Project Python factories and params still own generated robot parts. GUI
   editing should not silently rewrite Python. For Python-backed parts, the
   first editable model is an overlay or working-copy operation graph applied
   after the Python factory produces a base shape.

4. Editing must be mode-isolated.
   When the user is dragging a cube, resize handle, point, or hole control,
   orbit, tape, part-list activation, source selection, and context-menu actions
   should not steal the gesture.

5. Edit operations must be small and undoable.
   Each operation should have an id, input refs, output refs, timestamp, and a
   clear undo behavior. Avoid giant "current shape blob" state where possible.

6. The first version should be useful before it is broad.
   Cube, move, resize, point, hole, fuse, cut, and simple split are enough for a
   first serious editing workflow. Sketching, fillets, patterns, constraints,
   advanced topology naming, and automatic Python rewriting are out of scope.

## Proposed Architecture

Add a reusable edit subsystem under `src/flow_cad/editing/`.

Suggested modules:

- `models.py`: dataclasses or pydantic-compatible schemas for edit documents,
  entities, anchors, operations, tool presets, and revisions.
- `document.py`: load, validate, migrate, save, and append operations to a
  project-local Flow document.
- `kernel.py`: build123d/OCP operation application for primitives, transforms,
  holes, booleans, split, bounding boxes, and display mesh regeneration.
- `service.py`: viewer-facing edit service that wraps document and kernel logic.
- `presets.py`: generic hole presets such as M4 clearance, M5 clearance, and
  later counterbore or heat-set variants.

The viewer API should compose this edit service into `ViewerService` instead
of making the React app generate or mutate authoritative CAD.

## Project Storage Model

Use two storage layers:

1. Saved source document:
   `flow/flow_document.json`

   This is project-owned source, not generated state. It can be committed and
   reviewed like Python part source.

2. Local draft/session state:
   `.flow/edit-sessions/<session-id>.json`

   This stores unsaved local viewport drafts, active tool state, and undo/redo
   stacks if the user has not saved. It should remain ignored local state.

Generated edited STEP/STL outputs should still live under `exports/`, and
preview/display meshes should still live under `.flow/viewer-cache/`.

Open decision: the exact saved source path can change, but it should not live
only under `.flow/` if the edit changes are expected to survive rebuilds,
commits, and project handoff.

## Edit Document Shape

The document should stay explicit and boring. A rough V1 shape:

```json
{
  "schema_version": 1,
  "document_id": "main",
  "units": "mm",
  "revision": 7,
  "entities": {
    "box_001": {
      "kind": "primitive_box",
      "name": "box_001",
      "size_mm": [20.0, 20.0, 20.0],
      "transform": {
        "translation_mm": [0.0, 0.0, 10.0],
        "rotation_deg": [0.0, 0.0, 0.0]
      },
      "role": "inspection"
    },
    "wheel_box_test_body_working": {
      "kind": "python_part_working_copy",
      "base_part_id": "wheel_box_test_body",
      "role": "printable"
    }
  },
  "points": {
    "point_001": {
      "position_mm": [45.0, 0.0, 12.0],
      "coordinate_space": "world",
      "source": {
        "kind": "measurement",
        "label": "Line Edge -> Free Point"
      }
    }
  },
  "operations": [
    {
      "id": "op_001",
      "type": "create_box",
      "entity_id": "box_001"
    },
    {
      "id": "op_002",
      "type": "cut_hole",
      "target_entity_id": "wheel_box_test_body_working",
      "point_id": "point_001",
      "preset": "m4_clearance",
      "axis": [0.0, 0.0, 1.0],
      "through": true
    }
  ]
}
```

Important constraints:

- The operation graph stores exact dimensions and transforms in millimeters.
- Points can be world-space in V1. Later, model-bound local coordinates can
  keep points stable through part transforms.
- Python-backed part edits use a working-copy entity. They do not rewrite the
  Python function unless a future explicit "generate source patch" workflow is
  added.
- Role defaults should be conservative. A new cube can start as `inspection`
  until the user marks it printable or fuses it into a printable parent.

## Geometry Capability Changes

Extend the geometry authority model to distinguish editable exact document
geometry from read-only exact Python/STEP geometry.

Likely additions:

- `source_kind`: add `flow_document` and possibly `flow_python_with_edits`.
- `capabilities.exact_editing`: true only for entities with an edit-document
  source or working-copy overlay.
- `capabilities.direct_modeling`: optional future flag if useful.
- `warnings`: keep warning when an STL-only part is selected for a hole or
  boolean operation.

The viewer should refuse exact edit tools for `mesh_only` geometry.

## Backend API Sketch

Add edit routes under `/api/edit`.

Suggested V1 routes:

- `GET /api/edit/status`
  Returns whether editing is available, document path, document revision,
  active session id, undo/redo availability, and generic tool presets.

- `GET /api/edit/document`
  Returns the normalized edit document and current entities.

- `POST /api/edit/operations`
  Appends one operation, rebuilds affected entities, bumps document revision,
  and returns changed model descriptors.

- `PATCH /api/edit/entities/{entity_id}`
  Applies a simple transform, resize, rename, or role update. This can be
  represented internally as an appended operation.

- `POST /api/edit/points`
  Creates a persistent point from measured coordinates or typed coordinates.

- `PATCH /api/edit/points/{point_id}`
  Updates exact coordinates.

- `POST /api/edit/holes`
  Convenience route that appends a `cut_hole` operation from target entity,
  point, preset, and axis.

- `POST /api/edit/booleans`
  Appends `fuse`, `cut`, or `split` operation.

- `POST /api/edit/undo`
  Reverts the last operation in the active edit session or document.

- `POST /api/edit/redo`
  Reapplies the next reverted operation.

The API should return enough data for the frontend to update only changed
models, but the first version can reload viewer state after every accepted edit
if that is simpler and reliable.

## Kernel Operation Model

V1 operations should wrap build123d/OCP primitives and booleans:

- `create_box(size_mm, transform)`
  Creates an axis-aligned box in local coordinates.

- `set_transform(entity_id, translation_mm, rotation_deg)`
  Moves an entity or working copy.

- `resize_box(entity_id, size_mm, anchor)`
  Changes box dimensions. `anchor` controls whether resizing happens from the
  center, from one face, or from a selected handle.

- `create_point(position_mm, coordinate_space, source)`
  Creates a selectable edit anchor.

- `cut_hole(target_entity_id, point_id, preset, axis, through=true)`
  Subtracts a cylinder from the target. Through length should come from the
  target bounding box plus safe margin, not from a hardcoded magic depth.

- `fuse(target_entity_id, tool_entity_id)`
  Unions the tool into the target and optionally hides or consumes the tool.

- `cut(target_entity_id, tool_entity_id)`
  Subtracts the tool from the target and keeps the tool visible or hidden based
  on the command option.

- `split(target_entity_id, tool_entity_id | plane)`
  Produces two or more resulting entities. Split should wait until create,
  transform, resize, hole, fuse, and cut are stable because result identity and
  naming are harder.

Hole preset examples:

```json
{
  "m4_clearance": {
    "label": "M4 clearance",
    "diameter_mm": 4.5
  },
  "m5_clearance": {
    "label": "M5 clearance",
    "diameter_mm": 5.5
  }
}
```

Counterbore, countersink, and heat-set insert profiles can be added after the
basic through-hole path is proven.

## Frontend Editing Model

Add explicit edit state in `App.tsx` or a new `editing/` frontend module:

- `editMode`: `off | select | cube | move_resize | point | hole | boolean`.
- `activeEditEntityId`.
- `activePointId`.
- `editDocumentRevision`.
- `pendingOperation`.
- `undoRedoState`.

Add scene-level components:

- `EditLayer`
  Owns edit entity overlays, selectable points, active gizmo, and operation
  previews.

- `BoxEditGizmo`
  Draws axis handles and resize handles. It should stop propagation and disable
  camera controls while dragging.

- `PointLayer`
  Draws persistent points, selected point highlight, and coordinate labels.

- `HolePreview`
  Draws the through-hole cylinder preview, axis, preset label, and target part.

- `BooleanPreview`
  Highlights target and tool bodies before applying fuse, cut, or split.

Keep this separate from measurement rendering. Measurement can create point
inputs, but the point tool owns saved edit points.

## Viewport Interaction Contract

### Add Cube

1. User selects the Cube tool.
2. Backend creates `box_001` with a default size such as `20 x 20 x 20 mm`.
3. The cube appears at the origin or active cursor plane.
4. The cube is selected and immediately shows transform/resize handles.
5. Toolbar switches to Move/Resize for the cube.

### Move And Resize Cube

1. Drag center handle: translate freely on the camera-facing plane.
2. Drag axis midpoint handle: translate along that axis only.
3. Drag axis end handle: resize along that axis.
4. Coordinate panel shows exact center and size values.
5. Releasing the drag sends one operation or patch to the backend.
6. During the drag, camera orbit, tape, context menu, and part activation are
   disabled.

### Drop Point From Measurement

1. User measures from an exact snap target to a location.
2. User chooses "Drop Point" from the measurement HUD or point tool.
3. The point is created at the measured endpoint.
4. The point becomes selectable and appears in the edit point list.
5. Coordinate fields allow exact X/Y/Z override.

### Create Hole Through Point

1. User selects a target exact-editable part or working copy.
2. User selects a point.
3. User chooses hole preset: M4 clearance or M5 clearance for V1.
4. User chooses axis if the point does not carry a face normal.
5. Viewer shows a cylinder preview through the target.
6. Apply sends a `cut_hole` operation to the backend.
7. Backend rebuilds the target shape, exports or caches a fresh display mesh,
   extracts fresh snap features, bumps revision, and returns the updated model.

### Fuse, Cut, Split

1. User selects a target body and one tool body.
2. Toolbar enables Fuse, Cut, and Split only when both bodies are exact-editable
   or kernel-backed working copies.
3. Fuse consumes or hides the tool after union.
4. Cut subtracts the tool and keeps tool visibility as an option.
5. Split starts with plane or box-cutter split. The operation should produce
   explicit new entity ids so undo and part list state are predictable.

## Milestone Plan

### Milestone 0: Editing Readiness

Goal: remove known interaction ambiguity before adding direct manipulation.

Tasks:

- Clarify `selectedIds` vs `activeName` semantics in frontend state names or
  docs before edit tools depend on them.
- Extract snap picking/ranking into a pure tested module if edit-point picking
  will reuse it.
- Add edit capability flags to backend/frontend types with tests that STL-only
  parts cannot enter exact edit mode.
- Decide saved edit document path and draft-session behavior.

Exit criteria:

- Exact STEP snap targets remain authoritative.
- Mesh-only files show edit-disabled warnings.
- The code has a clear `activePartId`, visible selection, and edit selection
  boundary.

### Milestone 1: Edit Document And Backend Preview

Goal: make a backend-created cube real, exact, reloadable, and testable.

Tasks:

- Add `src/flow_cad/editing/` document models and loader.
- Add default empty document creation for projects.
- Add `/api/edit/status`, `/api/edit/document`, and
  `/api/edit/operations`.
- Implement `create_box` in the kernel service.
- Generate a display mesh for edit entities through the existing STEP-to-STL
  display path.
- Surface edit entities in `/api/parts` or a compatible viewer payload.

Exit criteria:

- A test can create a box operation, reload the document, and verify exact
  bounding-box dimensions.
- The viewer can load the created cube as a normal exact part.
- Rebuild/reload does not lose the saved cube.

### Milestone 2: Viewport Cube Move/Resize

Goal: satisfy the first visible workflow: put a cube on screen and manipulate it
from the 3D viewport with no unrelated interference.

Tasks:

- Add toolbar modes for Cube and Move/Resize.
- Add `EditLayer` and `BoxEditGizmo`.
- Disable camera controls and measurement while an edit handle is dragging.
- Add exact numeric fields for cube center and size.
- Send one backend operation per completed drag.
- Add undo for create, transform, and resize.

Exit criteria:

- User can add, select, move, and resize a cube without opening source or
  editing Python.
- The cube survives reload after save.
- Delete removes the cube; undo restores it.

### Milestone 3: Persistent Points

Goal: turn measurement endpoints into editable CAD anchors.

Tasks:

- Add edit point schemas, backend routes, and frontend point layer.
- Add "Drop Point" to the measurement HUD or point tool.
- Add coordinate input for selected point X/Y/Z.
- Store point provenance when created from exact snap or measurement.
- Keep point display separate from tape annotations.

Exit criteria:

- User can measure, drop a point, type exact coordinates, select the point, and
  reload without losing it.
- Points created from STEP snaps are marked exact.
- Points created from mesh-only geometry are marked approximate and cannot drive
  exact hole cutting without confirmation or conversion.

### Milestone 4: Through Holes

Goal: select a point and punch a standard through-hole in an exact target.

Tasks:

- Add generic M4/M5 clearance presets.
- Add target part selection and hole axis selection.
- Implement `cut_hole` using a cylinder through the target bounding box plus
  margin.
- Re-extract snap features after hole creation.
- Add backend tests that prove holes are truly through the target.

Exit criteria:

- User can select target, point, M4/M5 preset, and apply.
- Updated model shows a visible through-hole.
- Exact snap features refresh after the operation.
- STL-only targets are rejected with a clear warning.

### Milestone 5: Boolean Fuse And Cut

Goal: support the first real body-to-body operations.

Tasks:

- Add target/tool selection state.
- Add Fuse and Cut toolbar buttons.
- Implement backend `fuse` and `cut` operations.
- Decide whether consumed tool bodies are hidden, deleted, or retained as
  construction geometry.
- Add volume/bounds tests for simple cube fuse and cube cut.

Exit criteria:

- Two cubes can be fused into one target body.
- One cube can cut another.
- Undo restores the previous target/tool state.

### Milestone 6: Basic Split

Goal: add split only after identity and undo behavior are stable.

Tasks:

- Start with a simple split by plane or box cutter.
- Generate explicit result entity ids such as `body_a` and `body_b`.
- Add UI for choosing which resulting bodies to keep.
- Add tests for result counts, bounding boxes, and undo.

Exit criteria:

- Split produces selectable resulting bodies with predictable ids.
- Undo returns to the pre-split body.

### Milestone 7: Build And Export Integration

Goal: make edits part of normal Flow CAD project outputs.

Tasks:

- Update `flow cad build` to apply saved edit documents after Python base
  shapes are created and before export/cache/report generation.
- Ensure edited outputs use the same exporter and report paths as generated
  parts.
- Add manifest/project-loader tests for projects with and without edit docs.
- Add docs for downstream projects: when edits are source, when they are local
  drafts, and how to review them.

Exit criteria:

- `flow cad build` produces the edited STEP/STL outputs from saved document
  source.
- No generated output is hand-edited.
- Downstream projects can opt into GUI edits without putting product-specific
  geometry facts in this repo.

## Testing Strategy

Backend tests:

- Empty edit document loads and validates.
- `create_box` creates exact expected dimensions.
- `set_transform` and `resize_box` update bounding boxes predictably.
- `cut_hole` creates a through feature at the requested point and axis.
- Fuse and cut change volume/bounds as expected for simple boxes.
- Split returns stable result ids.
- STL-only parts are rejected for exact edit operations.
- API routes bump document revision and viewer revision.

Frontend tests:

- Toolbar modes are mutually exclusive.
- Edit dragging disables measurement and camera controls.
- Exact edit-disabled warnings appear for mesh-only models.
- Add cube sends the expected operation payload.
- Coordinate input patches point or box values without changing unrelated state.
- Undo/redo buttons follow backend state.

Manual/live checks before calling implementation done:

- Start `flow start` in a real project.
- Add a cube, drag it, resize it, reload, and confirm it persists.
- Drop a point from a measurement and type exact coordinates.
- Cut M4 and M5 through-holes and visually inspect that they pass through.
- Reinstall editable Flow CAD in a downstream project before verifying project
  behavior.

## Risks

- Topological naming after booleans can become complex. V1 should avoid
  promising stable face/edge identities after every edit.
- Split operation identity is harder than fuse/cut. It should not block cube,
  point, and hole editing.
- Rewriting Python source from GUI operations is tempting but should be a later
  explicit workflow. Silent source rewriting would create hard-to-review
  project changes.
- If edit state lives only in `.flow/`, users will lose serious design work
  during handoff. Saved edits need a project-source path.
- If the viewer mutates display meshes for speed, exact measurements and holes
  will drift from the real kernel shape. All authoritative edits must round-trip
  through backend kernel geometry.

## Open Decisions For Review

1. Should the saved edit source path be `flow/flow_document.json`,
   `flow/editing/document.json`, or configured in `flowcad.project.yaml`?

2. When editing a Python-generated part, should Flow CAD create a visible
   working-copy entity by default, or should it apply an overlay directly to the
   existing part id?

3. Should a new cube default to `inspection`, `reference`, or `printable`?

4. For a point that is not on a face, should hole axis default to global Z,
   camera direction, or a required toolbar axis choice?

5. Should boolean cut keep the tool body visible as construction geometry, hide
   it, or consume/delete it by default?

6. Should split V1 be plane-only, tool-body split, or both?

7. Should undo/redo be saved in the document history, local session history, or
   both?

## Recommended First Implementation Slice

Build the smallest real slice that proves the architecture:

1. Add an edit document loader/saver and `create_box` backend operation.
2. Expose edit entities to the viewer as exact kernel-backed models.
3. Add Cube and Move/Resize modes with a simple box gizmo.
4. Save the cube operation to project source and prove reload persistence.
5. Add backend and frontend tests for the contract.

Only after that slice works should point/hole and boolean operations be added.
