# Flow CAD Workbench Frontend

The rebuild entry point is a small React/Three.js workbench shell. It renders
project and part metadata before geometry, keeps chat permanently available,
and isolates inventory, viewport navigation, chat, inspection, and jobs into
feature-owned modules under `src/workbench/`. The preserved legacy application
remains in `src/App.tsx` as migration reference and is not the active entry
point.

Run from the repository root:

```bash
npm --prefix viewer/stl-viewer install
npm --prefix viewer/stl-viewer run dev
```

Then open:

```text
http://127.0.0.1:3000/
```

## Backend contract

The metadata-first slice consumes these replacement endpoints:

```http
GET /api/project
GET /api/parts
GET /api/models/{display_sha256}
```

`/api/parts` supplies stable UUIDs, lifecycle state, artifact state, STEP
authority/capabilities, occurrence metadata, `display_revision`, and the
content-addressed STL `model_url`. STEP remains exact geometry authority; STL is
only the browser display representation. The frontend never constructs project
geometry while listing parts.

Persistent chat uses the append-only `/api/chat/threads/{thread_id}` contract;
sending a turn durably records the user message, optimistic assistant row, and
attached CAD context before provider dispatch. Jobs remain behind the separate
provisional `/api/workbench/v1` client method and render an explicit unavailable
state until that service is connected. Tests inject a `WorkbenchClient`; a
running host can also set `window.__FLOW_CAD_WORKBENCH_CLIENT__` before React
mounts.

Navigation behavior is implemented independently from model loading:
turntable, arcball, and free-orbit modes; world Z-up turntable/fit; clamped
turntable pitch; left-drag rotate; right/middle-drag pan; wheel dolly about the
current pivot; and fit/frame against occurrence or loaded-model bounds.

While a display model is visible, the frontend polls the protected
`/api/agent-screen/requests/latest` channel. It fulfills pending requests from
the actual WebGL canvas (configured with `preserveDrawingBuffer`) and records
the live camera, selected part/occurrences, display hash, backend revision, and
`render_context: viewport-canvas`. It does not substitute an offscreen render.
