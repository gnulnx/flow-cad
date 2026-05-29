# Flow CAD Viewer V1 Work Document

This document turns `docs/JOHN_VIEWER.md` into an implementation-ready first goal.
The raw note captures the larger product direction. This file defines the first
working slice: a source-backed viewer iteration loop for faster human and LLM CAD
work.

## /goal

Set up Flow CAD Viewer V1 as a CLI-driven, source-backed viewer iteration loop.

V1 must let a user run one command, open a browser-based 3D viewer, inspect the
active Flow CAD parts in assembled position, select one or more parts, see the
Python source context for selected parts, regenerate source-derived artifacts,
and reload the view quickly.

The viewer must treat STEP and STL as first-class inputs. Because V1 includes a
proper backend, browser rendering may use backend-generated mesh sidecars, but
STEP remains the preferred long-term CAD artifact and generated mesh files are
cache/output only.

## V1 Scope

- Add `flow viewer start` under the existing `flow` CLI.
- Add `flow viewer reload` under the existing `flow` CLI.
- Start a FastAPI backend and React frontend from `flow viewer start`.
- Open the browser to the running viewer.
- Load active registry parts from generated exports.
- Read `.step` and `.stl` files through the backend.
- Convert STEP files on demand to a browser-viewable mesh format and cache the
  result under a generated viewer cache directory.
- Keep STL loading available for direct browser viewing and existing workflows.
- Show parts in assembled coordinates, not local unassembled origin views.
- Provide a right-side parts menu:
  - Single click shows/selects one part.
  - Ctrl-click adds/removes parts from the current assembled view.
- Provide a left-side source panel showing the Python file and source context for
  the selected part.
- Provide a reload path that refreshes the viewer after source rebuilds.

## Non-Goals For V1

- Do not build a full parametric CAD application.
- Do not directly edit generated STEP, STL, GLB, or mesh cache files.
- Do not implement cube/sphere creation yet.
- Do not implement direct fuse/cut booleans yet.
- Do not implement hole punch tools yet.
- Do not implement delete/undo geometry editing yet.
- Do not implement snap-based tape measure point creation yet.
- Do not move source-of-truth geometry out of Python.

## Architecture

### CLI

Add a `viewer` command group to `src/flow_cad/cli.py`.

Required commands:

```bash
flow viewer start
flow viewer reload
```

`flow viewer start` should:

- Resolve the repo root from source paths, not hardcoded absolute paths.
- Ensure viewer dependencies are present or print the exact install command.
- Start the FastAPI backend.
- Start the React/Vite frontend.
- Open the browser to the frontend URL.
- Print backend and frontend URLs.

`flow viewer reload` should:

- Tell the running backend/frontend to refresh its registry/export/source state.
- Print a clear error if no viewer server is running.
- Avoid rebuilding CAD unless the command gets an explicit rebuild option later.

### Backend

Add a small backend package under `src/flow_cad/viewer/`.

Required responsibilities:

- List active registry parts and their export metadata.
- Resolve each part to available generated artifacts.
- Prefer STEP when both STEP and STL are available.
- Serve STL directly when the selected artifact is already STL.
- Convert STEP to a browser-viewable mesh on demand.
- Cache conversion output in a generated directory such as `b3/viewer-cache/`.
- Expose source context for a selected component.
- Expose reload state for the frontend.

Suggested endpoints:

```text
GET  /api/health
GET  /api/parts
GET  /api/parts/{component_id}/model
GET  /api/parts/{component_id}/source
POST /api/reload
GET  /viewer-cache/{path}
```

The conversion layer should use the best available local CAD stack. If a STEP
converter is missing, the backend must return a clear actionable error naming the
missing dependency or environment variable instead of silently failing.

### Frontend

Use the existing React/Three viewer under `viewer/stl-viewer` as the starting
point.

Required UI layout:

- Full-screen 3D scene.
- Right-side registry-driven parts menu.
- Left-side source panel for the selected part.
- Top toolbar with fit-to-view and reload controls.

Required viewer behavior:

- Load model URLs from backend metadata instead of only local drag/drop files.
- Support both backend-converted STEP meshes and direct STL assets.
- Preserve assembled part transforms from backend metadata.
- Single-select a part from the menu.
- Ctrl-select multiple parts from the menu.
- Fit camera to visible selected parts.
- Keep mouse controls simple:
  - Left drag rotates.
  - Right drag pans.
  - Scroll zooms.

### Source Context

V1 is read-first for source code.

The backend should map a selected registry component to the most useful Python
source context available. Prefer explicit registry metadata if it exists. If not,
use a conservative source lookup that returns:

- Python file path.
- Component id.
- Likely generator function or registry entry context.
- Read-only source excerpt.

Editable source from the browser can be a later goal after the read/rebuild loop
is stable.

## Persistence Model

Python source and parameter files remain authoritative.

Generated artifacts are outputs:

- `b3/exports/step/**/*.step`
- `b3/exports/stl/**/*.stl`
- `b3/viewer-cache/**`
- any generated browser mesh sidecars

The viewer may regenerate or cache artifacts, but it must not treat generated
STEP/STL/mesh files as design truth.

## Implementation Order

1. Add the viewer CLI command group and no-op health/reload plumbing.
2. Add FastAPI backend with `/api/health`, `/api/parts`, and `/api/reload`.
3. Wire backend part listing to `src/flow_cad/registry.py`.
4. Add artifact resolution for STEP/STL exports.
5. Add STEP-to-mesh conversion and generated cache paths.
6. Update the React viewer to load backend part metadata.
7. Replace the floating loaded-model list with the right-side parts menu.
8. Add the left-side source panel.
9. Add reload button behavior and `flow viewer reload`.
10. Add tests and manual acceptance notes.

## Acceptance Criteria

- `flow viewer start` starts backend and frontend and opens the browser.
- The browser shows active Flow CAD registry parts.
- A STEP-only part can be viewed through backend conversion.
- An STL part can still be viewed directly.
- Part selection displays geometry in assembled position.
- Single click shows/selects one part.
- Ctrl-click adds/removes parts from the visible selection.
- The source panel shows Python context for the selected part.
- `flow viewer reload` causes the open viewer to refresh metadata/artifacts.
- Missing conversion dependencies produce clear, actionable errors.

## Test Plan

- Run `python -m pytest` after code changes.
- Add CLI tests proving `flow viewer start --help` and `flow viewer reload --help`
  are registered.
- Add backend tests for:
  - health endpoint;
  - registry part listing;
  - STEP/STL artifact resolution;
  - missing converter error handling;
  - reload endpoint behavior.
- Add frontend build or smoke coverage for the viewer app.
- Manually verify the browser flow:

```bash
flow cad build
flow viewer start
flow viewer reload
```

## Future Goals

- Snap-based measurement between points, edges, and vertices.
- Dropping measurement points for later feature placement.
- M4/M5 through-hole and recessed-hole tools.
- Cube tool with translate/resize manipulator.
- Direct fuse/cut authoring that writes back to Python source.
- Browser-editable source panel with guarded update/rebuild behavior.
- Deeper LLM integration for showing live agent edits and proposed source diffs.
