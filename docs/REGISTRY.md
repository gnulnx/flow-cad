# Draft Operation Registry

Date: 2026-06-10

## Purpose

The draft operation registry is Flow CAD's contract for fast, agent-safe CAD
iteration. It tells the viewer, MCP tools, deterministic chat adapters, and the
[Design Planner V1](DesignPlanner.md) which draft operations exist, what inputs
they accept, what they can preview, and whether accepted drafts can emit reviewable
source.

The registry exists to stop Flow CAD from growing one hardcoded feature at a
time. A shaped plate, gear, manifold, bracket, fixture, or robot part should be
planned as a set of registered operations or as a project/domain generator that
declares its own operation metadata. Flow CAD core should stay focused on small
reusable primitives and transaction safety.

## Current Authority

The authoritative v1 registry module is:

```text
src/flow_cad/draft_operations.py
```

The registry is intentionally import-light. Reading registered operation
metadata must not construct a project, load a CAD kernel shape, touch `.flow/`,
or write draft artifacts.

Read-only introspection surfaces:

```text
GET /api/draft-operation-registry
MCP tool: draft_operation_registry
```

## Registry Descriptor

Each registered operation has a stable descriptor with these fields:

| Field | Meaning |
| --- | --- |
| `id` | Stable operation id used by plans and tests, for example `add_hole`. |
| `title` | Human-readable label for UI and docs. |
| `summary` | One-sentence description of the operation. |
| `category` | Group such as `primitive`, `feature`, `pattern`, `transform`, or `lifecycle`. |
| `parameter_schema` | JSON-safe parameter schema for agent/UI input validation. |
| `execution_scopes` | Where the operation is available: direct draft, transaction, preview command, MCP, or planner. |
| `feature_kind` | Draft feature kind when the operation creates a feature. |
| `endpoint_slug` | Viewer backend route slug where applicable. |
| `direct_tool_name` | MCP direct-draft tool name where applicable. |
| `transaction_tool_name` | MCP transaction-first tool name where applicable. |
| `supports_preview` | Whether the operation can affect draft preview geometry. |
| `supports_source_emission` | Whether accepted drafts can emit reviewable build123d source for the operation. |
| `authority_level` | Geometry authority level for the operation metadata. |
| `human_review_posture` | Whether the operation is safe to apply deterministically or should require user review. |

The descriptor is metadata. Runtime execution still goes through
`DraftGeometryStore`, `ViewerService`, and transaction endpoints until later
registry-backed dispatch milestones replace hardcoded branches.

## V1 Core Operations

V1 describes the current draft transaction surface:

| Operation | Category | Scope | Source Emission |
| --- | --- | --- | --- |
| `create_box` | primitive | direct, transaction, MCP, planner | yes |
| `set_panel_thickness` | primitive | direct, transaction, MCP, planner | yes |
| `add_hole` | feature | direct, transaction, MCP, planner | yes |
| `add_counterbore` | feature | direct, transaction, MCP, planner | yes |
| `add_slot` | feature | direct, transaction, MCP, planner | yes |
| `add_raised_wall` | feature | direct, transaction, MCP, planner | yes |
| `add_louver_pattern` | pattern | direct, transaction, MCP, planner | yes |
| `mirror_features` | transform | direct, transaction, MCP, planner | yes |
| `measure` | inspect | direct, transaction, MCP, planner | no |
| `export_step` | lifecycle | direct, MCP | no hidden source mutation |
| `preview` | lifecycle | transaction, MCP, planner | no hidden source mutation |
| `accept` | lifecycle | transaction, MCP, planner | writes review artifacts only |
| `discard` | lifecycle | direct, transaction, MCP, planner | no source emission |

## Core Operations Versus Generators

Core operations should be small and broadly reusable. Examples:

- create a box or base solid
- add a through hole
- add a counterbore
- add a slot
- add an additive wall, pad, rib, or boss
- mirror or pattern features
- preview, measure, accept, or discard a draft transaction

Domain concepts should generally be generators or project/plugin operations.
Examples:

- spur gear
- planetary gear train
- coolant manifold
- electronics enclosure
- robot motor mount
- jig or fixture family

A gear should not become a hardcoded Flow CAD core feature. A reusable gear
operation pack should declare:

- generator parameters such as tooth count, module, bore, pressure angle, and
  thickness
- source emitter or source template
- preview support
- validators for tooth count, bore clearance, and manufacturability
- examples and domain notes

Project-specific facts stay in the project repo. Reusable patterns can be
promoted into Flow CAD operation packs or skills once they are generic.

## Planner Contract

Design Planner V1 uses the registry as the operation graph for plan execution.
See [DesignPlanner.md](DesignPlanner.md) for the full `DesignBrief ->
DesignPlan -> operations -> preview/validation` flow and plan types.

Plan kinds are `questions`, `draft_plan`, and `concept_plan`, and only registry
operation IDs are executable in `draft_plan` steps.

For example, a shaped plate from an annotated view should become a plan like:

```text
1. derive_footprint_from_annotations
2. create_box or create_extruded_footprint
3. add_hole x N
4. add_counterbore x N
5. preview
6. run focused validator
7. wait for accept/discard
```

Low-confidence steps should be visible to the user before mutation. High
confidence operations can run deterministically inside a draft transaction, but
the transaction remains draft until accepted.

## Visual Intent

Annotations are not geometry by themselves. Planner V1 requires them to be
converted into intent primitives first, then mapped to operations:

- closed outline
- hole mark
- wall region
- keepout region
- dimension callout
- symmetry hint
- face or plane hint

The current annotated raised-wall adapter maps freehand bounding boxes from
normalized viewport coordinates onto the draft top face. That is useful for fast
preview, but it is explicitly approximate. Exact projection belongs to the
future face-projection milestone in `docs/REGISTRY_TICKETS.md`.

## Extension Rules

When adding an operation:

1. Add or update the descriptor in `src/flow_cad/draft_operations.py`.
2. Add schema and capability tests.
3. Implement execution through `DraftGeometryStore` or a project operation pack.
4. Add viewer and MCP exposure only when the operation is safe for that surface.
5. Add source emission support before claiming accepted drafts are promotable.
6. Add focused validators for dimensions, clearances, and manufacturing risks.
7. Document examples and limitations.

Operations must state their write scope. Draft preview operations write only
under `.flow/`. Transaction accept writes review artifacts under
`.flow/draft-transactions/`; it does not mutate `flow/`, `exports/`, or
`reports/`.

## Current Limitations

- Execution is still partly hardcoded in `DraftGeometryStore`, `ViewerService`,
  FastAPI routes, MCP wrappers, and preview-command dispatch.
- The registry is v1 metadata and introspection first; full registry-backed
  dispatch is tracked in `docs/REGISTRY_TICKETS.md`.
- Project-local operation packs are not loaded yet.
- Exact annotation-to-face projection is not implemented yet.
