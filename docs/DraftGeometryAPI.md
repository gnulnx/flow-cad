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
- add simple louver patterns as repeated rounded slots
- mirror features to an opposing parallel face
- measure draft parts
- export draft STEP preview files
- discard draft runtime state

The API does not yet implement source promotion, draft transactions, viewer UI
editing, neighboring-part preview, or source patch generation. Those belong to
later performance-plan steps.

## Isolation Contract

Draft state and preview artifacts are written only under the active project's
local runtime state:

```text
.flow/drafts/<draft-token>/draft.json
.flow/drafts/<draft-token>/<part-id>.step
```

Draft operations must not write project source under `flow/`, generated handoff
artifacts under `exports/`, reports under `reports/`, or registry cache rows.
The returned `preview_step_path` is a preview artifact, not a handoff export.

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

## Viewer Backend Endpoints

The viewer backend exposes the draft operations separately from generated parts:

```text
POST   /api/drafts/box
POST   /api/drafts/{draft_token}/thickness
POST   /api/drafts/{draft_token}/holes
POST   /api/drafts/{draft_token}/counterbores
POST   /api/drafts/{draft_token}/slots
POST   /api/drafts/{draft_token}/louver-patterns
POST   /api/drafts/{draft_token}/mirror-features
GET    /api/drafts/{draft_token}/measure
POST   /api/drafts/{draft_token}/export-step
DELETE /api/drafts/{draft_token}
```

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

Tools:

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

By default, the MCP server allows the current working directory as the project
root. Set `FLOW_CAD_PROJECT_ROOT` or `FLOW_CAD_MCP_ALLOWED_PROJECT_ROOTS` to
control which project roots the server may write draft state under.
