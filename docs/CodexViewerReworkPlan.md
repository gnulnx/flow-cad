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

### Chat Runtime

Add an internal interface instead of binding Flow CAD directly to one model
host:

```text
AgentRuntimeClient.stream_chat(thread_id, messages, context_packet, tools, model_profile)
```

The first implementation can be a local HTTP/SSE client that talks to a
LlamaStudio-compatible or llama.cpp-compatible server. The Flow CAD service
should own the CAD tool registry and should expose only safe Flow CAD tools:

- read current viewer/project facts
- create/update/discard draft transactions
- generate preview models
- run focused validators
- read profile summaries
- return source-loop artifact summaries

Do not expose LlamaStudio's generic `write_file` or shell `run_command` tools as
the default Flow CAD viewer assistant path. CAD edits should go through Flow CAD
draft, validation, and promotion services with the same filesystem boundaries as
the current MCP tools.

## LlamaStudio Reuse Decision

LlamaStudio is useful, but Flow CAD should not embed its current UI.

Reusable now:

- conversation/thread persistence concepts
- SSE event patterns for streaming text, reasoning, tool-call deltas, tool
  execution start/end, and end/error markers
- model/profile configuration ideas
- llama-server lifecycle handling
- tool-call loop with bounded iterations
- frontend stream rendering patterns for reasoning and tool blocks

Not directly reusable:

- the HTMX/template frontend, because Flow CAD's viewer is React/Three
- global active-conversation assumptions, because Flow CAD needs project-scoped
  design threads
- generic workspace file and shell tools, because Flow CAD needs CAD-specific
  operation boundaries
- a single `conversations.json` shape, because Flow CAD threads need screenshot
  attachments, context snapshots, draft transaction links, validator reports,
  and accepted artifact links

Recommended path:

1. Build the Flow CAD thread store and React chat UI natively.
2. Borrow LlamaStudio's SSE vocabulary and model/profile concepts where useful.
3. Add an adapter that can call a running LlamaStudio or llama.cpp-compatible
   server for streaming responses.
4. Only extract a shared BLR local-agent runtime after a second application
   needs the same code. The extraction target should be model lifecycle,
   streaming, tool-call orchestration, and profiles, not the Flow CAD thread
   schema or UI.

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

Capture viewport screenshots into thread attachments and store annotation JSON.
Start with screenshot capture plus note/circle annotations; arrows and richer
regions can follow.

Done means a user can attach the current viewport and a visual note to a design
thread.

### CVR-5: Draft And Validator Event Integration

Wire the existing preview, accept, discard, validator, and profile operations
into thread events.

Done means draft previews and focused-validation evidence are no longer hidden
inside transient UI state.

### CVR-6: Streaming Assistant Adapter

Add a runtime-neutral streaming adapter with fake-runtime tests first, then a
LlamaStudio or llama.cpp-compatible implementation. The adapter should receive
compact context packets and CAD-safe tool schemas.

Done means a thread can stream assistant output and tool events without giving
the assistant broad filesystem or shell access.

### CVR-7: LlamaStudio Shared Runtime Evaluation

After CVR-6 works locally, decide whether to extract shared code from
LlamaStudio. The extraction should be justified by real duplication between
Flow CAD and at least one other BLR application.

Done means there is either a small shared runtime package with tests or a
documented decision to keep the adapter boundary only.

## Risks And Mitigations

- Context bloat: summarize older turns and send only the latest relevant
  snapshots, selected parts, active draft state, and linked validator evidence.
- Stale geometry: include backend revision and artifact paths in every context
  snapshot; warn when a thread references older state.
- Hidden mutation: keep source changes behind accepted review artifacts and
  explicit source-loop commands.
- Screenshot trust: pair images with camera, visible part ids, selected ids, and
  backend facts so the assistant is not guessing from pixels alone.
- Model-host coupling: keep `AgentRuntimeClient` small and runtime-neutral.
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
- a streaming assistant can use the thread context and call CAD-safe tools
- no chat path mutates project source, exports, reports, or handoff bundles
  without the existing reviewable source-loop boundary

## Recommended Next Step

Update `docs/PERFORMANCE.md` to add item 6A and revise the MCP roadmap so the
viewer LLM interface is no longer just a late "pane that can call tools." Then
start CVR-1 and CVR-2 before doing more UI polish. Persistence and context
snapshots are the foundation; the chat UI and model adapter should sit on those
contracts rather than becoming another transient command surface.
