 # Flow CAD Geometry Foundation Reset

  ## Summary

  Build a STEP-first, kernel-backed geometry authority layer so the viewer, measurements, exports, and future
  editing tools all consume the same LoadedPart / PartGeometry contract. Keep Python/params as a first-class
  authoring path for generated parts, but design the model so future GUI-authored/imported geometry can live in a
  saved Flow document/operation graph. STL remains supported as mesh-only view/print input with clear approximate
  capability labeling.

  ## Key Changes

  - Add a concise architecture contract doc, likely docs/GEOMETRY_FOUNDATION.md, defining:
      - Source hierarchy: Flow Python/params -> STEP/exact kernel geometry -> STL/mesh-only.
      - LoadedPart, PartGeometry, DisplayMesh, SnapFeature, capability flags, and quality labels.
      - Future Flow document direction for GUI-created parts, imported STEP, placements, annotations,
        measurements, feature anchors, and direct-modeling operations.

      - Explicit milestone boundary: no editable primitives, booleans, hole creation, or GUI editing yet.

  - Introduce a backend geometry authority module that normalizes registry artifacts into one model:
      - STEP-backed parts import through build123d/OCP and expose exact topology, exact snap targets, exact
        measurements, and a generated display mesh.

      - STL-only parts expose display mesh and mesh metrics only, with mesh_only, approximate_measurement,
        exact_editing=false, no exact topology/snap, and warning text that exact CAD editing is disabled.
      - Flow-generated parts keep Python source binding and params metadata while using kernel geometry for
        topology/snap/export behavior.

  - Extend viewer API contracts without breaking existing endpoints:
      - /api/parts adds source kind, geometry authority, capabilities, and warnings.
      - /api/parts/{id}/model remains the display mesh endpoint.
      - /api/parts/{id}/snap-features returns authoritative STEP-derived vertices, line edges, edge midpoints,
        circle centers, and quality/source labels instead of only hole centers.

      - Generic circular edges are labeled Circle Center; Hole Center is reserved for a future real hole
        classifier.

  - Update frontend behavior to consume the geometry contract:
      - STEP-backed parts use exact backend snap targets for edges/vertices/circles instead of browser mesh-
        derived edge fallback.

      - STL/client-loaded files show a clear mesh-only warning: view and approximate measure are allowed; exact
        CAD editing is disabled.

      - Measurement labels show whether a target is exact or approximate where relevant.
      - Backend revision changes purge stale models and clear session measurements so old geometry cannot look
        current.

  - Keep STL as an export/viewing artifact:
      - Continue generating STL/display meshes from exact geometry for browser rendering and print handoff.
      - Do not build feature editing on STL-derived topology in this milestone.
      - Existing mesh metrics stay useful, but are labeled mesh metrics rather than CAD-authoritative dimensions.

  ## Test Plan

  - Backend unit tests:
      - STEP-backed sample returns exact capabilities and all supported exact snap feature kinds.
      - STL-only sample returns mesh-only capabilities, no exact topology, and warning text.
      - Generic circular STEP geometry is not labeled as a hole.
      - Snap/display cache invalidates when source artifact or extractor contract changes.

  - Frontend tests:
      - STEP-backed model uses backend edge/vertex snap features instead of generated mesh edge fallback.
      - STL-loaded model displays mesh-only warning and approximate capability state.
      - Reload/revision change removes stale models and clears measurement annotations.
      - Existing measurement math tests continue to pass.

  - Verification commands:
      - python -m pytest
      - npm --prefix viewer/stl-viewer test
      - npm --prefix viewer/stl-viewer run build

  ## Assumptions

  - First milestone is a foundation slice with runtime behavior changes plus architecture/interface docs.
  - Python/params remain the editable source of truth for generated parts.
  - Future Flow document/operation graph is planned but not implemented as the primary persisted file in this
    milestone.

  - STEP is the preferred import/edit format; STL is mesh-only and approximate.
  - No direct modeling tools are added until this geometry authority layer is in place and tested.

