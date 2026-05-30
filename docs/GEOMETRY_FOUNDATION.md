# Geometry Foundation

Flow CAD uses a STEP-first geometry authority model. Python generators and params remain the editable source for generated robot parts, while exported STEP geometry is the exact kernel-backed authority for topology, snap targets, measurement, display-mesh generation, and future editing tools.

## Source Hierarchy

1. Flow Python and params are the authoring source for generated parts. The registry binds each generated artifact back to its component id, module id, source callable, print role, and material metadata.
2. STEP is the exact geometry authority. STEP-backed parts are imported through the local build123d/OCP stack for exact topology, exact snap targets, exact measurement inputs, and generated display meshes.
3. STL is mesh-only input. STL files are valid for viewing, mesh metrics, approximate measurement, and print handoff, but they are not CAD-authoritative and must not be used for exact feature editing.

## Runtime Model

`LoadedPart` is the viewer/API-facing registry item. It identifies the part, source binding, artifact paths, assembly occurrences, display URL, snap URL, capabilities, warnings, and current backend revision.

`PartGeometry` describes the active authority for a part:

- `source_kind`: `flow_python`, `step`, `stl`, or `missing`.
- `geometry_authority`: `step_kernel`, `mesh`, or `missing`.
- `quality_label`: `exact`, `approximate`, or `missing`.
- `capabilities`: booleans for display mesh, mesh metrics, exact topology, exact snap, exact measurement, approximate measurement, exact editing, and mesh-only status.
- `warnings`: user-visible limitations such as STL-only approximate measurement.

`DisplayMesh` is the browser-rendering representation. STEP-backed display meshes are generated from exact STEP geometry and cached with a display-mesh contract version plus source artifact metadata. STL display meshes are direct mesh input.

`SnapFeature` is a measurement and future-edit anchor. STEP-backed features come from kernel topology and include vertices, line edges, edge midpoints, and circle centers with exact quality labels. Generic circular edges are labeled `Circle Center`; `Hole Center` is reserved for a future classifier that can prove a circular edge is part of a real hole feature.

## API Contract

`/api/parts` keeps the existing part fields and adds geometry authority fields: `source_kind`, `geometry_authority`, `quality_label`, `capabilities`, and `warnings`.

`/api/parts/{id}/model` remains the display-mesh endpoint. For STEP-backed parts it returns a cached STL display mesh generated from STEP. For STL-only parts it returns the STL artifact directly.

`/api/parts/{id}/snap-features` returns authoritative STEP-derived snap features when exact topology is available. STL-only parts return no exact snap features and include mesh-only capability warnings.

Backend cache entries include source artifact metadata and extractor/display contract versions so stale models and snap features are discarded when the source artifact or extraction contract changes.

## Future Flow Document Direction

The model is intended to support a saved Flow document/operation graph without replacing Python authoring. A future document can persist GUI-created parts, imported STEP references, placements, annotations, measurements, feature anchors, and direct-modeling operations. Flow-generated Python parts can continue to carry params/source bindings while sharing the same `LoadedPart` and `PartGeometry` runtime contract.

## Milestone Boundary

This foundation milestone does not add editable primitives, booleans, hole creation, sketch editing, or GUI direct modeling. It establishes the authority and capability contract those tools must consume later. STL remains supported for viewing and approximate mesh measurement, but STL-derived topology is not an editing foundation.
