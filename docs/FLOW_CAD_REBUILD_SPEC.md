# Flow CAD Professional Rebuild Specification

Status: implementation handoff  
Date: 2026-08-22  
Intended audience: a fresh senior agent or engineer starting without prior
session context

## Executive Decision

The existing Flow CAD repository is frozen as a reference implementation while
a replacement runtime is built on a new branch. The replacement is not an
incremental viewer facelift and is not a port of the current architecture. It is
a clean rebuild around four primary product capabilities:

1. A fast, trustworthy assembled-parts viewer.
2. Measurement that is exact where STEP topology permits it and effortless to
   use.
3. Lightweight viewport annotation that never obstructs normal navigation.
4. Persistent in-application chat that preserves project, viewport, part,
   measurement, annotation, artifact, and agent context across sessions.

The new downstream CAD project will be named `flow_b2`. The existing
`b3_robot` repository will not be deleted or rewritten. It contains real part
source, measurements, assembly knowledge, and generated manufacturing
artifacts. It remains the immutable migration authority until `flow_b2` has
proved that every required source and artifact is preserved.

The replacement must make fast back-and-forth work with agents its central
product requirement. A workflow that takes tens of minutes to rename, rebuild,
display, or discuss one part is a product failure even if it eventually emits
correct geometry.

## Non-Negotiable Requirements

- Work begins on a new Flow CAD branch. Do not develop the replacement directly
  on the legacy branch.
- Do not delete, rewrite, clean, or repurpose `/home/gnulnx/b3_robot`.
- Create `/home/gnulnx/flow_b2` only after the user creates the repository.
- Initialize `flow_b2` using the replacement `flow init`; do not manually copy a
  starter project into place.
- Preserve every B3 part source file and every existing STEP/STL artifact.
- Prove preservation with byte counts, SHA-256 manifests, and `cmp`, not by
  visual similarity or regenerated geometry.
- `flow_b2` may contain product geometry and product parameters. It must never
  contain copied Flow CAD runtime, viewer, registry, cache, build, export, or
  generic validation implementation.
- Flow CAD and `flow_b2` must each have an authoritative `AGENTS.md` with
  mechanically testable ownership boundaries.
- Every long operation must immediately show queued/running/progress/complete
  or failed state. A blank viewport is never acceptable feedback.
- No normal interactive operation may silently run for minutes.
- Every completed change must be committed. Both worktrees must be clean at
  each handoff.

## Baseline That Must Be Preserved

These values describe the inspected state when this specification was written:

| Item | Baseline |
| --- | --- |
| Flow CAD repository | `/home/gnulnx/flow-cad` |
| Flow CAD baseline commit | `6c28a29` |
| Geometry-free viewer listing fix | `ae1de5d` |
| B3 source repository | `/home/gnulnx/b3_robot` |
| B3 baseline commit | `1490ae1` |
| B3 Python part modules | 16 files, 186,840 total bytes |
| Existing STEP artifacts | 90 files, approximately 69 MiB |
| Existing STL artifacts | 90 files, approximately 137 MiB |
| Existing Flow CAD Python runtime | 46 modules, 22,564 lines |
| Existing B3 `flow/` package | 36 files, 12,348 Python lines |

The counts are informative, not the preservation authority. The generated
SHA-256 migration manifests described below are authoritative.

## Why A Rebuild Is Justified

The current system has accumulated many individually useful capabilities, but
their ownership, state, and interaction contracts are not coherent.

The same part identity is repeated through project Python, registry definitions,
assembly placement code, filenames, documentation, validators, tests, generated
artifacts, active cache records, and viewer state. A rename is therefore a
manual cross-repository migration rather than a constant-time lifecycle
operation.

The framework/project boundary also failed structurally. Flow CAD defines core
part metadata types, while `b3_robot` separately defines its own versions of
`PartRole` and `PartDefinition`. Several generic manifest, bundle, registry, and
viewer-placement behaviors also live in B3-local validators. Written ownership
guidance did not prevent this duplication.

The user interface has a similar problem. Viewer, measurement, annotation,
source inspection, metadata editing, URDF export, draft operations, design
threads, worker jobs, chat, visual evidence, and agent screen capture share one
large application state graph. The product exposes many surfaces but does not
provide one short, dependable part-to-screen iteration loop.

This specification preserves the requirements and proven geometry while
rejecting the current coupling.

## Current Flow CAD Feature Inventory

This section records what exists in current source. It distinguishes implemented
capability from product quality. Inclusion here does not require the replacement
to port the implementation.

### 1. Project Bootstrap And Configuration

Implemented today:

- `flow init` scaffolds a project manifest, Python source tree, documentation
  stubs, local state, and project-local skills.
- `flowcad.project.yaml` identifies parameter, registry, assembly, validator,
  output, document, and URDF hooks.
- User configuration resolves from `~/.flow/config.toml` or
  `$FLOW_CAD_HOME/config.toml`.
- Project-local overrides resolve from `.flow/config.toml`.
- `flow start` selects backend/frontend ports, starts both processes, and opens
  a browser by default.
- Editable installation supports developing the runtime against downstream
  projects.

Problems to correct:

- The scaffold encourages each project to implement a Python registry and
  assembly adapter, making it easy to recreate runtime concepts locally.
- The generic project package is named `flow`, which obscures the boundary
  between Flow CAD and project source.
- Ownership is documented but not enforced by imports, schemas, or CI.

### 2. Build, Export, And Handoff Pipeline

Implemented today:

- Build123d/Python generators produce STEP-first geometry.
- STEP and optional STL exports are supported.
- SVG snapshots, text reports, SQLite cache updates, assemblies, tests, and
  export bundles can be included in a build.
- Build modes include default, one-part, changed-only, assembly preview,
  snapshot-only, and strict handoff.
- Build profile selection includes `all`, `active`, and project versions.
- A profiler records part and phase timings.
- `flow cad profile` reports the latest profile and slow events.
- `flow cad urdf` exports registered URDF targets and sidecar reports.

Problems to correct:

- The default build historically performs far more work than interactive review
  needs.
- Artifact generation, validation, reporting, cache refresh, and viewer refresh
  are coupled into broad modes.
- Changed-only behavior depends on project/source conventions that are not a
  formal dependency graph.
- A part lifecycle operation such as rename or retire is absent.

### 3. Registry And Local State

Implemented today:

- `PartDefinition` records an ID, generator, filename, role, material, print
  settings, version/family, assembly compatibility, and optional mass/inertia
  metadata.
- Roles include printable, reference, inspection, and legacy.
- `.flow/registry.db` uses SQLite/SQLModel.
- The cache stores component IDs, module IDs, roles, metadata status, STEP paths,
  volume, bounding boxes, build IDs, Git state, and parameter snapshots.
- `flow registry list` and `flow registry show` query the generated cache.
- The viewer supports local metadata overrides for color, mass, COM, inertia,
  and related fields.

Problems to correct:

- The database is a build cache, not a durable part lifecycle index.
- There is no stable UUID separate from the mutable part name.
- There are no aliases, rename history, retirement transactions, artifact
  freshness rows, assembly occurrence rows, or validation-result rows.
- Projects can and do redefine registry types.
- Deleting or renaming a definition requires manual edits across many surfaces.

### 4. Viewer And Geometry Authority

Implemented today:

- FastAPI provides project, model, source, snap, draft, thread, export, import,
  refresh, evidence, and agent-screen endpoints.
- React, React Three Fiber, Drei, and Three.js render the viewport.
- STEP is the exact geometry authority.
- STEP is converted to a display mesh for browser rendering.
- STL and dropped files are supported as mesh-only, approximate inputs.
- Capability labels distinguish exact and approximate behavior.
- Parts include artifact path, size, mtime, hash, identity, source kind,
  authority, warnings, and occurrences.
- The frontend supports project assemblies and repeated placed occurrences.
- Display modes include workbench/model/reference coloring.
- The viewport includes lighting, grid/axes, fit-to-view, frame-selected, and
  multiple rotation modes.
- Files can be opened or dropped into the viewer.
- Project reload and model refetch endpoints exist.

Problems to correct:

- Current viewer behavior spans very large modules: `App.tsx` is 2,939 lines,
  `Viewer.tsx` is 1,159 lines, and `index.css` is 2,406 lines.
- Backend routing and orchestration are similarly concentrated: `app.py` is
  2,362 lines and `service.py` is 1,665 lines.
- Viewer state, chat state, draft state, build state, source state, metadata
  state, and evidence state are interdependent.
- Parts can be indexed without having current render artifacts.
- Default visibility can select a large assembly, triggering many concurrent
  model fetches and browser parses.
- Status is primarily a text message. There is no consistent job/progress model
  for startup, conversion, loading, building, validation, and chat.

### 5. Part List, Selection, Inspection, And Metadata

Implemented today:

- Parts are grouped by version and role.
- Printable, inspection, reference, and legacy filters exist.
- Clicking parts controls active inspection and visibility.
- Multiple parts can be shown for assembly review.
- Source code for the active part is displayed in a dock.
- Detailed metadata can be opened and edited.
- Material, display color, mass source, COM, inertia, and notes have UI fields.
- Assembly mass properties can be calculated separately from part listing.
- A center-of-mass marker can be displayed.

Problems to correct:

- Active part, selected parts, visible parts, and assembly occurrences have
  overlapping but different meanings.
- Users can see contradictory selection and visibility states.
- The part list depends on manually maintained project definitions rather than a
  stable lifecycle registry.
- Metadata edits and source authority are not presented as one clear model.

### 6. Measurement

Implemented today:

- Persistent tape mode and keyboard quick-measure mode exist.
- Measurements can use two picked targets or the shortest distance between
  supported edge targets.
- Exact STEP snap targets include vertices, line edges, edge midpoints, and
  circle centers.
- Mesh-only models receive approximate browser-derived vertices and edges.
- Face points and free points are supported.
- Hovering an edge can preview its length.
- Measurement labels show distance, axis deltas, and exact/approximate quality.
- Measurement labels can be repositioned, deleted, and switched between picked
  and shortest resolution where applicable.
- A clear-all command exists.

Problems to correct:

- Measurement discovery is buried under the View menu and duplicated by
  keyboard behavior.
- Snap ranking and pointer behavior remain heuristic-heavy.
- Earlier implementations required a mesh face hit before considering nearby
  snaps, which made silhouette and near-edge measurement unreliable.
- Exact STEP and approximate mesh truths have historically been mixed.
- Measurements are session state rather than durable feature-anchored project
  objects.
- Reloading or changing geometry can invalidate world-coordinate annotations.
- The current interaction is capable but not yet “select two obvious points and
  get a trusted answer” simple.

### 7. Viewport Annotation

Implemented today:

- Annotation mode can be toggled from the Edit menu or keyboard.
- Pen/freehand, circle, and text/note tools exist.
- Undo and clear actions exist.
- The viewport overlay records normalized screen coordinates.
- Annotations can be included with context snapshots, screenshots, visual
  evidence, and chat turns.
- Browser viewport capture can preserve the live camera and markup overlay.

Problems to correct:

- The annotation toolbar competes with the viewport and current menu model.
- Screen-coordinate markup is not inherently attached to durable topology.
- Annotation state is coupled to chat/evidence workflows.
- Approximate annotation-to-geometry projection has been used for draft edits;
  it is not an exact CAD operation.
- The distinction between temporary markup, saved review note, and requested
  geometry change is not clear enough.

### 8. Persistent Threads And Chat

Implemented today:

- Design threads have IDs, titles, status, archive state, messages, and event
  history.
- A default thread can be created automatically.
- Messages, draft events, plans, validator events, viewport context snapshots,
  attachments, and visual evidence can be stored.
- The chat dock includes history, a composer, context chips, thread management,
  attachment/evidence trays, build/validate actions, and worker progress cards.
- Streaming and non-streaming chat endpoints exist.
- Worker jobs can be queued, streamed, cancelled, and committed.
- Codex CLI subprocess execution and provider/runtime configuration exist.
- Some deterministic natural-language draft paths exist for panels, holes, and
  annotation-derived raised walls.

Problems to correct:

- The current chat implementation has previously behaved like a slower terminal
  transcript rather than a direct CAD collaboration surface.
- Tool calls and tool results have not always formed a reliable bounded
  execution loop.
- Subprocess agent startup is expensive and fragile.
- Simple operations can generate excessive progress/tool cards.
- Follow-up draft context, selected/visible context, and viewport evidence have
  historically drifted.
- Visible progress is inconsistent across provider reasoning, tool execution,
  CAD generation, validation, and viewer refresh.
- Chat complexity is embedded in the same frontend and backend modules as basic
  viewing.

### 9. Draft Geometry And Preview

Implemented today:

- Draft boxes/profiles can be created without immediately modifying production
  source.
- Thickness, holes, counterbores, slots, raised walls, louver patterns, and
  mirroring are represented as draft operations.
- Transaction-first draft editing supports begin, apply, measure, preview,
  accept, and discard.
- Draft STEP and display previews live under project-local state.
- Focused validators can operate against draft transactions.
- Accepted drafts can produce source patches and acceptance artifacts.
- A deterministic preview-command grammar handles some panel requests.

Problems to correct:

- The draft operation registry, MCP tools, viewer endpoints, chat adapters, and
  source-promotion paths form too many overlapping APIs.
- Drafting is not the user's primary requested product. It must not delay the
  viewer, measurement, annotation, registry, or chat foundation.
- Draft support should return only after the replacement proves the core
  part-to-screen loop.

### 10. Validation, Reports, Profiling, And Bundles

Implemented today:

- A focused validator framework exposes validator contracts, fact providers,
  result schemas, profiles, CLI commands, and MCP tools.
- Generic panel and placement validators exist.
- Projects can register project-local validators.
- CAD text reports, build profiles, validator profiles, active-cache facts,
  draft facts, snap features, and URDF reports exist.
- Export bundles and print-manifest validation exist, although some generic
  implementations currently live in downstream project code.
- Interference checking can report pair counts, bounding-box candidates, and
  overlap volumes.

Problems to correct:

- Full-gate work has historically run during ordinary iteration.
- Some validators regenerate or inspect far more geometry than the immediate
  question requires.
- Generic and project-specific validation ownership is inconsistent.
- Reports are numerous but do not replace a single authoritative lifecycle and
  job state.

### 11. MCP, Agent Screen, And Visual Evidence

Implemented today:

- An MCP server exposes default and advanced Flow CAD tools.
- Tools include registry facts, draft transactions, validation, profiles,
  visual evidence, agent-screen requests, viewer refresh, and preview helpers.
- Agent-screen requests can be fulfilled by the user's existing browser
  viewport.
- Captures record source and render context so agents can distinguish the live
  canvas from offscreen renders.
- Visual evidence supports named camera presets and thread-linked PNGs.

Problems to correct:

- The tool surface is too large for the reliability of the underlying lifecycle
  model.
- MCP, viewer backend, and chat have historically exposed overlapping tool
  names and execution paths.
- Agent-visible state is only trustworthy when artifact identity, viewer
  revision, visible occurrences, camera, and annotation overlay agree.

## Current Performance And Reliability Failures

### Full Build Cost

A recorded B3 benchmark found that a normal full build took 534.15 seconds.
The old interference phase alone consumed 438.46 seconds because it recomputed
bounding boxes for 3,741 pairs across 87 parts. Caching one bounding box per
part reduced interference to 5.094 seconds and total build time to 103.70
seconds.

That was a valuable optimization, but a 103-second full build is still not an
interactive loop. The same benchmark also showed that the default profile was
producing 87 STEP files, 87 STL files, and 126 SVG snapshots. Broad output
generation was still the default answer to a local geometry question.

### Blank Viewer Caused By Synchronous Expensive Work

The viewer recently displayed no parts because `/api/parts` synchronously
computed whole-assembly URDF mass properties. The request could take minutes,
preventing the browser from receiving the metadata required to render existing
artifacts. Commit `ae1de5d` moved mass calculation to a separate endpoint and
made part listing geometry-free.

This must become a permanent architecture rule: discovery/list endpoints may
never construct CAD geometry, run validation, calculate assembly mass, or
perform artifact conversion.

### Model Loading And Browser Work

The current frontend selects default-visible assembly parts and concurrently
loads every missing selected model with `Promise.allSettled`. Each model is
downloaded, parsed as STL, given normals and bounds, and optionally paired with
snap features. Large assemblies therefore create a burst of network, parsing,
memory, and render work.

The status text reports a batch count, but there is no unified per-part load
queue, bounded concurrency, byte progress, cancellation, or visible placeholder
state. A slow or failed part can leave the viewport looking empty or partial.

### Cache And Freshness Complexity

Display meshes, converted STEP meshes, snap features, active registry facts,
source files, assembly placements, metadata overrides, frontend models, and
browser cache identity all participate in freshness. Some paths historically
used mtime-only checks. The product has required manual reload/refetch commands
and artifact-hash inspection to prove that the viewer is current.

The replacement needs one content-addressed artifact identity and one database
revision. The browser must never guess freshness.

### Part Rename And Retirement Cost

There is no first-class lifecycle transaction. Renaming a part currently fans
out across source functions, parameters, registry entries, assembly occurrences,
filenames, validators, tests, docs, generated artifacts, and viewer cache state.
This is why an operation that should take seconds can consume an agent session.

### Framework Leakage Into Product Repositories

`b3_robot/flow/` contains 12,348 Python lines, about 55 percent as many lines as
the reusable Flow CAD Python runtime. Much of that is legitimate geometry, but
the project also duplicates framework metadata types and generic workflow
helpers. This makes ownership ambiguous and causes agents to extend whichever
implementation is nearest rather than the reusable runtime.

### Monolithic Runtime And Frontend Modules

The largest current modules combine unrelated responsibilities:

| Module | Lines | Coupled concerns |
| --- | ---: | --- |
| `viewer/stl-viewer/src/App.tsx` | 2,939 | parts, loading, source, metadata, URDF, drafts, threads, evidence, chat, annotations |
| `src/flow_cad/viewer/app.py` | 2,362 | all HTTP routes plus chat/tool orchestration |
| `src/flow_cad/urdf_export.py` | 1,908 | target resolution, mass, COM, inertia, geometry, XML, reporting |
| `src/flow_cad/viewer/service.py` | 1,665 | project loading, artifacts, conversion, snap extraction, source, drafts |
| `viewer/stl-viewer/src/Viewer.tsx` | 1,159 | scene, navigation, picking, measurement, labels, rendering |
| `src/flow_cad/tools/registry.py` | 1,082 | many unrelated agent operations |

Large modules are not inherently slow, but these modules make it difficult to
isolate work, reason about state, test lifecycle boundaries, or let agents make
small safe changes.

### Chat Latency And Feedback

The current chat can start an external Codex subprocess, construct broad context,
stream worker output, execute tools, update drafts, validate, commit, and reload
the viewer. That is too much machinery for a normal design question.

The product has documented failures where no assistant row appeared immediately,
tool execution was not visible, simple operations fell through to slow agent
paths, and users could not tell whether the system was thinking, blocked, idle,
or failed.

### UX Friction

- Measurement is hidden among general View menu actions.
- Annotation is hidden under Edit and opens another overlay toolbar.
- Source and chat share a dock even though they serve different mental models.
- Parts, active source, visible occurrences, and selected state are easy to
  confuse.
- Status messages do not form a consistent progress system.
- Empty, loading, stale, missing-artifact, and failed states are not visually
  distinct enough.
- The interface exposes implementation concepts such as threads, workers,
  drafts, evidence, source loops, and validation events before establishing a
  simple part-review workflow.

## Replacement Product Contract

### The Primary Loop

The replacement succeeds only if this loop feels immediate:

1. Start Flow CAD in `flow_b2`.
2. See the application shell and part inventory immediately.
3. See the assembled robot progressively appear with explicit progress.
4. Select or search for a part.
5. Isolate it or show neighboring parts.
6. Measure it with two obvious clicks.
7. Mark the viewport with an unobtrusive annotation.
8. Ask an agent about the selected part and attached view in the built-in chat.
9. Receive visible progress and a proposed change.
10. Rebuild only the affected part.
11. See the existing viewport update automatically.
12. Continue the same conversation later with the context intact.

### Viewer Requirements

- The application shell and part list render before geometry.
- The viewport always displays an explicit empty/loading/partial/error state.
- Geometry loading uses a bounded queue, not an unbounded assembly burst.
- The selected part loads first; nearby/default-visible parts follow by
  priority.
- Each part row shows indexed, queued, loading, visible, stale, missing, or
  failed state.
- Failed parts do not prevent other parts from rendering.
- Viewer state is driven by one backend revision and content hashes.
- Navigation defaults must be predictable: left drag rotates, right drag pans,
  wheel zooms, and fit/frame actions are always visible.
- Selection, visibility, active inspection, and occurrence identity are distinct
  states with distinct labels.
- A searchable/virtualized part inventory remains responsive with thousands of
  parts.

### Measurement Requirements

- Measure is a first-class viewport tool, not a buried menu option.
- Pressing `M` or clicking Measure enters the same mode.
- Hover feedback clearly identifies vertex, edge, midpoint, circle center, face,
  or free point before the click.
- Exact STEP targets are always preferred and labeled Exact.
- Mesh-only targets are clearly labeled Approximate.
- Snapping searches projected targets near the pointer even when the pointer is
  just outside a solid silhouette.
- The first click pins a start target; the second click creates the result.
- Results show total distance and X/Y/Z deltas in millimeters.
- Edge hover/click can show exact edge length.
- Labels can be moved, pinned, hidden, or deleted without leaving measurement
  mode.
- Measurements persist with the design thread and bind to artifact revision plus
  feature identity when exact topology is available.
- A geometry revision mismatch marks a saved measurement stale rather than
  silently displaying it at old world coordinates.

### Annotation Requirements

- Annotation is a single unobtrusive viewport toggle with a compact edge palette.
- Supported first-release tools are pen, circle, arrow, and text.
- Starting annotation must not change the camera or hide the selected part.
- Escape exits annotation; undo and clear are immediate.
- Markup can be hidden without deleting it.
- Saved annotations belong to a thread/context snapshot and record viewport,
  camera, artifact revision, visible occurrences, and normalized points.
- Annotation is review intent, not CAD topology. Converting annotation to
  geometry requires an explicit agent proposal or CAD operation.
- The toolbar must never cover the geometry region the user is marking.

### Built-In Chat Requirements

- Chat is a permanent dock, not a separate browser session and not a modal.
- A usable default conversation exists immediately in a new project.
- Threads persist under project-local state and survive browser/server restarts.
- Every user turn automatically records selected part, visible occurrences,
  artifact hashes, camera, measurements, annotations, and attached viewport.
- The context packet is visible and inspectable by the user.
- Sending creates an assistant row within 100 ms.
- Reasoning summary, tool activity, build activity, and errors stream into that
  row without flooding the conversation with shell transcripts.
- The user can cancel an agent/build operation.
- A failed operation leaves a retryable, durable record.
- Chat may invoke only registered application operations. It cannot rely on
  copying runtime code into the project.
- Chat is optional: viewing and measurement remain fully functional when no
  model provider is configured.
- The chat storage model must support resuming with Codex or another provider
  without losing prior project context.
- Commit ID, changed files, build job, artifact hashes, and viewer revision are
  recorded as structured turn evidence.

### Registry Requirements

- Each part has an immutable UUID and a mutable human-readable key.
- Aliases preserve old names.
- Rename and retire are atomic operations.
- Assembly occurrences reference immutable UUIDs.
- Registry rows distinguish source definition, build state, artifacts, metadata,
  occurrences, aliases, and validation status.
- Listing parts is metadata-only and never invokes Build123d/OCP.
- SQLite is a disposable runtime index rebuilt from versioned project manifests.
- Versioned YAML/TOML plus Python geometry remain the source of truth.
- Deleting `.flow/flowcad.db` and running `flow sync` must reconstruct the full
  index without regenerating manufacturing artifacts.

## Performance Service-Level Objectives

These are release gates measured on the designated development workstation with
the preserved `flow_b2` fixture. Results must be written to machine-readable
benchmark artifacts and compared in CI.

| Operation | Target | Hard failure threshold |
| --- | ---: | ---: |
| `flow init` | under 1 s | 2 s |
| Backend health available after `flow start` | under 1.5 s | 3 s |
| Browser shell rendered | under 1 s | 2 s |
| Part inventory response, 1,000 indexed parts | under 100 ms | 250 ms |
| First selected model visible from warm cache | under 500 ms | 1 s |
| First selected model visible from cold display cache | under 2 s | 5 s |
| User-visible feedback after any action | under 100 ms | 250 ms |
| Exact snap hover response | under 16 ms average | 33 ms p95 |
| Measurement result after second click | under 50 ms | 100 ms |
| Save annotation/thread event | under 100 ms | 250 ms |
| Rename or retire registry transaction | under 250 ms | 1 s |
| Scoped ordinary part build | under 5 s target | 15 s |
| Viewer reflects completed scoped build | under 1 s | 2 s |
| Full `flow_b2` release gate | under 120 s | 180 s |

Any operation that exceeds one second must show a spinner or progress indicator.
Any operation that exceeds ten seconds must be a cancellable background job
with phase, elapsed time, and last progress update. No request/response endpoint
may block for minutes. No production benchmark may approach eight minutes.

## Three-Part Rebuild Plan

## Part I: Foundation, Ownership, Registry, And Preservation

Goal: establish a small runtime with enforced boundaries and prove that every
B3 part file is preserved before building product UI features.

### Branch And Freeze Procedure

1. Verify both existing repositories are clean.
2. Tag the legacy Flow CAD baseline, for example:

   ```bash
   git tag flow-cad-legacy-2026-08-22 6c28a29
   ```

3. Create the replacement branch from the clean Flow CAD main branch:

   ```bash
   git switch -c rebuild/flow-b2-foundation
   ```

4. Never force-push or rewrite the legacy tag.
5. Do not create or modify `flow_b2` until the user has created the repository.

### Runtime Structure

The replacement should expose a deliberately small public SDK and keep all
runtime implementation private:

```text
src/flow_cad/
  cli/                 command declarations only
  sdk/                 the only project-importable Python API
  project/             manifest loading and dependency checks
  registry/            schemas, sync, aliases, retirement, SQLite index
  jobs/                background jobs, progress events, cancellation
  build/               dependency graph and artifact generation
  artifacts/           hashes, paths, display conversion, preservation
  viewer/api/          thin HTTP route modules
  viewer/services/     query and command services
  chat/                thread storage and provider-independent events
  validation/          generic validators and performance gates
```

Dependency direction is one way:

```text
flow_b2 geometry -> flow_cad.sdk -> Flow CAD internals
```

Flow CAD internals may load a project through the SDK/manifest contract. Project
code may not import internal modules.

### New Manifest And Registry

Use a versioned declarative manifest for IDs, generator references, artifacts,
roles, material metadata, and assemblies. Python remains responsible for
geometry, not lifecycle plumbing.

Example:

```yaml
schema_version: 1
project_id: flow_b2
python_package: flow_b2

parts:
  - uuid: 2ff3ad34-7a6c-4d15-9743-e9790e4ae0cc
    key: unitree_l2_arch_guard
    generator: flow_b2.parts.unitree_l2:make_unitree_l2_arch_guard
    role: printable
    material: PETG
    artifacts:
      step: compute/unitree_l2_arch_guard.step
      stl: compute/unitree_l2_arch_guard.stl

assemblies:
  active:
    occurrences:
      - id: unitree_l2_arch_guard
        part_uuid: 2ff3ad34-7a6c-4d15-9743-e9790e4ae0cc
        translation_mm: [0, 0, 306]
        rotation_deg: [0, 0, 0]
```

SQLite tables should include at minimum:

- `projects`
- `parts`
- `part_aliases`
- `source_definitions`
- `assembly_occurrences`
- `builds`
- `build_jobs`
- `artifacts`
- `artifact_dependencies`
- `validation_results`
- `thread_summaries`

The database is generated state. Manifest and geometry source remain versioned
authority.

### Replacement `flow init`

Running `flow init` inside the user-created `/home/gnulnx/flow_b2` repository
must create only project-owned files:

```text
AGENTS.md
flowcad.project.yaml
flow_b2/
  __init__.py
  params.py
  parts/
    __init__.py
  validators/
    __init__.py
docs/
  PART_INTERFACES.md
  PRINT_MANIFEST.md
tests/
.flow/
  .gitignore
```

It must not copy `PartDefinition`, `PartRole`, cache models, viewer services,
export services, registry implementations, generic validators, or build
orchestration into the project.

### Byte-Identical Preservation Protocol

The migration must preserve both editable part source and generated part
artifacts. Regeneration is not preservation because STEP exporters can change
headers, entity ordering, timestamps, or serialization while representing the
same geometry.

Before copying anything, generate two sorted manifests in `b3_robot` without
modifying its tracked files:

```text
source-manifest.sha256
artifact-manifest.sha256
```

Source scope:

- every file under `flow/parts/`
- `flow/params.py`
- `flow/assemblies/robot.py`
- `flow/registry.py`
- `flow/urdf.py`
- every project validator
- `docs/PART_INTERFACES.md`
- `docs/PRINT_MANIFEST.md`

Artifact scope:

- every regular file under `exports/step/`
- every regular file under `exports/stl/`
- any associated checksum, assembly, or sidecar artifact explicitly referenced
  by the print manifest

The new repository receives an immutable archive:

```text
flow_b2/migration/b3_robot-1490ae1/
  source/
  exports/step/
  exports/stl/
  source-manifest.sha256
  artifact-manifest.sha256
  MIGRATION_MAP.csv
```

Files in this archive are copied, never regenerated or normalized. Preserve
bytes and verify every file with both SHA-256 and `cmp -s`. A migration command
must fail on the first mismatch.

Active part modules may then be copied byte-for-byte from `flow/parts/` to
`flow_b2/parts/` where their relative imports permit it. Files that require
porting must retain the untouched original in the migration archive and receive
a migration-map row containing:

- original path
- original SHA-256
- active destination path
- active SHA-256
- status: identical, renamed-identical, or ported
- reason for any source change
- validating tests

Copied STEP/STL artifacts remain the historical manufacturing baseline.
Newly generated replacement artifacts go to the normal `flow_b2` export tree
and are compared separately for geometric equivalence. They must never overwrite
the preserved originals.

### Boundary Enforcement

Add CI checks that fail when `flow_b2`:

- defines `PartDefinition`, `PartRole`, registry/cache models, build services,
  viewer routes, or generic exporter classes;
- imports anything under `flow_cad` except `flow_cad.sdk` and an explicit list
  of stable geometry helpers;
- contains copied files whose hashes match Flow CAD runtime Python files;
- hardcodes `/home/gnulnx/flow-cad`;
- edits the immutable migration archive;
- leaves untracked or modified task files at handoff.

### Part I Exit Criteria

- New branch exists and legacy tag is immutable.
- Replacement `flow init` completes within its performance budget.
- User-created `flow_b2` initializes successfully.
- Both SHA-256 manifests are committed in `flow_b2`.
- All preserved files pass SHA-256 and byte comparison.
- `flow sync` creates the SQLite index without constructing geometry.
- `flow part list`, `rename`, and `retire` work transactionally in a fixture.
- Two independent tiny fixture projects pass the SDK contract tests.
- Flow CAD and `flow_b2` ownership CI tests pass.
- Both repositories are committed and clean.

## Part II: High-Performance Viewer, Measurement, Annotation, And Chat

Goal: deliver the professional daily-use workbench before porting advanced
drafting, URDF, or broad validation features.

### Backend Design

- Split query routes from command/job routes.
- Part inventory reads only SQLite metadata.
- Model endpoints serve content-addressed display artifacts.
- Conversion and build operations create jobs immediately.
- Use server-sent events or WebSockets for job and chat progress.
- Bound conversion/model-loading concurrency.
- Make every command idempotent using request IDs.
- Store thread events as an append-only schema with migrations.
- Keep provider adapters behind one chat interface.
- Keep agent tools small: inspect part, inspect placement, measure facts, request
  viewport, request build, and propose source patch.
- Do not restore general draft geometry during this part.

### Frontend Design

Break the UI into isolated feature areas:

```text
AppShell
  ProjectStatusBar
  PartInventoryDock
  Viewport
    NavigationControls
    MeasurementTool
    AnnotationOverlay
    ProgressOverlay
  InspectorDock
  ChatDock
  JobDrawer
```

Each feature owns a small state store. Server state uses a query cache; transient
camera/pointer state remains local to the viewport. Chat, annotations, parts,
models, and build jobs do not share a single giant component state object.

### Loading Sequence

1. Render the shell.
2. Fetch project identity and inventory.
3. Render part rows with artifact state.
4. Load selected/priority part display mesh.
5. Paint it immediately.
6. Load remaining assembly parts through a bounded queue.
7. Load exact snap features only for visible/hovered/selected parts.
8. Load source and expensive metadata only on demand.

At every step, display progress and allow useful interaction with already loaded
content.

### Measurement Delivery Order

1. Exact STEP vertices, line edges, midpoints, and circle centers.
2. Screen-space snap search independent of mesh-face hit.
3. Two-click distance with X/Y/Z deltas.
4. Exact edge-length measurement.
5. Movable/pinnable labels and delete/clear.
6. Thread persistence with artifact-revision binding.
7. Approximate mesh measurement with unmistakable labeling.

### Annotation Delivery Order

1. Compact toggle and palette.
2. Pen, circle, arrow, and text.
3. Undo, clear, hide, and Escape behavior.
4. Thread/context-snapshot persistence.
5. Screenshot export that preserves live camera and overlay.
6. Explicit “ask agent about this markup” action.

### Chat Delivery Order

1. Persistent local threads and instant default thread.
2. Composer with optimistic assistant row.
3. Streaming content, progress, cancellation, and durable errors.
4. Automatic selected-part/viewport/measurement/annotation context.
5. Structured artifact/build/commit evidence.
6. One proven agent provider, preferably the provider already authenticated for
  the user.
7. Additional providers only after the primary flow meets latency and recovery
  gates.

The built-in chat should preserve continuity comparable to a browser agent
session while adding exact CAD context the browser session lacks. It should not
attempt to recreate a terminal inside the viewer.

### Part II Exit Criteria

- All viewer and interaction SLOs pass on the preserved `flow_b2` fixture.
- The shell and part list remain usable while geometry loads.
- A missing or corrupt part produces a clear row and viewport error without
  blocking other parts.
- A user can measure two exact points without opening a menu.
- Measurements remain trustworthy across save/reload and become visibly stale
  after geometry revision.
- Annotation never blocks camera navigation when disabled.
- A thread preserves chat, viewport, measurement, annotation, artifact, build,
  and commit context across restart.
- Every operation longer than one second shows progress.
- Frontend modules have narrow responsibilities and contract tests.
- Both repositories are committed and clean.

## Part III: `flow_b2` Migration, Agent Iteration Loop, And Production Gate

Goal: move the real robot into the replacement without losing any part and
prove that agent-assisted iteration is faster, safer, and reproducible.

### Project Migration

- Use the Part I archive and migration map as the only source inventory.
- Port geometry family by family; do not bulk-copy B3 registry or assembly
  runtime code.
- Keep byte-identical part modules where relative imports permit.
- Move B3 dimensions and measurements into `flow_b2` project parameters or
  declarative metadata.
- Translate the active assembly into declarative UUID-based occurrences.
- Translate print intent into registry metadata plus generated documentation.
- Keep B3-only validators in `flow_b2`; move any generic validator into Flow CAD
  first.
- Maintain an explicit status for every original part: preserved-only, active,
  reference, inspection, retired, or superseded.
- Never omit a file because it is not currently used.

### Agent Iteration Contract

Every chat-driven source change follows this bounded sequence:

1. Identify selected part UUID, artifact revision, source module, and assembly
   occurrences.
2. Attach current viewport, camera, visible neighbors, measurements, and
   annotations.
3. State the intended change and affected interfaces.
4. Produce a proposed patch without silently mutating other parts.
5. Apply only after authorization appropriate to the selected mode.
6. Run a scoped build job for the affected part.
7. Run focused project validators.
8. Publish new artifact hashes and viewer revision.
9. Refresh the existing viewport automatically.
10. Record changed files, tests, validators, build timing, commit ID, and any
    remaining uncertainty in the thread.
11. Commit the repository and verify a clean worktree.

The user must be able to stop after step 6 and inspect the geometry immediately.
Full release validation must not block ordinary review.

### Release Gate

The production gate runs separately and includes:

- manifest/schema validation
- registry/assembly referential integrity
- source and parameter dependency validation
- all active STEP/STL exports
- geometric comparison against migration baselines where required
- focused and project validators
- assembly interference
- print manifest generation
- viewer artifact/index consistency
- complete SHA-256 artifact manifest
- project tests
- performance benchmark comparison
- clean Git status

The gate fails if it exceeds 180 seconds on the reference workstation. The
profile must identify the responsible phase rather than merely reporting total
elapsed time.

### Part III Exit Criteria

- Every B3 source and artifact file appears in the preservation manifest and
  passes byte verification.
- Every original part has an explicit migration status.
- The active `flow_b2` assembly renders progressively and completely.
- No active `flow_b2` Python file reimplements Flow CAD runtime behavior.
- Rename and retirement require no cross-file manual search.
- A representative part edit goes from chat request to visible updated geometry
  within 30 seconds, excluding genuinely expensive kernel geometry documented
  by the profile.
- Scoped ordinary parts meet the 15-second hard build threshold.
- Full release gate stays below 180 seconds.
- The built-in chat successfully resumes a prior design thread after restart.
- Flow CAD and `flow_b2` are committed, clean, and independently testable.

## Required `AGENTS.md` Contracts

Documentation alone is insufficient, but the operating guides must clearly
state the architecture enforced by CI.

### Flow CAD `AGENTS.md`

The replacement guide must state:

- Flow CAD is the reusable runtime and public project SDK.
- It owns CLI, init, manifests, registry schemas, SQLite indexing, build jobs,
  artifact management, display conversion, viewer, measurement engine,
  annotation persistence, chat/thread infrastructure, generic validation,
  profiling, and MCP/application tools.
- It never owns B2 geometry, B2 dimensions, B2 assembly placements, B2 mass
  facts, or B2 print intent except isolated fixtures.
- Public project APIs live only under `flow_cad.sdk`.
- Internal modules may not be imported by downstream projects.
- List/query operations are geometry-free.
- Operations over one second expose progress; operations over ten seconds are
  cancellable jobs.
- Runtime changes require fixture-project contract tests.
- Cross-repository changes are committed separately.
- No task ends with a dirty worktree.

It must also include a short architecture map and exact fast/focused/release
commands so a fresh agent does not need to reconstruct the product from source.

### `flow_b2` `AGENTS.md`

The new project guide must state:

- `flow_b2` owns B2 geometry, parameters, assemblies, hardware interfaces,
  measured metadata, project validators, print intent, and generated exports.
- `/home/gnulnx/flow-cad` owns all reusable runtime behavior.
- `/home/gnulnx/b3_robot` is a preserved read-only migration authority unless
  the user explicitly requests work there.
- `flow_b2` may import only `flow_cad.sdk` and explicitly approved stable
  geometry helpers.
- It must never define or copy registry types, cache/database models, build
  orchestration, viewer APIs, export services, generic validators, or runtime
  CLI code.
- Reusable behavior discovered during B2 work is implemented and committed in
  Flow CAD, installed editable, then verified in `flow_b2`.
- Part source changes preserve fixed mating contracts and use focused builds
  before the release gate.
- Original migration files and checksum manifests are immutable.
- Every task reports artifacts and hashes, commits all work, and ends with an
  empty `git status --short`.

## Features Deferred Until The Core Is Proven

Do not rebuild these during Parts I or II unless they are required for the
primary loop:

- general-purpose direct modeling
- automatic annotation-to-geometry mutation
- broad design planner
- multiple model-provider marketplace
- complex source patch generation
- advanced report inventory
- generalized URDF editor UI
- plugin marketplace
- orchestration of multiple autonomous CAD workers
- cosmetic animation beyond clear professional feedback

URDF export, advanced draft operations, and specialized reports can be ported
after `flow_b2` proves the viewer, measurement, annotation, registry, chat, and
iteration performance contracts.

## Fresh-Agent Starting Checklist

A fresh implementation agent must do the following before changing code:

1. Read this specification completely.
2. Read the current Flow CAD and B3 `AGENTS.md` files.
3. Verify baseline commits and clean worktrees.
4. Inventory the exact source/artifact set again; do not assume counts are
   unchanged.
5. Create the legacy tag and new rebuild branch only after confirming targets.
6. Write the preservation manifest tooling and tests before porting runtime
   features.
7. Build two tiny fixture projects before connecting B3 or `flow_b2`.
8. Implement and benchmark `flow init`, `flow sync`, and metadata-only part
   listing.
9. Wait for the user-created `flow_b2` repository.
10. Run replacement `flow init` there.
11. Copy and verify the immutable B3 migration archive.
12. Implement the viewer vertical slice with one real preserved part.
13. Add measurement, annotation, then chat in that order.
14. Expand to the real assembly only after performance gates pass.
15. Commit each repository separately and prove both worktrees clean.

## Final Acceptance Scenario

The rebuild is not complete until a user can perform this scenario without
terminal archaeology:

1. Open `flow_b2` and run `flow start`.
2. See the shell and part list immediately.
3. Watch the B2 assembly load with useful progress.
4. Search for and isolate `unitree_l2_arch_guard`.
5. Measure two mounting centers and an edge clearance easily.
6. Draw an annotation without obstructing the view.
7. Ask in the built-in chat to change the selected guard.
8. See immediate assistant/build progress.
9. Review a scoped rebuilt part in the same viewport within the performance
   budget.
10. Close and restart Flow CAD.
11. Resume the same thread with its viewport, measurements, annotations,
    artifacts, and commit evidence intact.
12. Verify every preserved B3 part source and STEP/STL file still matches its
    original SHA-256.

If any part of that workflow requires an agent to rediscover repository
ownership, manually repair a registry, run an unexplained multi-minute request,
or guess whether the viewer is current, the replacement has not met this
specification.
