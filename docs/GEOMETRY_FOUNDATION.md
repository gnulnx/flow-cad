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

### Colored component display

STEP-backed inventory entries advertise `display_scene_url`. The workbench
requests a cached GLB through `/api/parts/{uuid}/display-scene` with the indexed
STEP `artifact_revision`. A cold cache is prepared by a cancellable job submitted
to `/display-scene/jobs`. Conversion is serialized in disposable subprocesses;
listing parts and querying cache state never load CAD or product generators.

The disposable `.flow/cache/display-scenes/v3/` cache binds component names,
colors, placements and mesh bytes to the STEP SHA-256 and converter version.
Direct build previews read linear RGB and alpha from the underlying OCCT color,
matching STEP imports independently of build123d's public color representation.
Version 3 invalidates older previews that could contain sRGB material factors.
`/display-scene/model` serves the derived GLB. STEP remains the exact authority;
GLB component selection is visual selection, not an editable CAD operation.
STL remains available for print exports and as an explicitly indicated fallback
if color conversion fails. STL-only inputs remain supported.

Click a component to highlight its edges and show its name; clicking background
clears the selection. Dragging still orbits, and measurement mode keeps its own
pointer behavior. Frame part uses the clicked component's bounds. Colors remain
visible instead of tinting the whole selected assembly. The grid follows the
lowest visible geometry, without changing authored coordinates or export poses.

### Live screen capture for project workbenches

MCP `agent_screen_request`, `agent_screen_latest`, and
`agent_screen_requests_list` use the same project-local `AgentScreenService`
as the current workbench API. They do not initialize the legacy project loader
or CAD kernel. The browser supplies its live canvas and annotation overlay.

New projects must be explicitly included in `FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS`
in the MCP server configuration (an OS-path-separated list). Keep this scoped to
approved projects. Restart/reconnect the MCP server after changing its environment;
an existing connection retains its old list. An allowlist error now identifies
that setting and the need to reconnect. Captures remain under each project's
ignored `.flow/agent-screen/` directory.

The model is intended to support a saved Flow document/operation graph without replacing Python authoring. A future document can persist GUI-created parts, imported STEP references, placements, annotations, measurements, feature anchors, and direct-modeling operations. Flow-generated Python parts can continue to carry params/source bindings while sharing the same `LoadedPart` and `PartGeometry` runtime contract.

## Milestone Boundary

This foundation milestone does not add editable primitives, booleans, hole creation, sketch editing, or GUI direct modeling. It establishes the authority and capability contract those tools must consume later. STL remains supported for viewing and approximate mesh measurement, but STL-derived topology is not an editing foundation.
