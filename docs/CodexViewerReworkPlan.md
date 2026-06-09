# Codex Viewer Rework Plan

Date: 2026-06-09

## Review Verdict

The proposal in `docs/ViewerLLMInterfaceRework.md` is feasible and should be
part of the performance work. It solves a different problem than item 5.

Focused validators made the source loop faster and more factual, but they do
not preserve design context, conversation history, visual references, or the
human reasoning that led to a change. The current viewer-preview command pane
also works as a deterministic operation surface, but it is too narrow to become
the main design workspace.

The right framing is:

- focused validators answer "is this narrow geometry contract OK?"
- viewer preview answers "can I see a draft before source mutation?"
- design threads answer "what are we trying to do, what did we inspect, what
  did the assistant know, what changed, and why?"

That third loop belongs in the performance roadmap because the slowest part of
many CAD iterations is not kernel time. It is repeated context reconstruction,
ambiguous visual references, lost measurements, stale assumptions, and
serializing every design turn through a single command box.

## Slot In The Performance Roadmap

Do not treat this as a replacement for item 6. Item 6 should remain the preview
engine: selected-part context, command-to-operation proposals, draft
transactions, preview meshes, acceptance artifacts, and focused-validator
follow-up commands.

Add a new roadmap item after viewer preview and before or beside the orientation
cube:

```text
6A. Add Persistent Design Threads And Viewport-Aware Chat
```

This item should absorb the current command pane as one tool inside a real
conversation workspace. The command parser, draft transaction endpoints, preview
model loader, and acceptance artifacts remain valuable; they become structured
tool events in the thread history instead of the center of the UI.

This should also move the "Phase 4: Viewer LLM Interface" section in
`docs/PERFORMANCE.md` from a future MCP note into the main draft/source loop.
The LLM pane should not be optional polish if the goal is to shorten actual
agent-assisted design iteration.

## Current Baseline

Flow CAD already has enough foundation to make this practical:

- `/api/parts` exposes project, assembly, part, occurrence, geometry authority,
  capability, warning, and display URL data.
- `/api/parts/{component_id}/preview-context` exposes selected-part context,
  source availability, snap summary, dimensions, project frame placeholders,
  local frame placeholders, and mating-contract metadata.
- Draft transactions already isolate preview state under `.flow/`.
- Draft preview models are already served as display meshes from `.flow/`.
- Accepted drafts already produce reviewable source-loop artifacts without
  hidden source mutation.
- Focused validators already return structured reports and profile events.
- The MCP server already wraps draft operations, draft transactions, focused
  validators, and profile reads through shared services.

The missing layer is a persisted design-thread service and a frontend chat
workspace that records and reuses this context.

## Proposed Architecture

### Thread Store

Add a project-local thread store owned by the viewer backend:

```text
.flow/design-threads/
  index.json
  <thread-id>/
    thread.json
    messages.jsonl
    context-snapshots/
      <snapshot-id>.json
    attachments/
      <attachment-id>.png
      <attachment-id>.json
```

Use `.flow/` for the first implementation because chat history can include
large screenshots, local paths, failed attempts, and user-specific model output.
Add an explicit export or promote command later for threads that should become
project documentation under `docs/design-threads/` or a generated report bundle.

Use JSONL for messages so the backend can append without rewriting long
histories. Use `thread.json` for title, status, tags, created/updated times,
linked part ids, linked draft transaction tokens, accepted artifact paths, and
summary fields. Atomic writes are enough for the first local-only version.
SQLite can wait until search, concurrent writers, or large history indexing
become real needs.

### Message And Event Model

Represent a design thread as a mixed event history:

- `user_message`: user text and optional attachment references.
- `assistant_message`: streamed assistant text, reasoning summary when
  available, and model/profile metadata.
- `tool_call`: proposed or executed operation with structured inputs.
- `tool_result`: draft facts, validation reports, profile summaries, or errors.
- `context_snapshot`: viewer state captured at the time of a message.
- `draft_event`: begin, apply, preview, accept, discard, or reset.
- `review_event`: accepted source patch, generated source, validator stub,
  acceptance manifest, and source-loop commands.

The key rule is that thread history stores links and structured summaries, not
hidden project mutations. Source edits still require reviewable patches and the
normal source loop.

### Context Snapshots

Add a backend context collector that accepts a viewer state payload and expands
it with authoritative backend facts.

Frontend-provided state:

- camera pose and projection
- visible part ids
- selected part ids
- active measurement ids and values
- active draft transaction token
- active preview model token
- viewport size
- screenshot attachment ids
- annotation ids

Backend-expanded facts:

- project id and project name
- active assembly id and backend revision
- selected/visible part metadata from `/api/parts`
- selected-part preview context
- geometry authority and capability labels
- artifact paths and source context availability
- focused validator results linked to the current thread
- draft transaction status and accepted artifact summaries

The assistant should receive a compact context packet assembled from these
snapshots rather than raw full project state every turn.

### Screenshot And Annotation Storage

The browser can capture the current Three.js viewport with `toBlob()` from the
renderer canvas. Store the image as a thread attachment and pair it with a JSON
sidecar:

```json
{
  "attachment_id": "att_...",
  "kind": "viewport_screenshot",
  "camera": {},
  "visible_part_ids": ["..."],
  "selected_part_ids": ["..."],
  "backend_revision": 12,
  "annotations": []
}
```

Annotation support should store vector overlay data, not burn every note into
the bitmap:

- arrow: start/end normalized viewport coordinates
- circle: center/radius normalized viewport coordinates
- note: normalized anchor plus text
- region: polygon or bounding box
- linked part id when the user pins an annotation to a part

For text-only local models, the screenshot still improves the human record, and
the assistant can use the annotation metadata plus viewer facts. For a future
multimodal runtime, the same attachment can be sent as an image input.

### Chat Runtime And Model Provider Broker

Add an internal interface instead of binding Flow CAD directly to one model
host:

```text
AgentRuntimeClient.stream_chat(thread_id, messages, context_packet, tools, model_profile)
```

The runtime should be selected through a `flow model` provider broker documented
in `docs/ProviderSupport.md`. This broker should follow the Hermes Agent model:
users can pick local, hosted, account-backed, direct API, aggregator, or custom
providers through one setup path. LlamaStudio and LM Studio are both first-class
local providers, but neither should define the whole architecture.

The Flow CAD service should own the CAD tool registry and should expose only
safe Flow CAD tools:

- read current viewer/project facts
- create/update/discard draft transactions
- generate preview models
- run focused validators
- read profile summaries
- return source-loop artifact summaries

Do not expose generic `write_file`, `run_command`, shell, or broad filesystem
tools as the default Flow CAD viewer assistant path. CAD edits should go through
Flow CAD draft, validation, and promotion services with the same filesystem
boundaries as the current MCP tools.

## Provider Setup Reuse Decision

Flow CAD should borrow provider setup behavior from Hermes Agent and local
runtime behavior from LlamaStudio where each project is strongest.

Hermes Agent reuse target:

- provider picker and grouped provider UX
- provider aliases and canonical provider profiles
- auth modes for API key, OAuth, device login, local no-auth, and custom endpoint
- live model discovery and cached model lists
- provider-specific model validation fallbacks
- config/secrets separation and atomic writes
- fallback provider chains

LlamaStudio reuse target:

- local model runtime and profile concepts
- local streaming event vocabulary where compatible
- llama-server lifecycle handling
- local tool-call loop patterns with bounded iterations

LlamaStudio should remain a first-class named Flow CAD provider. LM Studio should
also be a first-class named local provider. They are related local-runtime paths,
but they are not the same integration.

Reusable now:

- Hermes provider profile and registry patterns
- Hermes auth/setup/model-discovery flows, copied or adapted with MIT
  attribution where source is reused
- Hermes tests around provider persistence, model validation, setup delegation,
  and auth edge cases
- LlamaStudio/LM Studio local endpoint probing and streaming adapter behavior
- frontend stream rendering patterns for assistant text, reasoning, and tool
  blocks

Not directly reusable:

- Hermes' full agent loop, because Flow CAD owns CAD context, tool boundaries,
  and source-promotion rules
- Hermes' generic workspace file and shell tools, because Flow CAD needs
  CAD-specific operation boundaries
- LlamaStudio's current UI, because Flow CAD's viewer is React/Three
- global active-conversation assumptions, because Flow CAD needs project-scoped
  design threads
- a single `conversations.json` shape, because Flow CAD threads need screenshot
  attachments, context snapshots, draft transaction links, validator reports,
  and accepted artifact links

Recommended path:

1. Build the Flow CAD thread store and React chat UI natively.
2. Add the `flow model` provider broker from `docs/ProviderSupport.md`.
3. Copy/adapt focused Hermes provider setup code rather than importing the whole
   Hermes runtime.
4. Add first-class local providers for LlamaStudio and LM Studio.
5. Add hosted/account/API providers behind the same profile contract.
6. Keep the `AgentRuntimeClient` boundary small so provider work does not leak
   into the design-thread schema or CAD tool contracts.

## Required Backend Changes

Add a `flow_cad.viewer.threads` service:

- list, create, get, rename, archive, and delete project threads
- append messages and tool events
- write context snapshots
- write screenshot attachments and annotation sidecars
- link draft transactions, validator reports, profile ids, and accepted
  artifacts
- produce compact assistant context packets from the latest thread and viewer
  state

Add viewer API endpoints:

```text
GET    /api/design-threads
POST   /api/design-threads
GET    /api/design-threads/{thread_id}
PATCH  /api/design-threads/{thread_id}
POST   /api/design-threads/{thread_id}/messages
POST   /api/design-threads/{thread_id}/context-snapshots
POST   /api/design-threads/{thread_id}/attachments/viewport-screenshot
POST   /api/design-threads/{thread_id}/chat/stream
POST   /api/design-threads/{thread_id}/draft-events
POST   /api/design-threads/{thread_id}/validator-events
```

Add tests for:

- JSON/JSONL serialization and atomic writes
- path containment under `.flow/design-threads`
- snapshot payload expansion from viewer state plus backend facts
- draft transaction link and accept/discard events
- screenshot write boundaries and metadata sidecars
- SSE stream event formatting with a fake runtime client

## Required Frontend Changes

Replace the command-pane-centered workflow with a left-dock design workspace
that can switch between source and chat:

- left dock tabs for `Source` and `Chat`
- thread list with create, rename, archive, and switch
- message history with persisted user, assistant, tool, context, draft, and
  validation events
- composer for natural conversation
- context chips for selected parts, visible parts, measurements, draft
  transaction, backend revision, and assembly
- screenshot capture button
- attachment tray for screenshots and annotations
- tool/result blocks for proposals, previews, validator reports, profile
  summaries, and accepted artifacts
- compact command/proposal controls embedded as an advanced tool section

This keeps the current Python source pane useful without forcing it to occupy
the main left dock all the time. Source remains one tab; Chat becomes the normal
design-review tab. The Parts panel should remain independently available in its
existing dock so a user can keep parts visible while using chat.

The existing `CommandPane` can be retained briefly as the first tool panel, but
the primary navigation should become thread history. Preview apply/accept
buttons should emit thread events, so the user can later see exactly which
context and draft facts led to an accepted artifact.

Frontend tests should focus on behavior:

- switching threads restores message history and linked context
- sending a message includes current viewer context
- screenshot capture posts an attachment payload
- applying, previewing, accepting, and discarding drafts append thread events
- streamed assistant/tool events render incrementally
- backend reload clears stale live preview state but does not erase history

## Draft Operations In Thread History

Every draft operation should become visible in the thread:

1. User asks for a change.
2. Assistant or parser proposes explicit operations.
3. User applies operations to a draft transaction.
4. Viewer renders the preview model.
5. Focused validator runs against the transaction.
6. User accepts or discards.
7. Acceptance writes review artifacts and source-loop commands.

The thread should store:

- transaction token
- operation list
- before/after dimensions
- feature counts and hole centers
- preview STEP and display mesh paths
- validator report ids or summaries
- acceptance artifact paths
- source-loop commands
- warnings and authority labels

This keeps item 6's work useful while making it discoverable after the immediate
preview session ends.

## Ticket Plan

### CVR-1: Design Thread Persistence

Build the project-local thread store, JSON schemas, API endpoints, and backend
tests. No LLM integration yet.

Done means the viewer can create threads, append messages/events, reload the
browser, and recover the full history from `.flow/design-threads`.

### CVR-2: Viewer Context Snapshot API

Add a context snapshot payload and backend expansion service. Include camera,
visible parts, selected parts, measurements, draft transaction state, active
assembly, backend revision, geometry authority, warnings, and source context
availability.

Done means a user can capture "what I am looking at" as structured data attached
to a thread.

### CVR-3: React Design Thread UI

Replace the command-pane-first experience with a left-dock `Source | Chat` tab
set. The Chat tab should include thread list, message history, composer, context
chips, and tool/result event rendering. Keep the existing preview command
controls available as a structured tool area.

Done means the viewer has a real chat interface with history, while source
review and parts inspection remain accessible without competing for the same
space.

### CVR-4: Screenshot And Annotation MVP

Capture viewport screenshots into thread attachments and store 2D markup JSON.
Start with screenshot capture plus freehand pen strokes, text notes, and circles;
arrows and richer regions can follow.

Done means a user can draw over the current 3D viewport in-app, attach that
marked-up screenshot to a design thread, and keep the structured markup data
with the thread.

Break CVR-4 into these implementation tickets:

#### CVR-4A: Thread Attachment Storage Contract

Add first-class design-thread attachments under each thread directory:

```text
.flow/design-threads/<thread-id>/attachments/
  <attachment-id>.png
  <attachment-id>.json
```

The backend should accept a viewport screenshot payload, sanitize any requested
attachment id, write PNG bytes plus a JSON sidecar atomically, and return a
stable attachment record. Attachment writes must stay contained inside the
thread's `attachments/` directory.

Tests:

- posting a PNG data URL writes `<attachment-id>.png`
- posting the same payload writes a JSON sidecar with `kind`,
  `content_type`, selected/visible ids, backend revision, viewport/camera
  metadata, and annotations
- malicious attachment ids such as `../outside` are sanitized and cannot escape
  `.flow/design-threads/<thread-id>/attachments`
- unsupported content types or malformed image payloads return a 400

Done means screenshot bytes and sidecar metadata are durable project-local
thread artifacts rather than inline-only snapshot fields.

#### CVR-4B: Viewport Screenshot Attachment API

Add:

```text
POST /api/design-threads/{thread_id}/attachments/viewport-screenshot
```

The endpoint should accept `data_url` or base64 image data plus the current
viewer context. It should return an attachment record that can be referenced by
context snapshots and chat turns:

```json
{
  "attachment_id": "att_...",
  "kind": "viewport_screenshot",
  "content_type": "image/png",
  "filename": "att_....png",
  "metadata_filename": "att_....json",
  "selected_part_ids": ["..."],
  "visible_part_ids": ["..."],
  "annotations": []
}
```

Tests:

- route registration includes the new endpoint
- a missing thread returns 404
- a valid request returns a stable attachment record with no absolute local
  paths required by the frontend
- context snapshots and chat payloads can reference `viewport_attachment_id`
  without losing existing inline screenshot compatibility

Done means the frontend has a small, stable API for visual evidence instead of
knowing the backend storage layout.

#### CVR-4C: Markup JSON MVP

Normalize freehand, note, and circle annotations into predictable JSON sidecars:

```json
{
  "annotations": [
    {
      "id": "ann_...",
      "kind": "freehand",
      "points": [{"x": 0.12, "y": 0.20}, {"x": 0.40, "y": 0.32}],
      "color": "#f97316",
      "width": 0.006
    },
    {
      "id": "ann_...",
      "kind": "note",
      "x": 0.52,
      "y": 0.34,
      "text": "move this rib"
    },
    {
      "id": "ann_...",
      "kind": "circle",
      "x": 0.50,
      "y": 0.50,
      "radius": 0.18
    }
  ]
}
```

Coordinates should be viewport-relative numbers clamped to `[0, 1]`. Unknown
annotation types should be ignored or rejected consistently; the first pass needs
freehand, note, and circle.

Tests:

- freehand stroke points are normalized and preserved
- note annotation text is trimmed and preserved
- circle center/radius values are normalized and clamped
- unknown annotation types do not corrupt the sidecar schema
- annotation ids are generated when omitted and sanitized when provided

Done means visual markup is structured data that future multimodal or text-only
assistant adapters can consume.

#### CVR-4D: React Attachment Tray And Annotation Controls

Add a compact visual-evidence area in the Chat workspace:

- an `Attach view` action that posts a viewport screenshot attachment
- a live 2D markup mode over the rendered 3D viewport
- pen, text, and circle tools that place annotations directly on the viewport
- an attachment tray showing captured attachment ids and annotation summaries

The UI should keep threads collapsible and preserve the advanced command tools
as a secondary section.

Tests:

- drawing on the markup overlay creates structured freehand/text/circle
  annotations
- `Attach view` posts selected ids, visible ids, assembly/revision, viewport
  metadata, marked-up screenshot data, and annotation JSON
- the returned attachment id appears in the chat workspace
- switching threads restores returned attachment records from persisted thread
  data when present
- no canvas available in the test environment is handled without crashing

Done means a user can attach the current render plus visual markup from the
first-class chat surface without leaving Flow CAD for a slide editor.

#### CVR-4E: Chat-Turn Attachment References

When a user sends a chat message, include the latest viewport attachment id in
the context payload and message metadata. Keep selected/visible part context
automatic.

Tests:

- sending a message after `Attach view` includes
  `viewport_attachment_id`/attachment metadata in the chat request
- the message history displays the user message, assistant response, and linked
  view attachment
- browser reload keeps thread messages and attachment references visible

Done means chat turns can refer to durable visual evidence instead of ephemeral
canvas state.

#### CVR-4F: Integration And Regression Gate

Run the backend and frontend suites that cover the screenshot/annotation path:

```bash
python -m pytest tests/test_viewer_design_threads.py tests/test_viewer_service.py
npm --prefix viewer/stl-viewer test -- --run App.test.tsx
npm --prefix viewer/stl-viewer test
npm --prefix viewer/stl-viewer run build
git diff --check
```

Done means CVR-4 is not just storage or UI in isolation: the API, React
workspace, chat context payload, persistence behavior, and build all agree.

### CVR-5: Draft And Validator Event Integration

Wire the existing preview, accept, discard, validator, and profile operations
into thread events.

Done means draft previews and focused-validation evidence are no longer hidden
inside transient UI state.

Break CVR-5 into these implementation tickets:

#### CVR-5A: Thread Event API Contract

Add explicit thread event endpoints:

```text
POST /api/design-threads/{thread_id}/draft-events
POST /api/design-threads/{thread_id}/validator-events
```

Draft events should persist as `draft_event` records. Validator, profile, and
focused review evidence should persist as `tool_result` or `review_event`
records with structured content. Both endpoints should update the thread's
linked draft transaction tokens, accepted artifact paths, and updated timestamp
when the payload contains those facts.

Tests:

- posting begin/apply/preview/accept/discard draft events appends durable JSONL
  records
- accepted draft events link source patch, generated source, validator stub,
  acceptance manifest, and source-loop commands
- validator/profile events persist report ids, summaries, status, warnings, and
  profile ids
- missing thread returns 404 and malformed payloads return 400

Done means draft and validation facts have a stable backend event contract
independent of the transient React state that produced them.

#### CVR-5B: Frontend Draft Event Emission

Wire the advanced draft controls to append thread events after each meaningful
draft action:

- proposal parsed
- operations applied to a transaction
- preview model generated and rendered
- focused validator/profile evidence attached
- transaction accepted or discarded
- command state reset

Each event should include the active thread id, selected part id, transaction
token, operation summaries, preview facts, authority labels, warnings, and any
accepted artifact paths already returned by the backend.

Tests:

- applying operations posts an `apply` draft event and renders it in history
- previewing posts a `preview` draft event with preview model/source facts
- accepting posts an `accept` draft event and links acceptance artifacts
- discarding posts a `discard` draft event and clears live preview state without
  erasing thread history

Done means a user can inspect the thread history and understand exactly which
draft operations produced the visible preview or accepted artifacts.

#### CVR-5C: Validator And Profile Evidence Attachment

Add the first narrow event path for focused validator and profile results. The
initial UI may post these records from the assistant/tool stream or from an
advanced tool result block; the data contract should not require a model host.

Tests:

- a focused validator summary appears in the thread as a structured result
- a profile summary can be linked to the same draft transaction
- validator/profile events remain readable after browser reload

Done means validation evidence can be attached to a design decision even before
full model-driven tool orchestration exists.

#### CVR-5D: Integration Gate

Run:

```bash
python -m pytest tests/test_viewer_design_threads.py tests/test_viewer_service.py
npm --prefix viewer/stl-viewer test -- --run App.test.tsx
npm --prefix viewer/stl-viewer test
npm --prefix viewer/stl-viewer run build
git diff --check
```

Done means backend event persistence, React event emission, persisted history,
and the production frontend build agree.

### CVR-6: Streaming Assistant Adapter

Add a runtime-neutral streaming adapter with fake-runtime tests first, then a
provider-resolved implementation selected by `flow model`. The adapter should
receive compact context packets and CAD-safe tool schemas.

Done means a thread can stream assistant output and tool events without giving
the assistant broad filesystem or shell access.

Break CVR-6 into these implementation tickets:

#### CVR-6A: Runtime-Neutral Streaming Interface

Add a small internal adapter boundary:

```text
AgentRuntimeClient.stream_chat(thread_id, messages, context_packet, tools, model_profile)
```

The stream should normalize model-host output into typed events such as
`assistant_delta`, `assistant_message`, `tool_call`, `tool_result`, `done`, and
`error`. Start with a deterministic fake runtime so the backend and frontend can
be tested without a running model server.

Tests:

- fake runtime streams deterministic assistant text and tool events in order
- errors become structured stream events instead of uncaught exceptions
- streamed events include the target thread id and runtime/profile metadata

Done means Flow CAD can test streaming behavior without binding to a specific
LLM process.

#### CVR-6B: Compact Context Packet And CAD-Safe Tools

Build a compact assistant context packet from the active thread, latest context
snapshot, selected/visible part facts, active draft state, attachments, and
linked validator evidence. Expose only Flow CAD safe tools:

- `read_viewer_context`
- `create_draft_transaction`
- `apply_draft_operations`
- `generate_preview_model`
- `run_focused_validator`
- `read_profile_summary`
- `summarize_acceptance_artifacts`

Do not expose generic `write_file`, `run_command`, shell, or broad filesystem
tools on the default viewer assistant path.

Tests:

- context packets omit bulky screenshots but keep attachment ids and annotation
  summaries
- tool schemas include the CAD-safe tools above
- tool schemas exclude broad filesystem and shell capabilities

Done means a model receives enough design context to be useful without bypassing
the existing draft, validation, and source-loop boundaries.

#### CVR-6C: Streaming Chat API

Add:

```text
POST /api/design-threads/{thread_id}/chat/stream
```

The endpoint should append the user message and context snapshot, stream
assistant/tool events as Server-Sent Events, persist the final assistant/tool
records into the thread, and return clean `error`/`done` events. It should fall
back to the fake runtime unless a compatible local runtime endpoint is
configured.

Tests:

- SSE event formatting is valid with a fake runtime client
- assistant deltas are persisted as an assistant message when the stream ends
- tool events are persisted with structured inputs/results
- missing thread returns 404 before any stream body is emitted

Done means the browser can receive incremental assistant output from the Flow
CAD backend with the same persisted thread contract as non-streaming chat.

#### CVR-6D: Provider-Resolved Runtime Client

Resolve the active model profile through the `flow model` provider broker. Keep
environment variables as a temporary override for tests and local experiments,
but make the saved provider profile the normal runtime source.

Add the first concrete runtime clients behind the same adapter:

- LlamaStudio
- LM Studio
- OpenAI-compatible local endpoint
- fake provider for deterministic tests

Tests:

- selected provider profiles resolve into runtime clients
- env overrides still take precedence in tests
- line-oriented `data: {...}` chunks normalize into Flow CAD stream events where
  the provider uses SSE
- malformed chunks become structured warnings/errors without crashing the stream
- runtime configuration is optional and defaults to fake runtime in tests

Done means Flow CAD has concrete adapter paths for first-class local providers
without embedding another application's UI or generic workspace tool surface.

#### CVR-6E: Frontend Streaming Rendering

Teach the React chat workspace to consume the streaming endpoint when available,
render assistant text incrementally, display tool-call/tool-result blocks, and
fall back to the existing JSON `/chat` response if streaming is unavailable.

Tests:

- streamed assistant deltas render before the final `done` event
- tool call/result events appear in the message list
- fallback JSON chat still works for older backends or failed stream setup

Done means chat feels like a first-class design assistant surface rather than a
submit-and-wait form.

#### CVR-6F: Integration Gate

Run:

```bash
python -m pytest tests/test_viewer_agent_runtime.py tests/test_viewer_design_threads.py
npm --prefix viewer/stl-viewer test -- --run App.test.tsx
npm --prefix viewer/stl-viewer test
npm --prefix viewer/stl-viewer run build
git diff --check
```

Done means the runtime adapter, streaming API, persisted thread events,
frontend incremental rendering, and production build are verified together.

### CVR-7: Hermes-Style Model Provider Setup

Implement the `flow model` provider broker described in
`docs/ProviderSupport.md`. This is the provider setup layer for design-thread
chat, worker packets, and future model-backed CAD tools.

The implementation should reuse Hermes Agent's MIT-licensed provider setup code
where practical:

- provider profiles and aliases
- provider grouping and picker behavior
- API-key/OAuth/device/custom-endpoint setup flows
- model discovery, cache, validation, and soft-fallback behavior
- fallback provider chains
- config/secrets separation
- regression tests around provider persistence and auth edge cases
- a provider declaration shape that makes future Hermes provider updates easy to
  compare and manually cherry-pick

LlamaStudio and LM Studio must be first-class provider choices in this broker.
OpenAI Codex is also important, but it is one provider among many, not the reason
for the architecture.

Done means `flow model` can select and test at least LlamaStudio, LM Studio, one
hosted/account provider, one direct API-key provider, and one custom
OpenAI-compatible endpoint, and the viewer backend can use the selected profile.

## Risks And Mitigations

- Context bloat: summarize older turns and send only the latest relevant
  snapshots, selected parts, active draft state, and linked validator evidence.
- Stale geometry: include backend revision and artifact paths in every context
  snapshot; warn when a thread references older state.
- Hidden mutation: keep source changes behind accepted review artifacts and
  explicit source-loop commands.
- Screenshot trust: pair images with camera, visible part ids, selected ids, and
  backend facts so the assistant is not guessing from pixels alone.
- Model-host coupling: keep `AgentRuntimeClient` small and runtime-neutral, with
  provider setup isolated in `flow model`.
- Provider sprawl: copy Hermes' profile/registry/test patterns so adding a
  provider is usually data plus a small setup strategy, not viewer code.
- License drift: confirm Flow CAD's project license and preserve Hermes' MIT
  notices before copying substantial source.
- Project-specific leakage: keep robot-specific design intent in project
  validators, docs, and local skills; Flow CAD owns only the thread/runtime
  machinery.
- Storage noise: store default history under `.flow/`; add explicit export for
  design records worth committing.

## Completion Criteria

The rework is complete when:

- the viewer has persistent project design threads
- each thread survives reload and contains full message/event history
- a user can capture viewport context and screenshots into a thread
- selected and visible part context is automatically included with chat turns
- draft preview operations appear as structured thread events
- accepted drafts link to source patch, generated source, validator stub,
  acceptance manifest, and source-loop commands
- focused validator results and profile summaries can be attached to the thread
- `flow model` can configure the active provider/model through a Hermes-style
  provider setup flow
- LlamaStudio and LM Studio are both first-class local provider options
- a streaming assistant can use the thread context and call CAD-safe tools
  through the selected provider profile
- no chat path mutates project source, exports, reports, or handoff bundles
  without the existing reviewable source-loop boundary

## Recommended Next Step

Keep `docs/PERFORMANCE.md` pointed at this plan and
`docs/ProviderSupport.md`. Start with the persisted design-thread contracts and
the `flow model` provider scaffold before doing more UI polish. Persistence,
context snapshots, and provider configuration are the foundation; chat streaming
should sit on those contracts rather than becoming another transient command
surface.
