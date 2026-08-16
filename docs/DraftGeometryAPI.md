# Draft Geometry API

Flow CAD exposes a draft-only geometry API for fast simple panel work before a
change is promoted into project source. The API is intentionally separate from
the build, handoff, and project-source paths.

## Scope

The current draft API supports:

- create rectangular box or panel draft parts
- adjust panel thickness
- add through holes
- add basic face counterbores
- add rounded slots
- add raised wall/pad features
- add simple louver patterns as repeated rounded slots
- mirror features to an opposing parallel face
- measure draft parts
- export draft STEP preview files
- discard draft runtime state
- group draft operations into local runtime transactions
- accept a transaction into reviewable source-patch and validator-stub artifacts
- inspect registered draft operation metadata for planner, UI, and MCP use

The API does not yet implement hidden source promotion, viewer UI editing, or
neighboring-part preview. Transaction acceptance writes review artifacts under
local runtime state; it does not apply patches or modify project source.

The draft operation registry is documented in `docs/REGISTRY.md`. The staged
work plan for moving from metadata introspection to registry-backed dispatch is
tracked in `docs/REGISTRY_TICKETS.md`.

## Isolation Contract

Draft state and preview artifacts are written only under the active project's
local runtime state:

```text
.flow/drafts/<draft-token>/draft.json
.flow/drafts/<draft-token>/<part-id>.step
.flow/draft-transactions/<transaction-token>/transaction.json
.flow/draft-transactions/<transaction-token>/accept/source.patch
.flow/draft-transactions/<transaction-token>/accept/<part-module>.py
.flow/draft-transactions/<transaction-token>/accept/check_<part-module>_draft.py
.flow/draft-transactions/<transaction-token>/accept/acceptance.json
```

Draft operations must not write project source under `flow/`, generated handoff
artifacts under `exports/`, reports under `reports/`, or registry cache rows.
The returned `preview_step_path` is a preview artifact, not a handoff export.
Accepted transaction artifacts are review inputs, not applied project changes.

## Coordinate Contract

Draft boxes are centered at the origin with dimensions in millimeters:

- length maps to X
- width maps to Y
- height or thickness maps to Z

Face feature coordinates use the selected face's local rectangle. `x=0, y=0`
means the lower-left corner of that face's local 2D coordinate frame, and the
feature axis follows the outward face normal.

Supported face names:

| Face | Normal | Feature x | Feature y |
| --- | --- | --- | --- |
| top | +Z | X length | Y width |
| bottom | -Z | X length | Y width |
| front | +Y | X length | Z height |
| back | -Y | X length | Z height |
| right | +X | Y width | Z height |
| left | -X | Y width | Z height |

Feature mirroring copies all features from a source face to the opposing
parallel face pair: `top`/`bottom`, `front`/`back`, or `left`/`right`. Mirrored
features keep the same face-local `x`/`y` coordinates and feature parameters,
while their axes follow the target face normal.

## Returned Facts

Every operation returns the current draft facts:

- `ok`
- `draft_token`
- `part_id`
- `dimensions`
- `bounding_box`
- `feature_list`
- `hole_centers`
- `preview_step_path`
- `preview_step_relative_path`
- `warnings`

Warnings include feature edge-distance issues, unsupported partial-hole requests,
counterbore depth problems, and feature application failures.

## Geometry Transactions

Draft transactions group draft operations before source changes are considered:

```text
begin_transaction(part_id="panel_left")
transaction_create_box(...)
transaction_add_hole(...)
transaction_add_louver_pattern(...)
transaction_preview()
transaction_accept()
```

Open transactions can be measured, previewed, accepted, or discarded. Discarding
an open transaction removes its transaction state and draft preview state. Once
accepted, the transaction becomes read-only and further draft mutations fail.

`accept` exports a draft STEP preview if needed, then writes review artifacts
under `.flow/draft-transactions/<transaction-token>/accept/`:

- `source.patch`: unified patch targeting `flow/parts/<part-module>.py` and
  `flow/validators/check_<part-module>_draft.py`
- `<part-module>.py`: generated build123d source for review
- `check_<part-module>_draft.py`: focused validator stub for review
- `acceptance.json`: transaction, draft facts, and target path metadata

The user or agent reviews and applies the patch in the source loop. Flow CAD
does not mutate `flow/` during transaction acceptance.

## Viewer Backend Endpoints

The viewer backend exposes the draft operations separately from generated parts:

```text
POST   /api/drafts/box
POST   /api/drafts/{draft_token}/thickness
POST   /api/drafts/{draft_token}/holes
POST   /api/drafts/{draft_token}/counterbores
POST   /api/drafts/{draft_token}/slots
POST   /api/drafts/{draft_token}/raised-walls
POST   /api/drafts/{draft_token}/louver-patterns
POST   /api/drafts/{draft_token}/mirror-features
GET    /api/drafts/{draft_token}/measure
POST   /api/drafts/{draft_token}/export-step
DELETE /api/drafts/{draft_token}
POST   /api/draft-transactions
POST   /api/draft-transactions/{transaction_token}/box
POST   /api/draft-transactions/{transaction_token}/thickness
POST   /api/draft-transactions/{transaction_token}/holes
POST   /api/draft-transactions/{transaction_token}/counterbores
POST   /api/draft-transactions/{transaction_token}/slots
POST   /api/draft-transactions/{transaction_token}/raised-walls
POST   /api/draft-transactions/{transaction_token}/louver-patterns
POST   /api/draft-transactions/{transaction_token}/mirror-features
GET    /api/draft-transactions/{transaction_token}/measure
POST   /api/draft-transactions/{transaction_token}/preview
POST   /api/draft-transactions/{transaction_token}/accept
DELETE /api/draft-transactions/{transaction_token}
GET    /api/draft-operation-registry
```

`GET /api/draft-operation-registry` is read-only. It returns JSON-safe
operation descriptors and does not create draft state, export preview geometry,
or mutate project source.

## MCP Tools

The MCP server follows the same shared-service pattern used in DojoV2: the MCP
handlers are thin wrappers around `flow_cad.draft_geometry.DraftGeometryStore`.
The broader server policy, use cases, and tool-extension rules are documented in
`docs/FlowCadMCP.md`.

Run the server over stdio:

```bash
python -m flow_cad.mcp
```

An editable install also exposes:

```bash
flow-cad-mcp
```

Default tools:

- `draft_operation_registry`
- `draft_begin_transaction`
- `draft_transaction_create_box`
- `draft_transaction_set_panel_thickness`
- `draft_transaction_add_hole`
- `draft_transaction_add_counterbore`
- `draft_transaction_add_slot`
- `draft_transaction_add_raised_wall`
- `draft_transaction_add_louver_pattern`
- `draft_transaction_mirror_features`
- `draft_transaction_measure`
- `draft_transaction_preview`
- `draft_transaction_accept`
- `draft_transaction_discard`

Direct draft primitives remain available in the advanced MCP toolset for
debugging and tests:

- `draft_create_box`
- `draft_set_panel_thickness`
- `draft_add_hole`
- `draft_add_counterbore`
- `draft_add_slot`
- `draft_add_raised_wall`
- `draft_add_louver_pattern`
- `draft_mirror_features`
- `draft_measure`
- `draft_export_step`
- `draft_discard`

By default, the MCP server allows the current working directory as the project
root. Set `FLOW_CAD_PROJECT_ROOT` or `FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS` to
control which project roots the server may write draft state under. Set
`FLOW_CAD_MCP_TOOLSET=advanced` to expose direct primitives; otherwise agents
see the transaction-first default surface.
