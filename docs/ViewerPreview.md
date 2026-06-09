# Viewer Preview Work Plan

Date: 2026-06-09

## Purpose

Viewer preview is the draft-loop workbench for Flow CAD. It should let a user
select a part, describe a simple change, see draft geometry before project source
changes, inspect measured facts and warnings, and accept the draft into reviewable
source-loop artifacts.

This work stream turns `docs/PERFORMANCE.md` item 6 from a list of desired
capabilities into small tickets with explicit verification. The scope is the
generic Flow CAD viewer/runtime. Project repos still own product-specific
geometry rules, mating contracts, validator content, and print intent.

## Current Baseline

Already implemented:

- Viewer backend draft endpoints for boxes, holes, counterbores, slots, louver
  patterns, mirroring, measurements, preview STEP export, transactions,
  acceptance artifacts, and discard.
- MCP draft tools that call the same `DraftGeometryStore` service.
- Draft transaction acceptance that writes review artifacts under
  `.flow/draft-transactions/<token>/accept/` without mutating `flow/`, `exports/`,
  `reports/`, or handoff bundles.
- Focused validator support for draft transactions through `flow validate run
  panel-basic --draft-transaction <token>`.
- Browser selection, source context, STEP-backed snap feature loading, mesh
  warnings, and parts inspector metadata.

Resolved by this work stream:

- The browser can display a transaction preview mesh from the draft STEP
  artifact as a first-class model.
- The viewer has selected-part command context payloads that combine part id,
  placement, source context, local frame, geometry facts, and warnings.
- Constrained natural-language commands are converted into proposed draft operations in
  the viewer loop.
- Proposed operations, before/after facts, warnings, generated review artifacts,
  and patch previews are presented in one preview session.
- Source-loop follow-up commands are surfaced from the accepted draft.

## Target Workflow

The first-class preview loop should be:

1. Select one registry part in the viewer.
2. Open the command pane with selected-part context already populated.
3. Enter a constrained panel command, such as:

   ```text
   Make this a 120 x 45 x 3 mm panel, add two M4 clearance holes 12 mm from the
   front edge, and put five louvers on the outside face.
   ```

4. Review proposed draft operations before mutation.
5. Apply the proposal to a draft transaction.
6. Preview the draft mesh in the viewer beside or in place of the selected part.
7. Inspect dimensions, feature facts, warnings, changed operations, and artifact
   paths.
8. Accept the transaction into review artifacts.
9. Run the focused source loop against the accepted draft transaction.

## Non-Goals

- Hidden source mutation or automatic patch application.
- Project-specific command interpretation for robot hardware rules.
- Replacing the full handoff gate.
- Treating STL-only mesh input as exact editable geometry.
- Building the orientation cube from item 7 in this work stream, except for
  exposing enough selected-part frame data for the later cube.

## Ticket Plan

### VP-1: Define Viewer Preview Session Contract

Goal: Create the shared vocabulary for a viewer preview session.

Requirements:

- Define typed payloads for selected-part context, draft preview session,
  proposed operation, draft fact summary, preview model metadata, acceptance
  artifact summary, and source-loop follow-up commands.
- Keep the contract generic: no robot-specific dimensions or hardware rules.
- State geometry authority for every current and draft artifact.
- Include warnings for mesh-only, missing source, approximate measurement, and
  unsupported command syntax.
- Document the contract in this file and in API type comments.

Verification:

- TypeScript type checks cover the viewer contract.
- Python tests assert backend JSON payload keys and geometry authority labels.
- `docs/PERFORMANCE.md` item 6 links here instead of carrying vague prose.

### VP-2: Serve Draft Preview Display Meshes

Goal: Let the browser load a draft transaction preview as a displayable STL mesh
without making it a handoff export.

Requirements:

- Add viewer backend endpoints that turn a draft transaction preview STEP into a
  cached display STL under project local state.
- Return a preview model URL, source STEP path, display STL path, dimensions,
  feature facts, warnings, and geometry authority.
- Reuse the existing STEP-to-STL converter and cache freshness pattern where
  practical.
- Keep all draft preview outputs under `.flow/`.
- Do not add draft previews to registry parts, active cache, exports, reports, or
  handoff bundles.

Verification:

- `python -m pytest tests/test_viewer_service.py -k draft_transaction_preview`
- A test proves the display STL path is under `.flow/` and not under `exports/`.
- A test proves stale display meshes are refreshed after draft changes.

### VP-3: Add Selected-Part Preview Context

Goal: Make the viewer command pane deterministic by fetching context instead of
asking an LLM to infer it.

Requirements:

- Add a backend context endpoint for a selected part.
- Include part id, module id, family, version, role, material, artifact paths,
  occurrences, active assembly id, geometry authority, capabilities, warnings,
  source context availability, snap-feature summary, and local/project frame
  placeholders.
- Include current mesh or STEP-derived dimensions when available, clearly labeled
  by authority.
- Return a stable error for missing or mesh-only exact-editing context.

Verification:

- `python -m pytest tests/test_viewer_service.py -k selection_context`
- Tests cover STEP-backed, STL-only, and missing-artifact parts.

### VP-4: Build A Constrained Command-To-Operations Adapter

Goal: Convert the first benchmark panel command into explicit draft operations
without pretending to solve arbitrary CAD language.

Requirements:

- Add a small parser for constrained panel commands covering dimensions, thickness,
  M-size or numeric clearance holes, edge offsets, mirrored/two-hole patterns, and
  simple louver counts.
- Return a proposed operation list and unsupported-intent warnings before applying
  anything.
- Keep the parser deterministic and testable; future LLMs can call it or replace
  it with structured operations.
- Reject ambiguous face language unless the selected-part context can resolve it.

Verification:

- Unit tests cover the benchmark command and at least three rejection cases.
- Tests prove proposal generation is side-effect free.

### VP-5: Apply Proposals To Draft Transactions

Goal: Turn reviewed proposed operations into draft transaction mutations.

Requirements:

- Add a backend apply endpoint that accepts structured operations, creates or
  updates a draft transaction, and returns the updated session payload.
- Record operation history in transaction state.
- Include before/after dimensions, feature counts, hole centers, and warnings.
- Preserve discard semantics for unaccepted transactions.

Verification:

- `python -m pytest tests/test_draft_geometry.py tests/test_viewer_service.py -k preview`
- Tests prove applying a proposal produces the expected draft facts and no source
  writes.

### VP-6: Add Viewer Command Pane

Goal: Put the preview workflow in the browser where the selected part is already
visible.

Requirements:

- Add a command pane integrated with current part selection.
- Show selected part id, placement summary, local/project frame summary, current
  dimensions, source authority, and warnings.
- Let the user enter the constrained benchmark command.
- Show proposed operations before apply.
- Provide apply, preview, accept, discard, and reset actions with clear disabled
  states.
- Keep controls compact and workbench-like; do not turn the viewer into a landing
  page or a tutorial screen.

Verification:

- `npm --prefix viewer/stl-viewer test -- App.test.tsx`
- Tests cover selected-part context fetch, proposal display, apply action, disabled
  states, and warnings.

### VP-7: Render Draft Preview Models In The Scene

Goal: Make draft geometry visually inspectable immediately.

Requirements:

- Load the preview model URL returned by the backend into the existing STL viewer
  pipeline.
- Mark preview models as draft geometry with distinct color and warnings.
- Allow showing preview with neighboring selected parts.
- Keep registry part models and draft preview models separate in state.
- Clear stale preview models on discard, accept, backend reload, or selected-part
  change.

Verification:

- `npm --prefix viewer/stl-viewer test -- App.test.tsx`
- Tests prove preview models are passed to `Viewer`, use draft metadata, and are
  removed after discard/accept.

### VP-8: Add Preview Inspector Facts

Goal: Make preview review fact-based instead of visual-only.

Requirements:

- Show draft dimensions, bounding box, feature list, hole centers, warnings,
  operation history, preview STEP path, display mesh path, and geometry authority.
- Show current-vs-draft differences for dimensions and feature counts.
- Show acceptance artifact paths after accept.
- Keep source patch contents in the source/review surface, not hidden.

Verification:

- Frontend tests assert inspector content from mocked backend payloads.
- Backend tests assert accepted transaction artifact summaries.

### VP-9: Connect Accepted Drafts To The Focused Source Loop

Goal: After acceptance, tell the user and agents exactly what to run next.

Requirements:

- Return source-loop commands from the preview session:
  `flow validate run panel-basic --draft-transaction <token>`, then the relevant
  touched-part build and source validator commands when a source patch is applied.
- Expose generated source path, validator stub path, source patch path, and
  acceptance manifest path.
- Do not apply the patch automatically.

Verification:

- Backend tests assert command strings and artifact paths.
- Frontend tests show accepted artifacts and source-loop commands.

### VP-10: Add End-To-End Benchmark And Gate Proof

Goal: Prove item 6 works as a repeatable, independently verifiable workflow.

Requirements:

- Add a documented benchmark using the rectangular panel command from
  `docs/PERFORMANCE.md`.
- Time the draft preview loop and record whether it meets the less-than-10-second
  target on a normal local run.
- Run focused validation on the accepted draft transaction.
- Run the viewer test suite and Python tests that cover the backend contract.

Verification:

- `python -m pytest tests/test_draft_geometry.py tests/test_viewer_service.py`
- `python -m pytest tests/test_mcp_server.py tests/test_focused_validators.py`
- `npm --prefix viewer/stl-viewer test`
- A benchmark note in this file records command, elapsed time, and pass/fail.

## Subagent Work Packets

The work can be delegated safely when each worker owns a disjoint write set:

- Backend preview worker: VP-2, VP-3, VP-5, VP-8 backend fields, VP-9 backend
  fields. Owns `src/flow_cad/viewer/`, `src/flow_cad/draft_geometry.py`, and
  `tests/test_viewer_service.py`.
- Command adapter worker: VP-4. Owns a new parser module under `src/flow_cad/`
  and focused parser tests.
- Frontend preview worker: VP-6, VP-7, VP-8 frontend. Owns
  `viewer/stl-viewer/src/` files only.
- Verification worker: VP-10. Owns benchmark notes and may run tests, but should
  not change runtime code unless assigned a specific failing test.

The project manager reviews all worker diffs, resolves integration issues, runs
the full relevant gates, and keeps hidden source mutation out of scope.

## Completion Criteria

Item 6 is complete only when:

- The viewer can create or update a draft transaction from a selected part.
- The viewer can display draft preview geometry before project source changes.
- The viewer shows selected-part context, proposed operations, current-vs-draft
  facts, warnings, preview artifacts, and acceptance artifacts.
- Accepted drafts produce reviewable source-loop artifacts without mutating
  project source.
- The focused source-loop command for the accepted draft is visible and works.
- Tests prove filesystem boundaries, backend contracts, frontend state behavior,
  and the benchmark panel workflow.
- `docs/PERFORMANCE.md` remains a summary pointer to this work plan.

## Status

- VP-1: Complete. Shared backend/frontend payloads cover selected context,
  proposed operations, preview models, acceptance artifacts, patch previews, and
  source-loop commands.
- VP-2: Complete. Draft transaction preview models are served from `.flow/` via
  `/api/draft-transactions/{transaction_token}/preview-model` and
  `/api/draft-transactions/{transaction_token}/model`.
- VP-3: Complete. `/api/parts/{component_id}/preview-context` returns selected
  part metadata, source availability, snap summary, dimensions, project/local
  frame placeholders, and mating-contract metadata.
- VP-4: Complete. `flow_cad.preview_commands.parse_panel_command()` parses the
  benchmark command into side-effect-free operations with warnings and
  assumptions.
- VP-5: Complete. The viewer applies proposed operations through draft
  transaction endpoints and keeps discard/accept semantics intact.
- VP-6: Complete. The browser viewer has a command pane tied to current
  selection, proposal review, apply, preview, accept, discard, and reset.
- VP-7: Complete. Preview models load through the existing STL viewer path as
  distinct draft geometry and clear on discard, accept, reload, or selection
  change.
- VP-8: Complete. The pane shows current and draft dimensions, deltas, facts,
  warnings, artifacts, source-loop commands, and a source patch preview.
- VP-9: Complete. Accepted drafts return source-loop commands and reviewable
  artifact paths without applying patches.
- VP-10: Complete. Verification on 2026-06-09:
  - `python -m pytest`: 115 passed, 4 warnings.
  - `npm --prefix viewer/stl-viewer test`: 46 passed.
  - `npm --prefix viewer/stl-viewer run build`: passed, with the existing Vite
    chunk-size warning.
  - `git diff --check`: passed.
  - Draft preview benchmark:
    `python -m pytest tests/test_viewer_service.py::test_viewer_backend_exposes_draft_transaction_preview_model -q --durations=1`
    reported a 0.15s test call and 1.35s total run, under the 10s draft preview
    target.
