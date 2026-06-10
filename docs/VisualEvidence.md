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
- `view`: `front`, `back`, `left`, `right`, `top`, `bottom`, `iso`, or
  `custom`
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
GET  /api/design-threads/{thread_id}/visual-evidence/{artifact_id}
GET  /api/design-threads/{thread_id}/visual-evidence/{artifact_id}/image
```

The `POST` endpoint accepts a PNG `data_url` or base64 PNG data plus render
metadata. It stores the artifact and returns the sidecar record. The browser can
use this endpoint for a first manual render button, and later the agent runtime
can call it through a CAD-safe tool after a separate render context captures the
requested view.

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

The tool result should return the artifact id, image URL, metadata, and any
warnings. Text-only model adapters receive the metadata and artifact reference;
vision-capable adapters may receive the image bytes through their provider
adapter.

## Frontend Contract

The Chat workspace should show visual evidence separately from user
attachments. The UI should distinguish:

- user screenshots and markup
- agent/manual render artifacts
- generated standard view packs

The first implementation can add a manual "Render evidence" action that captures
the current canvas into the new visual-evidence endpoint. That is not the final
agent-owned render context, but it proves the storage, thread reload, and UI
contract without disturbing the existing attachment path.

The second implementation should add a hidden or offscreen render context that
loads the same model data as the main viewer and can capture named views without
mutating user camera or visibility state.

Follow Mode should be added only after render events are durable. It must be
off by default, visibly indicated when active, and reversible without stopping
the agent task.

## Test Strategy

Backend tests:

- valid PNG evidence writes image and sidecar under the thread directory
- thread records include `visual_evidence` and `visual_evidence_count`
- metadata and image retrieval endpoints work
- missing thread returns 404
- invalid view presets, malformed image payloads, and non-PNG data return 400
- malicious artifact ids cannot escape `visual-evidence/`

Frontend tests:

- loaded thread visual evidence renders in the Chat workspace
- manual evidence capture posts to `/visual-evidence`
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

