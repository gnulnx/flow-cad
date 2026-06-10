# Draft Operation Registry Tickets

Date: 2026-06-10

## Goal

Flow CAD needs an extensible draft-operation registry so new design capabilities
do not require hardcoding every feature in the viewer backend, MCP server, chat
adapter, and source emitter independently.

The registry is the contract between:

- design-thread planning
- deterministic command adapters
- viewer/backend draft transactions
- planner contract behavior in `docs/DesignPlanner.md`
- MCP tools
- source emission
- focused validators
- project/domain-specific generators

The immediate v1 goal is to make the current draft surface discoverable and
testable as registered operations. Later tickets move execution and plugin
loading behind the registry.

## Non-Goals

- Do not turn every possible CAD concept into a core Flow CAD feature.
- Do not make `gear`, `manifold`, `bracket`, or robot-specific geometry core
  operations.
- Do not mutate project source during draft preview.
- Do not replace build123d source as the production source of truth.
- Do not require exact camera-ray projection before the registry exists.

## Design Principles

- Core operations should be small: create base solid, add/subtract feature,
  pattern, mirror, measure, preview, accept, discard.
- Domain concepts should be generators or project/plugin operations composed
  from core operations.
- Every operation must declare its schema, authority, write scope, preview
  support, source-emission support, validation hooks, and human-review posture.
- The chat planner should produce a visible work plan of registered operations,
  not hidden model prose.
- `docs/DesignPlanner.md` defines the V1 plan types and when each type is used.
- Fast deterministic adapters should call the same registry surface that agents
  and UI automation call.

## Milestone R1: Registry Contract And Introspection

Status: In progress.

### R1.1 Add A Typed Draft Operation Descriptor

Owner: Flow CAD runtime.

Files:

- `src/flow_cad/draft_operations.py`
- `tests/test_draft_operations.py`
- `docs/REGISTRY.md`

Requirements:

- Define a descriptor for existing draft operations.
- Include stable operation id, title, summary, category, parameter schema,
  execution scopes, feature kind where applicable, endpoint slug, MCP tool names,
  source-emission capability, preview capability, and authority level.
- Include every current draft operation:
  - `create_box`
  - `set_panel_thickness`
  - `add_hole`
  - `add_counterbore`
  - `add_slot`
  - `add_raised_wall`
  - `add_louver_pattern`
  - `mirror_features`
  - `measure`
  - `export_step`
  - `preview`
  - `accept`
  - `discard`
- Provide pure functions that return operation descriptors and JSON-safe
  payloads.
- Tests prove ids are unique and required v1 operations are present.

Acceptance:

- `python -m pytest tests/test_draft_operations.py -q` passes.
- The registry can be imported without constructing a project or CAD kernel
  shape.

### R1.2 Expose Registry Through Viewer Backend

Owner: Viewer backend.

Files:

- `src/flow_cad/viewer/service.py`
- `src/flow_cad/viewer/app.py`
- `tests/test_viewer_service.py`

Requirements:

- Add a service method that returns the registry payload.
- Add a read-only endpoint for browser/UI agents.
- Endpoint must not write draft state or require an active project mutation.
- Tests prove `add_raised_wall` and existing hole/counterbore operations are
  present.

Acceptance:

- Viewer backend test proves `/api/draft-operation-registry` returns registered
  operation metadata.

### R1.3 Expose Registry Through MCP

Owner: MCP surface.

Files:

- `src/flow_cad/mcp/server.py`
- `tests/test_mcp_server.py`
- `docs/FlowCadMCP.md`

Requirements:

- Add a read-only MCP tool that returns registered draft operations.
- Make it available in default, advanced, and transactions toolsets.
- Preserve the existing visual-only toolset as visual-only.
- Update toolset tests for expected counts.

Acceptance:

- MCP tests prove the registry tool is in the default and transaction toolsets
  and absent from the visual-only toolset.

### R1.4 Document The Registry

Owner: Docs.

Files:

- `docs/REGISTRY.md`
- `docs/DraftGeometryAPI.md`

Requirements:

- Explain registry purpose, descriptor fields, scopes, v1 operations, extension
  path, and current limitations.
- Explicitly explain why domain concepts such as gears and manifolds should be
  generators/plugins composed from smaller operations.

Acceptance:

- Docs name the authoritative registry module and backend/MCP introspection
  surfaces.

## Milestone R2: Registry-Backed Dispatch

Status: Planned.

### R2.1 Replace Preview Operation Dispatch Tables

Requirements:

- Replace hardcoded `_apply_preview_operation` branches with registry-backed
  dispatch metadata.
- Keep explicit service methods for now, but derive endpoint names and operation
  support from descriptors.
- Tests prove unsupported operation ids fail with a clear registry error.

### R2.2 Generate Backend Endpoint Metadata From Registry

Requirements:

- Keep FastAPI route functions explicit for readability, but derive route docs
  and operation metadata from the registry.
- Add a validator test that every endpoint-backed operation has a descriptor and
  every endpoint descriptor has a route.

## Milestone R3: Planner Work Queue

Status: In progress.

### R3.1 Persist Design Plans In Threads

Status: Implemented for V1 thread persistence.

Requirements:

- Add a design-plan record type to design threads.
- A plan contains tickets/steps, registered operation ids, required context,
  status, assumptions, warnings, and acceptance gates.
- Plan type is one of `questions`, `concept_plan`, or `draft_plan`.
- Chat displays the plan as work-in-progress before draft mutation.

### R3.2 Deterministic Adapters Produce Plans

Status: Implemented for panel/plate parser plans and initial annotation intent
plans; exact sketch projection remains future work.

Requirements:

- Plate/panel command parsing should produce a plan of registered operations.
- Annotated-wall adapter should produce intent primitives first, then a plan.
- The plan should be reviewable before apply when confidence is low.
- See `docs/DesignPlanner.md` for the concrete behavior and preview/validation
  loop for both `draft_plan` and `questions` outcomes.

## Milestone R4: Plugin And Project Operation Registries

Status: Planned.

### R4.1 Load Project-Local Operation Packs

Requirements:

- Support project-local registry extensions under `flow/operations/` or a
  project manifest section.
- Project operations may declare generator functions, validators, docs, and
  examples.
- Project operations cannot silently override core operation ids.

### R4.2 Promote Reusable Operation Packs

Requirements:

- Add a path to promote generic project operation packs into Flow CAD reusable
  skills or packages.
- Keep product-specific dimensions and hardware facts in project repos.

## Milestone R5: Exact Visual Intent Projection

Status: Planned.

### R5.1 Annotation Intent Primitives

Requirements:

- Convert freehand/circle/note annotations into explicit intent primitives:
  closed outline, hole mark, wall region, keepout, dimension callout, symmetry
  hint.
- Persist intent primitives in the context snapshot.

### R5.2 Face Projection

Requirements:

- Project annotation primitives onto selected STEP-backed faces using camera
  state, ray casting, and exact face topology where available.
- Preserve approximate viewport mapping only as a labeled fallback.

## Completion Criteria For R1

- `docs/REGISTRY_TICKETS.md` exists and defines the staged work.
- `docs/REGISTRY.md` documents the v1 registry contract.
- Existing draft operations are discoverable from a typed registry.
- Viewer backend and MCP expose read-only registry introspection.
- Regression tests cover registry metadata and exposure.
- Full Python test suite passes.
