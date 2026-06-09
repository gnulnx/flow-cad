# Flow CAD MCP Server

Flow CAD includes an MCP server for agent-facing workbench operations that need
structured inputs and outputs. The server is a control-plane interface over
shared Flow CAD services, not a second implementation of CAD logic.

The current server is intentionally small. It exposes draft-only geometry tools
for fast panel iteration and writes only project-local runtime draft state.

## Server Entry Points

Run the server over stdio:

```bash
python -m flow_cad.mcp
```

Editable installs also expose:

```bash
flow-cad-mcp
```

The implementation lives in:

- `src/flow_cad/mcp/server.py`
- `src/flow_cad/mcp/__main__.py`
- `src/flow_cad/draft_geometry.py`

The server is built with `FastMCP`, following the same shared-service pattern as
the DojoV2 MCP server: put domain logic in a shared service first, then wrap it
for MCP.

## Project Root Policy

MCP tools may write draft runtime state, so project root selection is explicit.

Environment variables:

- `FLOW_CAD_PROJECT_ROOT`: default project root when a tool call does not pass
  `project_root`.
- `FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS`: path-list of allowed roots. When set,
  requested project roots must be inside one of these roots.
- `FLOW_CAD_MCP_LOG_PATH`: optional MCP log path. Defaults to a temp-file log.

If neither root variable is set, the current working directory is the allowed
project root.

## Current Tools

Draft geometry tools:

- `draft_create_box`
- `draft_set_panel_thickness`
- `draft_add_hole`
- `draft_add_counterbore`
- `draft_add_slot`
- `draft_add_louver_pattern`
- `draft_mirror_features`
- `draft_measure`
- `draft_export_step`
- `draft_discard`

These tools use `DraftGeometryStore` and return the same structured facts as the
viewer backend draft endpoints:

- draft token
- bounding box
- feature list
- hole centers and axes
- preview STEP path
- warnings

Draft artifacts are isolated under:

```text
.flow/drafts/<draft-token>/
```

They must not write `flow/`, `exports/`, `reports/`, handoff bundles, source
patches, or registry cache rows.

## Suggested Use Cases

Use the MCP server for:

- agent-driven draft panel exploration before source edits
- local-model workflows that need deterministic geometry facts
- draft STEP preview generation that must not touch handoff exports
- bounded workbench operations that return small JSON payloads
- future read-only facts such as part metadata, bounding boxes, placements,
  features, last-build profiles, and focused validator results

The MCP server is especially useful when a caller needs to perform several
small operations across turns, such as create a panel, add holes, measure edge
distances, export a preview STEP, and discard the draft.

## When To Add An MCP Tool

Add an MCP tool when all of these are true:

- The operation is reusable Flow CAD runtime or workbench behavior, not
  product-specific geometry knowledge.
- The behavior already lives in a shared service module, or the change adds that
  shared service first.
- The tool can return bounded structured JSON with explicit warnings or errors.
- Any writes are constrained to approved runtime state or produce reviewable
  artifacts.
- The operation is useful for agents, local models, or future UI automation.
- Focused contract tests can prove registration, routing, payload shape, and
  filesystem boundaries.

Good examples:

- read part metadata from active cache
- list generated parts and placements
- return STEP-backed snap or feature facts
- create or modify draft-only preview geometry
- run one focused validator and return coordinates
- read the last build profile summary

## When Not To Add An MCP Tool

Do not add an MCP tool when the operation is:

- project-specific geometry policy that belongs in a downstream project skill,
  validator, or docs file
- a hidden source mutation, hidden source promotion, or unreviewed patch apply
- a direct write to `exports/`, handoff bundles, generated reports, or project
  CAD source
- realtime viewer interaction, camera control, pointer tracking, or streaming
  telemetry
- a long-running gate command where the existing CLI is the better interface
- a broad workflow that should be split into smaller read, draft, validate, and
  promote steps
- a duplicate implementation of logic that already exists in a service or CLI

If a proposed tool would need robot-specific dimensions, material rules,
hardware contracts, or print handoff facts, keep that knowledge in the project
repo and expose only generic Flow CAD primitives here.

## Extension Pattern

Use this order for new MCP capabilities:

1. Add or extend a shared service under `src/flow_cad/`.
2. Add focused tests for the shared service.
3. Add the MCP wrapper in `src/flow_cad/mcp/server.py`.
4. Add tests that use a fake `FastMCP` to prove tool registration and forwarding.
5. Add filesystem-boundary tests for any write-capable tool.
6. Document the tool in this file and any domain-specific API doc.

The MCP wrapper should stay thin: validate root policy, call the shared service,
return its structured payload, and log the call.

## Relationship To Viewer Backend

The viewer backend and MCP server may expose the same shared service, but they
serve different callers:

- Viewer backend endpoints support browser and workbench UI flows.
- MCP tools support agents and local models over stdio.

Keep behavior in the shared service so the two interfaces do not drift. For the
current draft API, both interfaces call `DraftGeometryStore`.

## Readiness Checks

For MCP changes, run:

```bash
python -m pytest tests/test_mcp_server.py
python -m pytest
```

For write-capable tools, tests should prove that outputs stay out of project
source, handoff exports, generated reports, and bundles.
