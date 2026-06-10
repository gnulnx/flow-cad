# Visual Evidence

Flow CAD design threads should preserve the visual reasoning behind CAD work.
The product goal is not "screenshots as decoration"; it is a durable evidence
trail that a human or model can use to understand what was visible, from which
camera, with which parts selected, and why a design decision was made.

## Product Contract

Visual evidence has three distinct sources:

- **User-shared evidence**: the existing active viewport capture with optional
  2D markup. This is the user's intentional "look here" context and must keep
  working exactly as a chat attachment path.
- **Agent visual evidence**: images generated from an agent-owned render context.
  These should not move the user's live camera, hide parts in the user viewport,
  or steal focus.
- **Follow Mode**: an explicit opt-in mode where the user's viewport mirrors the
  agent render context so the user can debug what the agent is inspecting.

The default ownership rule is simple: the user's viewport belongs to the user.
Agent inspection uses a separate render context unless Follow Mode is enabled.

## Storage Contract

Thread-local visual artifacts live under `.flow/design-threads/` and are not
committed by default:

```text
.flow/design-threads/<thread-id>/
  attachments/
    <attachment-id>.png
    <attachment-id>.json
  visual-evidence/
    <artifact-id>.png
    <artifact-id>.json
```

`attachments/` remains the user screenshot and markup path. `visual-evidence/`
is for agent/manual-render artifacts that can be generated without modifying the
active user viewport.

Each visual-evidence sidecar should record:

- `artifact_id`
- `source`: `agent`, `manual-agent-render`, `test`, or a future provider name
- `view`: initially `front`, `back`, `left`, `right`, `top`, `bottom`, or
  `iso`; `custom` can follow once arbitrary camera payloads are supported
- `content_type`: initially `image/png`
- `width` and `height`
- `selected_part_ids`, `visible_part_ids`, and `part_ids`
- `purpose`
- `camera` and `viewport` metadata when available
- active assembly id and backend revision when available
- relative image path
- created timestamp

## API Contract

Initial backend endpoints:

```text
POST /api/design-threads/{thread_id}/visual-evidence
POST /api/design-threads/{thread_id}/visual-evidence-requests
GET  /api/design-threads/{thread_id}/visual-evidence-requests
GET  /api/design-threads/{thread_id}/visual-evidence-requests/{request_id}
POST /api/design-threads/{thread_id}/visual-evidence-requests/{request_id}/complete
POST /api/design-threads/{thread_id}/visual-evidence-requests/{request_id}/fail
GET  /api/design-threads/{thread_id}/visual-evidence/{artifact_id}
GET  /api/design-threads/{thread_id}/visual-evidence/{artifact_id}/image
```

The `POST` endpoint accepts a PNG `data_url` or base64 PNG data plus render
metadata. It stores the artifact and returns the sidecar record. The browser can
use this endpoint for a manual render button. Agent render requests use
`visual-evidence-requests`: MCP or the chat runtime creates a pending request,
the browser fulfills it through the separate offscreen render context, then the
request is marked fulfilled with the artifact id or failed with an error.

Initial agent-safe tool:

```text
request_visual_evidence(
  thread_id,
  view,
  part_ids,
  visible_ids,
  selected_ids,
  fit,
  width,
  height,
  purpose
)
```

The tool result returns a pending request record. Text-only model adapters
receive the request and eventual artifact metadata; vision-capable adapters may
receive the image bytes through their provider adapter after the browser
fulfills the request.

## Frontend Contract

The Chat workspace should show visual evidence separately from user
attachments. The UI should distinguish:

- user screenshots and markup
- agent/manual render artifacts
- generated standard view packs

The manual "Render evidence" action should use a hidden/offscreen render context
that loads the same model data as the main viewer and captures named views
without mutating user camera or visibility state. It should post the resulting
PNG and camera/viewport metadata to the visual-evidence endpoint.

The current user-owned "Attach view" action remains separate and captures the
active viewport plus markup into `attachments/`.

Follow Mode is an explicit debug affordance in the visual-evidence tray. It is
off by default and follows the latest fulfilled agent request in the tray without
mutating the user's live viewport or replacing the user-owned attachment flow.

## Test Strategy

Backend tests:

- valid PNG evidence writes image and sidecar under the thread directory
- thread records include `visual_evidence` and `visual_evidence_count`
- metadata and image retrieval endpoints work
- pending render requests can be created, listed, fulfilled, failed, and
  reloaded from thread payloads
- missing thread returns 404
- invalid view presets, malformed image payloads, and non-PNG data return 400
- malicious artifact ids cannot escape `visual-evidence/`
- malicious request ids cannot escape `visual-evidence/requests/`

Frontend tests:

- loaded thread visual evidence renders in the Chat workspace
- manual evidence capture posts to `/visual-evidence`
- pending requests are fulfilled by the offscreen render worker through
  `/visual-evidence-requests/{request_id}/complete`
- failed render requests are reported through
  `/visual-evidence-requests/{request_id}/fail`
- manual evidence capture uses the separate render context and includes
  `camera`/`viewport` metadata
- manual evidence capture does not use the existing
  `/attachments/viewport-screenshot` endpoint
- reloading a thread restores evidence records
- missing images degrade to an inspectable metadata row

Runtime/manual tests:

- use a downstream project such as `/home/gnulnx/b3_robot`
- reinstall Flow CAD editable into the project environment
- start the viewer
- create a thread
- create user viewport evidence with markup
- create visual evidence
- reload the thread and verify both evidence types survive
