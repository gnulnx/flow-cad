# Refresh And Cache-Busting Feature Request

Status: proposed  
Created: 2026-06-12  
Scope: Flow CAD viewer backend, React viewer, CLI, and MCP/agent control surface.

## Problem

Flow CAD can show stale geometry in the live viewer even after the project source
and generated exports are correct. In the B3 battery rear-panel incident, the
exported STEP/STL and `exports.tar.gz` contained the new centered toggle-switch
hole, and Bambu Studio showed the correct part. Chrome still displayed the old
no-hole mesh in the Flow CAD viewer, while Firefox displayed the correct mesh.

That failure mode is unacceptable for CAD iteration. A user or agent must be
able to prove which exact generated artifact the viewport is rendering, and the
viewer must not reuse stale binary model data after a rebuild.

## Goals

- Make stale model bytes impossible after source/export changes.
- Give users and agents a reliable way to refresh the live viewer process.
- Give users and agents visible proof of the artifact path, mtime, size, and
  content identity currently rendered in the viewport.
- Keep refresh behavior project-aware: `flow start` and all agent tools must
  target the active project root, not a stale or parallel backend.

## Required Features

### Cache-busted model URLs

Registry payloads from `/api/parts` should include model URLs that change when
the generated display source changes. A stable URL such as:

```text
/api/parts/battery_compartment_rear_panel/model
```

is not enough. Use a query value derived from the rendered artifact identity,
for example:

```text
/api/parts/battery_compartment_rear_panel/model?v=<source_mtime_ns>-<source_size>
```

or, preferably:

```text
/api/parts/battery_compartment_rear_panel/model?v=<source_hash>
```

The same rule applies to snap-feature URLs and draft preview model URLs when
their source artifact changes.

### No-store model responses

All model and generated-geometry responses must send no-cache headers:

```text
Cache-Control: no-store
Pragma: no-cache
Expires: 0
```

At minimum this must cover:

- `/api/parts/{component_id}/model`
- `/api/imports/{import_id}/model`
- `/api/draft-transactions/{transaction_token}/model`
- any future model/preview binary endpoints

### Frontend model invalidation

The React viewer must evict and refetch loaded Three.js models when any of these
change for a part:

- backend revision
- `model_url`
- `artifact_path`
- `artifact_mtime_ns`
- `artifact_size`
- `artifact_hash` when available
- placement occurrence transform

The cache key must not be only `partId`. A selected part with the same `partId`
but new model identity must be treated as a different rendered model.

### Live process refresh controls

Agents need a first-class refresh operation that can target the running viewer
process without relying on a human to click reload or manually restart.

Add or extend a tool/API/CLI path that can:

- identify the active viewer backend URL for a project root
- call backend reload for that exact process
- force the frontend to drop currently loaded registry models
- report the new backend revision
- report whether the requested part was refetched
- return the rendered artifact identity after refresh

Suggested surfaces:

```bash
flow refresh --project-root <path> --part <part_id> --force-model-refetch
```

and an MCP/agent equivalent, for example:

```text
mcp__flow_cad.viewer_refresh(project_root, part_id, force_model_refetch=true)
```

This must be distinct from a best-effort browser reload. It should verify that
the live process serving the viewport is the same project root the agent is
editing.

### Rendered artifact identity in the UI

The viewer should expose enough information for the user and agents to verify
what is on screen:

- part id
- artifact path
- source STEP path when a STEP-derived display mesh is used
- display STL cache path
- source mtime
- source size
- source hash when available
- backend revision
- model URL including cache-busting token

This can live in the inspector/details panel and in the agent-screen capture
metadata. Agent screen captures should include the visible part ids plus the
rendered artifact identities for those parts.

## Acceptance Criteria

- Rebuilding a part changes its `model_url` or cache identity in `/api/parts`.
- Chrome, Firefox, and a Playwright browser session all display the rebuilt mesh
  after a normal viewer refresh.
- Browser hard reload is not required for normal CAD iteration.
- `flow refresh --part <part_id>` or the MCP equivalent can refresh the live
  process and report the rendered artifact identity.
- Tests prove a part with the same `partId` and changed artifact identity is
  refetched and reloaded into the Three.js scene.
- Backend tests prove binary model endpoints send no-store headers.
- Viewer/service tests prove model URLs change when the source STEP mtime/size
  or hash changes.
- Agent-screen metadata includes the artifact identity used for the visible
  selected part.

## Regression Test Scenario

Use a small fixture part with one removable through-hole.

1. Start the viewer and load the part without the hole.
2. Rebuild the same part id with a through-hole while preserving the part id.
3. Refresh through the new Flow CAD refresh path.
4. Assert the browser requests a new model URL or sends a no-cache request.
5. Assert the old mesh is removed from viewer state.
6. Assert the new viewport render visibly contains the hole.
7. Assert agent-screen metadata reports the new artifact identity.

## Non-Goals

- Do not solve this by telling users to switch browsers.
- Do not rely on manual browser cache clearing as the normal workflow.
- Do not make B3 project code responsible for generic viewer invalidation.
- Do not hide stale geometry behind a successful selected part id. If rendered
  bytes are stale or unknown, the viewer should say so.
