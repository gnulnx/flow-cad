# Flow CAD Viewer Foundation Review

Date: 2026-05-30

Scope: source-backed viewer API in `src/flow_cad/viewer/`, React/Three viewer in `viewer/stl-viewer/`, legacy standalone viewer/scripts where they affect workflow clarity, and the current measurement/selection foundation.

## Executive Summary

The viewer has a workable architecture: a Python service owns project registry, exports, source lookup, STEP conversion, and STEP snap extraction; the React client owns STL display, part visibility, source panel state, camera controls, and measurement annotations.

The weak foundation is that measurement and selection logic cross three different geometry truths without an explicit contract:

- STEP topology features from the backend.
- STL/render mesh features generated in the browser.
- Session-only measurement annotations stored as world coordinates.

That split is the main cause of flaky measurements. The most important fix is to choose the authoritative snap source per part and make stale geometry impossible after reload. Do that before adding more editing tools.

## Priority Findings

### 1. STEP edge and vertex snap data is generated, then discarded in the viewer

Severity: High

Evidence:

- Backend extracts STEP `vertex`, `line_edge`, `edge_midpoint`, and `circle_center` features in `src/flow_cad/viewer/service.py:139-204`.
- Frontend keeps only STEP `circle_center` features, then appends browser-generated mesh features in `viewer/stl-viewer/src/components/Viewer.tsx:286-291`.

Impact:

STEP-backed parts are expected to get precise semantic snapping, but edge and vertex snapping actually comes from `EdgesGeometry` on the tessellated STL. That means edge/vertex snaps depend on mesh tessellation, STL export tolerances, hard feature-angle filtering, and rounding. This directly undermines measurement trust.

Recommendation:

For STEP-backed registry parts, use backend snap features as the authoritative set for all supported feature kinds. Only use `buildMeshSnapFeatures()` when backend features are missing or the model is a dropped STL/file URL. If both are used, tag source quality and avoid duplicate feature kinds unless there is an explicit merge rule.

### 2. Snap search requires the cursor ray to hit a mesh before snap candidates are considered

Severity: High

Evidence:

- `findSnapTarget()` raycasts meshes and returns `null` when there is no face hit in `viewer/stl-viewer/src/components/Viewer.tsx:572-580`.
- Candidate features are only built for the hit object in `viewer/stl-viewer/src/components/Viewer.tsx:582-594`.

Impact:

A visible endpoint, edge, or hole center near the cursor will not snap if the cursor is just outside the solid silhouette or over nearby empty space. This conflicts with the intended "near an edge or vertex" behavior and makes edge/silhouette measurements feel random.

Recommendation:

Split picking into two passes:

1. Raycast faces to identify the primary hovered object when possible.
2. Independently project visible snap features for visible/eligible parts and choose within a screen-space radius.

Keep the primary-hit preference, but do not make it a precondition for snapping.

### 3. Reload can leave stale models and stale measurements on screen

Severity: High

Evidence:

- Reload calls `/api/reload`, then `loadViewerState()` in `viewer/stl-viewer/src/App.tsx:141-148`.
- `loadViewerState()` loads all parts with `Promise.allSettled()` in `viewer/stl-viewer/src/App.tsx:131-137`.
- Each successful load replaces only that part id; removed or failed parts are not purged from `models` in `viewer/stl-viewer/src/App.tsx:84-87`.
- Measurement annotations are local `MeasurementLayer` state and are only cleared by the toolbar request in `viewer/stl-viewer/src/components/Viewer.tsx:280-313`.

Impact:

After reload, a failed model can keep showing old geometry, and existing measurement annotations remain at old world coordinates even if part placements or geometry changed. This creates a dangerous false-current viewer state.

Recommendation:

On every successful `/api/parts` refresh, rebuild `models` as a snapshot keyed by the returned revision and remove missing or failed model ids from visible state. Clear measurements automatically when the backend revision changes, unless annotations are later made model-bound and recalculated.

### 4. "Hole Center" currently means "any circular edge center"

Severity: High

Evidence:

- Every STEP edge with `geom_type == "circle"` becomes a `circle_center` with label `Hole Center` in `src/flow_cad/viewer/service.py:185-203`.
- The test accepts a plain cylinder as producing a `Hole Center` in `tests/test_viewer_service.py:171-174`.

Impact:

Bosses, outer cylinders, roundovers, circular outlines, and decorative arcs can all be labeled as hole centers. For robot hardware work, this is a fundamental semantic error: a snap named "Hole Center" should mean a hole/through feature, not any circular curve.

Recommendation:

Rename the raw feature to `circle_center`/`Circle Center`, then add a separate hole-classification pass only when topology supports it. A conservative first step is to expose radius, plane/axis, source edge kind, and label unknown circles neutrally.

### 5. Quick-measure mode can drop pointer capture without cleanup

Severity: Medium

Evidence:

- Measurement mode cleanup clears hover/draft refs when mode becomes `off` in `viewer/stl-viewer/src/components/Viewer.tsx:295-306`.
- The pointer event effect removes listeners on cleanup but does not release capture or handle `pointercancel` in `viewer/stl-viewer/src/components/Viewer.tsx:395-402`.
- Pointer capture is acquired on measurement pointer-down in `viewer/stl-viewer/src/components/Viewer.tsx:351-365`.

Impact:

If the user releases `M`, changes mode, or the browser cancels the pointer during an active measurement, the canvas can retain pointer capture until the browser clears it. This is a plausible cause of intermittent stuck or missed measurement interactions.

Recommendation:

Track the captured pointer id in a ref, release capture in the cleanup path, and handle `pointercancel`/`lostpointercapture` the same way as pointer-up.

### 6. Selection has two meanings but one `activeName`

Severity: Medium

Evidence:

- Parts panel single-click isolates visibility through `handlePartActivate()` in `viewer/stl-viewer/src/App.tsx:321-331`.
- Scene click without Ctrl only changes `activeName`, not visibility, in `viewer/stl-viewer/src/App.tsx:333-340`.
- Both paths render as the same active part highlighting and source-panel selection.

Impact:

The UI has `selectedIds` for visibility and `activeName` for source/highlight, but the names and interactions are easy to confuse. A user can click a part in the scene, see it active, and assume it is selected/isolated when it is not. This is selection tech debt that will get worse when edit tools arrive.

Recommendation:

Name the states by behavior, for example `visiblePartIds` and `activePartId`. Decide whether scene click should isolate, activate only, or use a separate inspect affordance, then make parts panel and viewport semantics visibly consistent.

### 7. Measurement snap scoring is heuristic-heavy and not covered by tests

Severity: Medium

Evidence:

- Snap ranking uses priority, pull bonus, sticky bonus, and fixed screen radii in `viewer/stl-viewer/src/components/Viewer.tsx:683-692`.
- The tested measurement helpers cover distance math and mesh feature extraction, but not `findSnapTarget()`, visibility filtering, previous-target stickiness, face fallback, or mode transitions.

Impact:

The highest-risk measurement behavior is private to `Viewer.tsx` and effectively untested. Changes to snap priority can silently shift behavior across hole centers, vertices, edges, face points, and free points.

Recommendation:

Extract picking/ranking into a pure module that accepts camera matrices, projected targets, hit data, and previous-target id. Add deterministic tests for edge-near-cursor, silhouette snap, circle-center priority, sticky target release, face fallback, and no-hit behavior.

### 8. STEP snap cache freshness only watches the STEP file mtime

Severity: Medium

Evidence:

- Snap feature and converted-STL cache freshness uses `cache mtime >= source mtime` in `src/flow_cad/viewer/service.py:301-318` and `src/flow_cad/viewer/service.py:414-416`.

Impact:

Changing snap extraction logic, schema semantics, converter settings, tolerances, or dependency behavior will not invalidate old cache files unless the STEP mtime changes or the schema version is manually bumped.

Recommendation:

Include a cache metadata object with extractor version, converter version, source file size/hash, and schema version. Use it for invalidation. Bump the extractor version whenever snap semantics change.

### 9. Viewer entry points and docs describe multiple stale viewer modes

Severity: Medium

Evidence:

- `viewer/README.md` describes a no-server viewer with OBJ/GLTF support and says measurement tools are future work.
- `viewer/stl-viewer/README.md` describes the React viewer as an STL viewer, not the source-backed Flow CAD viewer.
- `scripts/serve_viewer.py`, `scripts/convert_step_to_stl.py`, and `viewer/step_converter.py` are separate legacy paths.
- `viewer/step_converter.py` returns converted STL bytes with STEP media type `application/vnd.ms-pki.stp`.

Impact:

Agents and users have several plausible but conflicting ways to start or reason about the viewer. That increases the chance of fixing the wrong viewer or testing the wrong path.

Recommendation:

Make `flow start` / `flow viewer start` the documented primary path. Mark `viewer/index.html` as legacy smoke viewer. Move or delete dead converter scripts after checking whether any handoff workflow still depends on them.

### 10. `flow viewer start` and `flow start` do not target projects the same way

Severity: Medium

Evidence:

- `flow start` loads the current project and passes `project.root` into `start_viewer()` in `src/flow_cad/cli.py:33-54`.
- Nested `flow viewer start` passes the package/repo `PROJECT_ROOT` instead in `src/flow_cad/viewer/cli.py:42-50`.
- `start_viewer()` also hardcodes the frontend path from `PROJECT_ROOT` in `src/flow_cad/viewer/cli.py:63`.

Impact:

The two commands look equivalent but can show different projects. This is especially risky for laptop or external-project checkouts, where portability is a stated goal.

Recommendation:

Make nested `flow viewer start` delegate through the same current-project loading path as `flow start`, or clearly reserve it for Flow CAD development. Resolve the frontend asset path separately from the project root.

### 11. Source context ignores the requested context window and sends full files

Severity: Low

Evidence:

- `context_lines` is assigned to `_` and ignored in `src/flow_cad/viewer/service.py:321-356`.

Impact:

The current behavior may be intentional for transparency, but the parameter name is misleading and full-file payloads can become expensive as generators grow.

Recommendation:

Either remove the parameter and document full-file source display, or return both `content` and a bounded `excerpt` with clear fields.

### 12. Mesh metrics are useful, but not authoritative for CAD dimensions

Severity: Low

Evidence:

- Bounds, volume, surface area, and mesh quality are calculated from the STL `position` attribute in `viewer/stl-viewer/src/meshMetrics.ts:49-101`.

Impact:

These metrics are good for STL health and rough print estimates, but they are not a substitute for STEP/BRep-derived dimensions. This matters if the viewer starts using these metrics for CAD editing or hardware placement decisions.

Recommendation:

Label mesh-derived metrics as mesh metrics in UI/API. Use source CAD or STEP topology for exact dimensions when a part is registry-backed.

## Good Foundations To Keep

- The backend already knows project registry, placements, source files, generated artifact paths, and reload revision.
- The frontend already renders assembled occurrences and applies occurrence transforms consistently for display, bounds, and snap target conversion.
- The distance math in `measurement.ts` has focused tests for point, edge, and edge-to-edge measurement.
- The viewer cache lives under project local state, which is the right shape for portable project checkouts.

## Suggested Fix Order

1. Stop discarding STEP edge and vertex features; use backend snap data as the registry-part authority.
2. Purge stale models and clear measurements on backend revision changes.
3. Extract snap ranking/picking into a tested module.
4. Replace "Hole Center" with neutral circle-center semantics until real hole classification exists.
5. Fix pointer-capture cleanup for measurement mode changes and pointer cancellation.
6. Clarify selection state naming and scene-click behavior.
7. Consolidate viewer docs and mark legacy scripts explicitly.

## Validation Recommendations

Add tests before changing behavior:

- Backend: duplicate circular edges, neutral circle labels, cache invalidation metadata, and external-project `flow viewer start` project root.
- Frontend unit: snap source selection for STEP-backed vs dropped STL models.
- Frontend pure picking: no-face-hit silhouette snap, face fallback, previous-target stickiness, and snap priority.
- Frontend interaction: quick-measure key release during drag, pointer cancel, reload clears stale measurements, and failed reload does not keep old geometry visible as current.

## Bottom Line

The viewer is close enough to keep building on, but measurement should not be treated as trustworthy until STEP snap authority, stale reload state, and snap picking tests are fixed. The current architecture can support that without a rewrite; the main need is to make geometry authority explicit and remove stale state paths.
