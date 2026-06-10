# Flow CAD MCP Server

Flow CAD includes an MCP server for agent-facing workbench operations that need
structured inputs and outputs. The server is a control-plane interface over
shared Flow CAD services, not a second implementation of CAD logic.

The current server exposes draft-only geometry tools, draft transactions,
focused-validator read/run tools, and design-thread visual evidence storage for
fast panel iteration. Draft tools write only project-local runtime state,
preview artifacts, and review artifacts. Validator tools read project facts and
write only profile files under `.flow/profiles/`. Visual evidence tools write
only thread-local PNG/JSON artifacts under `.flow/design-threads/`.

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
- `FLOW_CAD_MCP_TOOLSET`: optional discovery profile. Defaults to `default`.

If neither root variable is set, the current working directory is the allowed
project root.

## Toolsets

The MCP server keeps the lower-level tools implemented, but it does not expose
every tool by default. This keeps the model-facing discovery surface smaller and
pushes normal agents toward reviewable transaction workflows.

Available toolsets:

- `default`: transaction draft tools, validators/profile, and agent visual
  evidence request/read tools. This is the recommended agent-facing surface.
- `advanced`: every Flow CAD MCP tool, including direct draft primitives and
  raw visual evidence upload. Use for debugging, tests, and power users.
- `visual`: only visual evidence tools, including raw upload.
- `transactions`: transaction draft tools plus validators/profile; no visual
  evidence tools and no direct draft primitives.

Example:

```bash
FLOW_CAD_MCP_TOOLSET=default flow-cad-mcp
FLOW_CAD_MCP_TOOLSET=advanced flow-cad-mcp
```

Codex example:

```bash
codex mcp add flow-cad \
  --env FLOW_CAD_PROJECT_ROOT=/path/to/project \
  --env FLOW_CAD_MCP_TOOLSET=default \
  -- flow-cad-mcp
```

Hermes example:

```bash
hermes mcp add flow-cad \
  --command flow-cad-mcp \
  --env FLOW_CAD_PROJECT_ROOT=/path/to/project \
  --env FLOW_CAD_MCP_TOOLSET=default
```

## Default Tools

The default toolset exposes 19 tools:

Draft transaction tools:

- `draft_begin_transaction`
- `draft_transaction_create_box`
- `draft_transaction_set_panel_thickness`
- `draft_transaction_add_hole`
- `draft_transaction_add_counterbore`
- `draft_transaction_add_slot`
- `draft_transaction_add_louver_pattern`
- `draft_transaction_mirror_features`
- `draft_transaction_measure`
- `draft_transaction_preview`
- `draft_transaction_accept`
- `draft_transaction_discard`

Focused validator/profile tools:

- `validator_list`
- `validator_run`
- `profile_last`

Design-thread visual evidence tools:

- `visual_evidence_list`
- `visual_evidence_get`
- `request_visual_evidence`
- `visual_evidence_requests_list`

## Advanced Tools

The advanced toolset includes all default tools plus direct draft primitives and
raw visual evidence upload.

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

Advanced visual evidence tool:

- `visual_evidence_create`

These tools use `DraftGeometryStore` and return the same structured facts as the
viewer backend draft endpoints:

- draft token
- transaction token when using transaction tools
- bounding box
- feature list
- hole centers and axes
- preview STEP path
- source patch and validator stub paths after transaction acceptance
- warnings

Validator tools return:

- validator metadata
- structured report JSON
- issue counts by severity
- expected/actual values, units, coordinates, feature ids, and remediation when
  available
- profile path and latest-profile summary

Visual evidence tools return or persist:

- artifact id
- source, view preset, purpose, image dimensions, and part ids
- relative PNG and metadata paths
- browser API image URL for viewer-backed inspection
- caller metadata such as provider, render context, or test source

Draft artifacts are isolated under:

```text
.flow/drafts/<draft-token>/
.flow/draft-transactions/<transaction-token>/
.flow/design-threads/<thread-id>/visual-evidence/
```

They must not write `flow/`, `exports/`, `reports/`, handoff bundles, source
files, or registry cache rows. Accepted transactions may write reviewable source
patches and validator stubs only under `.flow/draft-transactions/`.

## Suggested Use Cases

Use the MCP server for:

- agent-driven draft panel exploration before source edits
- local-model workflows that need deterministic geometry facts
- draft STEP preview generation that must not touch handoff exports
- transaction acceptance that produces reviewable source-patch artifacts without
  applying them
- bounded workbench operations that return small JSON payloads
- future read-only facts such as part metadata, bounding boxes, placements,
  features, last-build profiles, and focused validator results
- agent/manual visual evidence persistence once a renderer or browser session
  has produced PNG data

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
- direct control of the user's live viewport for agent visual inspection
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

For visual evidence, the viewer backend and MCP server call the design-thread
service. MCP can create/list/read durable evidence artifacts when the caller
already has PNG image data. MCP can also call `request_visual_evidence` to write
a pending browser-render request under the design thread. The viewer fulfills
that request with its offscreen render context and marks the request fulfilled
or failed. MCP must not drive the user's live viewport directly.

## Readiness Checks

For MCP changes, run:

```bash
python -m pytest tests/test_mcp_server.py
python -m pytest
```

For write-capable tools, tests should prove that outputs stay out of project
source, handoff exports, generated reports, and bundles.
