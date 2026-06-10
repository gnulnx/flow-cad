# Viewer Chat Triage

Date: 2026-06-10

## Scope

This is the working triage list for the 6A design-thread/chat smoke test in a
fresh Flow CAD project at `/home/gnulnx/flow_test` after `flow init` and
`flow start`.

The goal is to close the current gaps before calling `docs/PERFORMANCE.md` item
6A complete. The priority order below is based on the current user-visible
iteration flow, not implementation convenience.

## Current Smoke State

- Fresh project can start the viewer.
- User gets a default persistent design thread automatically when no thread
  exists.
- User can send a message without opening the thread drawer first.
- Chat stores user and assistant messages.
- Simple constrained plate/panel creation requests now create chat-linked draft
  transactions and preview geometry.
- Follow-up corner-hole requests now reuse the active draft transaction instead
  of starting an empty transaction.
- Annotated raised-wall requests now have a deterministic draft path that maps
  saved freehand annotation bounding boxes onto the draft top face and applies
  requested heights in annotation order.

## P0: Chat Composer Requires Manual Thread Creation

Status: Implemented, pending human smoke test in `/home/gnulnx/flow_test`.

Observation:

- In a clean browser, the chat composer is visible but unusable until the user
  manually creates a thread.
- This reads as broken input rather than a deliberate state.

Why it matters:

- The first-run experience should make chat feel like the normal design-review
  workspace.
- A disabled text box on an empty chat surface creates confusion before any CAD
  work starts.

Likely implementation area:

- `viewer/stl-viewer/src/App.tsx`
- `viewer/stl-viewer/src/components/DesignThreadDock.tsx`
- `src/flow_cad/viewer/threads.py`

Proposed fix:

- Auto-create and select a default design thread when the Chat tab opens and no
  active thread exists.
- Use a neutral generated title such as `Session <short-id>` or
  `<selected-part-id> <short-id>` when a part is selected.
- Keep rename/archive behavior unchanged.
- If backend auto-create fails, show a clear inline error and keep the composer
  disabled with an explicit reason.

Acceptance criteria:

- In a fresh `flow init` project, opening Chat creates or selects a current
  thread without requiring the `Threads` drawer.
- The composer accepts typing immediately.
- The created thread persists after browser reload.
- The user can rename the default thread.

## P0: Simple Chat Edits Do Not Create Draft Geometry

Status: Implemented for the deterministic plate/panel path, pending human smoke
test in `/home/gnulnx/flow_test`.

Observation:

- User prompt: `Please create a base plate that is 100mm x 100mm x 10mm thick`.
- Assistant response reported it could not create the draft because the Flow CAD
  draft transaction was cancelled.
- No draft preview, transaction state, or apply/accept flow appeared from the
  natural chat turn.

Why it matters:

- Item 6A is not just persistent chat. It must make the existing draft-preview
  work discoverable from the design-thread workflow.
- Simple panel/plate requests are the benchmark case for the performance plan.

Likely implementation area:

- `src/flow_cad/viewer/agent_runtime.py`
- `src/flow_cad/viewer/app.py`
- `src/flow_cad/viewer/threads.py`
- `viewer/stl-viewer/src/App.tsx`
- `viewer/stl-viewer/src/components/DesignThreadDock.tsx`
- Existing draft services in `src/flow_cad/draft_geometry.py` and
  `src/flow_cad/viewer/service.py`

Current architecture risk:

- Flow CAD exposes CAD-safe tool schemas to the assistant runtime, but the chat
  path still needs a reliable tool-execution loop or deterministic fallback that
  turns simple plate/panel requests into draft transactions.
- The advanced draft controls can apply proposals, but natural chat does not yet
  reliably drive that same draft transaction pipeline.

Proposed fix:

- Route simple plate/panel creation requests through the existing deterministic
  preview-command adapter before relying on a model tool call.
- When a prompt matches the constrained panel/plate grammar, create a proposed
  operation set, show it in thread history, and offer/apply a draft transaction
  through the same service used by the advanced draft tools.
- For model-driven tool calls, add a bounded executor that can run only the
  CAD-safe tools already listed for the chat runtime.
- Persist each step as thread events: propose, begin transaction, apply,
  preview, validate, accept/discard.

Implemented checkpoint:

- The non-streaming and streaming chat endpoints run the deterministic
  plate/panel adapter before the model runtime.
- Supported prompts append `propose`, `apply`, and `preview` draft events, link
  the draft transaction to the thread, and return the preview model payload.
- The viewer loads draft preview models referenced from chat history.
- The parser accepts dimensions written as `100mm x 100mm x 10mm thick`.

Remaining after P0:

- The bounded model tool executor is still P1/P1-adjacent work, not required for
  the deterministic P0 smoke path.
- Human browser smoke test still needs to confirm the `/home/gnulnx/flow_test`
  runtime behavior.

Acceptance criteria:

- In a fresh project, the prompt `create a 100 x 100 x 10 mm base plate`
  creates a draft transaction or proposed operation set without hidden source
  mutation.
- The user can preview the draft geometry from Chat.
- The thread records draft facts, warnings, preview artifacts, and source-loop
  commands.
- If the operation cannot be completed, the UI states the exact failed step and
  leaves a retry action.

## P0: Follow-Up Chat Edits Lost The Active Draft Context

Status: Implemented, covered by regression tests, pending human smoke test in
`/home/gnulnx/flow_test`.

Observation:

- A first chat turn could create a plate preview.
- A second turn such as `Place m5 holes in each corner 10mm from each side`
  failed because the draft operation was attempted against a new or empty draft
  transaction instead of the active chat-linked draft.

Why it matters:

- 6A is only useful if chat behaves like a persistent design session. The second
  edit is the core workflow, not an edge case.

Implemented fix:

- Chat context extraction now carries the active `draft_transaction_token` into
  deterministic preview-command parsing and application.
- Follow-up hole requests reuse the existing draft transaction and regenerate
  the preview model in-thread.

Acceptance criteria:

- Create a draft plate from chat.
- Send a second chat request for corner holes.
- The same draft transaction token receives four `add_hole` operations and the
  preview updates without falling through to the model runtime.

## P0: Annotated Follow-Up Requests Could Not Become Geometry

Status: Implemented as a bounded approximate adapter, covered by regression
tests, pending human smoke test in `/home/gnulnx/flow_test`.

Observation:

- A second turn asking the assistant to use the annotated view to create raised
  walls failed with a cancelled visual/tool path even though the UI had saved
  annotation points.

Why it matters:

- The new 6A agent-visible image/evidence capability is only valuable if common
  annotation-driven edits can become draft operations quickly.

Implemented fix:

- Added additive `raised_wall` draft features with preview geometry, transaction
  operations, API endpoints, feature payloads, and generated source on accept.
- Added a deterministic annotated-wall chat path for active draft transactions.
  It maps saved freehand annotation bounding boxes from normalized viewport
  coordinates onto the draft top face, then applies requested wall heights in
  annotation order.

Known limitation:

- The current mapping is an approximate viewport-bbox-to-top-face projection.
  It is good enough for fast preview iteration, but it is not exact camera-ray
  picking or topology-aware face projection yet.

Acceptance criteria:

- Create a draft plate from chat.
- Draw four rectangular freehand annotations on the visible top face.
- Send a second chat request for raised walls with four heights.
- The same draft transaction receives four `add_raised_wall` operations and the
  preview updates without waiting for model tool execution.

## P1: No Visible Thinking Or Progress Feedback While Chat Runs

Observation:

- After sending a chat message, the UI does not clearly show that the assistant
  is working.
- The send button text can change locally, but there is no durable in-thread
  pending assistant block, streamed progress, or tool status.

Why it matters:

- CAD actions can involve model streaming, context packing, visual evidence
  requests, draft operations, validation, and preview generation.
- Without progress feedback, users cannot tell whether the app is thinking,
  blocked, idle, or failed.

LlamaStudio precedent:

- `/home/gnulnx/LlamaStudio/app/chat.py` streams separate SSE payloads for
  `reasoning`, `content`, and `tool_call_delta`.
- `/home/gnulnx/LlamaStudio/app/templates/index.html` renders stream blocks for
  reasoning, text, running tools, and completed tool results.
- Flow CAD should reuse that interaction pattern conceptually: reasoning/tool
  progress is visible as a structured part of the conversation, not only hidden
  in logs or collapsed into a final assistant message.

Likely implementation area:

- `src/flow_cad/viewer/agent_runtime.py`
- `src/flow_cad/viewer/app.py`
- `viewer/stl-viewer/src/App.tsx`
- `viewer/stl-viewer/src/components/DesignThreadDock.tsx`

Proposed fix:

- Insert an optimistic assistant event immediately after the user message, such
  as `Thinking...` or `Preparing CAD context...`.
- Stream and render event blocks for:
  - reasoning/thinking text when the provider supplies it
  - assistant content deltas
  - tool calls
  - tool execution start/end
  - errors and cancellations
- Persist final reasoning/tool summaries in the design thread, with full
  reasoning retained only where the selected provider/runtime exposes it and the
  product policy allows it.

Acceptance criteria:

- Sending a message immediately creates a visible pending assistant block.
- Long turns show incremental updates.
- Tool calls show running/success/error state.
- Failures leave a visible error block in the thread.
- Reloading the thread shows the final assistant/tool evidence.

## P1: Reasoning And Tool Events Are Too Coarse

Observation:

- Flow CAD already has stream event types such as `assistant_delta`, `tool_call`,
  and `tool_result`.
- It does not yet have the same user-facing fidelity as LlamaStudio for
  reasoning blocks and tool-execution progress.

Why it matters:

- For CAD work, the user needs to know whether the assistant is interpreting
  context, asking for visual evidence, creating a draft, validating, or waiting
  for acceptance.

Proposed fix:

- Extend normalized stream events to include provider reasoning when available.
- Add explicit `tool_exec_start` and `tool_exec_end` style events for the
  bounded Flow CAD tool executor.
- Render these as compact, inspectable blocks in Chat.

Acceptance criteria:

- A model/provider that emits reasoning produces a collapsible reasoning block.
- Draft/visual-evidence/validator tool execution emits visible lifecycle events.
- The message history can distinguish assistant text from tool evidence.

## P2: Context Chips Can Report `Selected` But `Nothing Visible`

Observation:

- Screenshot shows `1 selected` and `nothing visible` at the same time.

Why it matters:

- The assistant receives context from these viewer facts.
- Contradictory chips reduce trust in the attached context packet.

Likely implementation area:

- `viewer/stl-viewer/src/App.tsx`
- `viewer/stl-viewer/src/components/DesignThreadDock.tsx`
- Viewer state/context construction around selected and visible part ids.

Proposed fix:

- Audit how `visiblePartIds` is computed for selected parts in a fresh project.
- If no explicit visibility list exists, fall back to currently loaded/displayed
  model ids.
- If the selected part is hidden, state that explicitly as `1 selected, hidden`
  instead of `nothing visible`.

Acceptance criteria:

- Fresh project viewer reports visible ids that match displayed models.
- Selected-visible contradictions are either eliminated or labeled clearly.
- Chat context packets match the displayed chips.

## Recommended Fix Order

1. Auto-create/select a default thread so the composer is usable immediately.
2. Add visible pending/streaming assistant feedback.
3. Make simple plate/panel chat requests route into the deterministic draft
   transaction pipeline.
4. Add richer reasoning/tool event rendering based on the LlamaStudio stream
   block pattern.
5. Fix selected/visible context chip consistency.

## Closeout Gate

Before marking item 6A complete:

```bash
.venv/bin/python -m pytest tests/test_viewer_design_threads.py tests/test_viewer_service.py tests/test_viewer_agent_runtime.py
npm --prefix viewer/stl-viewer test -- --run
npm --prefix viewer/stl-viewer run build
```

Manual smoke:

1. Start a fresh `flow init` project.
2. Open Chat and confirm a default thread exists.
3. Type immediately without opening the thread drawer.
4. Send `create a 100 x 100 x 10 mm base plate`.
5. Confirm visible thinking/progress.
6. Confirm draft transaction/proposal appears in the thread.
7. Preview the draft.
8. Reload the browser and confirm history, draft evidence, and visual evidence
   survive.
