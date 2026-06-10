# Performance And Iteration Plan

Date: 2026-06-08

## Purpose

Flow CAD should feel like a design tool, not a batch compiler. This document
starts the performance and iteration plan for making common CAD changes fast
enough to explore, inspect, correct, and promote without waiting on the full
handoff pipeline for every design question.

The immediate benchmark is intentionally simple: create or modify a rectangular
panel with thickness, holes, and optional side features. That should not require
a 25 minute feedback loop.

The target is to separate Flow CAD work into three loops:

- Draft loop: see and measure a simple geometry change in 1 to 10 seconds.
- Source loop: promote an accepted change into editable source and focused tests
  in less than 1 minute.
- Gate loop: run the full build, exports, viewer cache refresh, reports,
  project validators, and tests before handoff.

Simple part work should live mostly in the draft and source loops. The gate loop
should stay strict, but it should not be the default exploratory loop.

## Problem Statement

The current workflow makes small CAD edits too expensive:

1. Ask for a simple part, such as a rectangular panel.
2. Wait for source edits, broad build work, export refresh, viewer refresh,
   validators, and tests.
3. Inspect the result and discover one orientation, hole, clearance, or face
   detail is wrong.
4. Repeat.

That is not a design flow. It is a batch compile loop.

The full production pipeline is correct for handoff because generated artifacts
must remain coherent: STEP/STL exports, active viewer cache, snapshots, reports,
project manifests, assembly placements, and validators all need to agree. It is
too heavy for first-pass geometry exploration.

## Where The Time Goes

A simple panel is not hard CAD. The slow loop is mostly systems latency:

| Stage | Why It Expands | Faster Path |
| --- | --- | --- |
| Intent parsing | The agent has to infer frames, mating parts, source ownership, and project intent from files. | Viewer selection should provide part id, frame, dimensions, placement, and known interfaces automatically. |
| Source editing | The first visible result requires editing Python generators instead of making a temporary primitive. | Draft geometry transactions should preview boxes, holes, slots, and patterns before source changes. |
| Build/export | A small edit can trigger broad rebuilds, STEP/STL export refresh, reports, and cache updates. | Touched-part and draft-only build profiles should run first; full handoff build runs later. |
| Validation | Broad validators and full assembly checks answer too much during early iteration. | Fast project or part-family validators should answer the immediate question in seconds. |
| Viewer review | The viewer often waits on regenerated artifacts and manual reload/review. | The viewer should preview draft geometry directly and show measured facts in the inspector. |
| Direction language | "Front", "back", "outside", and "left" can mean different things in global, assembly, and part-local frames. | A shared orientation cube should make the project frame and selected-part local axes visible in the viewer. |
| Agent serialism | One worker inspects, edits, builds, validates, and summarizes in sequence. | A project-director workflow should delegate narrow read, test, validator, and profiling subtasks to local workers. |

The first profiler must separate these clocks:

- Agent/context time.
- CAD kernel generation time.
- Export time.
- Viewer/cache time.
- Validator/test time.
- Manual review time.

If the CAD kernel only spends a small part of the total time on rectangular
geometry, then the fix is not "make rectangles faster." The fix is to avoid
running the whole production pipeline for every design question.

## Principles

- Python/build123d source remains first-class production source for generated
  parts.
- STEP remains the exact handoff and review format.
- STL and browser display meshes are view-only approximations.
- Draft geometry is allowed, but it must be labeled as draft until promoted.
- Fast paths must produce facts, not vibes: bounding boxes, hole centers,
  normals, wall thickness, mating clearances, and changed part ids.
- The full gate should stay strict and reproducible.
- Every recurring slow path should turn into a tool, validator, or skill.
- Flow CAD should own reusable workbench/runtime capabilities; project repos
  should own project-specific geometry, dimensions, validators, and print intent.

## Part 1: Improve Iteration Speed

### 1. Add Build Timing And Trace Output

Flow CAD needs a profile for every build:

- Part generation time by part id.
- STEP export time by part id.
- STL export time by part id.
- Snapshot/report generation time.
- Viewer cache update time.
- Assembly placement time.
- Validator time by validator.
- Interference or collision check time and pair count.
- Test timings when launched through Flow CAD.
- Cache hit/miss reason for every skipped or rebuilt artifact.

Useful commands:

```bash
flow cad profile
flow cad build --profile <build-profile>
flow cad profile --last
```

The output should make the slowest five operations obvious.

The implemented build-profiler contract is documented in
`docs/FlowCadProfiler.md`.

### 2. Split Build Profiles

The standard command remains:

```bash
flow cad build
```

But it should not be the only loop. Flow CAD needs explicit profiles:

```bash
flow cad build --part <part-id>
flow cad build --changed
flow cad build --assembly-preview
flow cad build --handoff
```

Suggested meanings:

- `--part`: build one part and its direct facts.
- `--changed`: rebuild only changed source dependencies.
- `--assembly-preview`: refresh placements and viewer cache without handoff
  packaging.
- `--handoff`: strict full build behavior for release/export review.

Build control flags can still be combined with any profile mode:

- `--stl/--no-stl` (default `--stl`)
- `--snapshots/--no-snapshots` (default `--snapshots`)
- `--reports/--no-reports` (default `--reports`)
- `--bundle/--no-bundle` (default `--bundle`)
- `--cache/--no-cache` (default `--cache`)
- `--snapshots-only` (snapshot-only regeneration)

Mode flags are mutually exclusive, and `--handoff` enforces the strict full
build behavior used for release/handoff workflows.

Project handoff commands should still run the full build and validators.
Interactive work should start smaller.

#### Foundation Readiness Before Step 3

Before starting the draft geometry operation API, the first two steps must leave
a reliable fast-loop foundation:

- [x] Build profiles are mutually exclusive and `--handoff` forces the strict
  release gate behavior.
- [x] `--changed` records cache-hit events instead of failing when everything is
  already current.
- [x] `--changed` uses current parameter snapshots as rebuild inputs, not only
  part source mtimes.
- [x] `--changed` can rebuild one touched part while recording cache hits for
  untouched parts.
- [x] `--snapshots-only` does not regenerate STEP or STL artifacts.
- [x] Viewer-cache and interference phases measure the actual work they report.
- [x] Regression tests cover the cache-hit, touched-source, parameter-change,
  snapshot-only, and profile-phase contracts.

### 3. Add A Draft Geometry Operation API

Simple panels should not require an agent to hand-write a new Python generator
before the user can see anything.

Flow CAD should expose draft operations through MCP and the viewer backend. A
minimum draft-only panel API could be:

```text
create_box_part(id, length, width, height, material, role)
set_panel_thickness(part_id, thickness)
add_hole(part_id, face, x, y, diameter, through=true)
add_counterbore(part_id, face, x, y, diameter, depth)
add_slot(part_id, face, x, y, length, width, angle=0)
add_louver_pattern(part_id, face, count, pitch, width, height, angle)
mirror_features(part_id, source_face, target_face)
measure_part(part_id)
export_draft_step(part_id)
```

For a basic panel, the draft interaction should be close to:

```text
create_box_part(length=120, width=45, height=3)
add_hole(face="top", x=12, y=8, diameter=4.2)
add_hole(face="top", x=108, y=8, diameter=4.2)
measure_part()
```

The API should return:

- Draft part token.
- Bounding box.
- Feature list.
- Hole centers and axes.
- Minimum wall/edge distances where available.
- STEP path for preview.
- Warnings for likely print or assembly problems.

Only after the user accepts the draft should Flow CAD generate or patch editable
source.

The initial draft-only operation API is documented in
`docs/DraftGeometryAPI.md`. This covers draft box/panel creation, thickness
changes, holes, slots, basic counterbores, louver-pattern slots, feature
mirroring, measurements, preview STEP export, viewer-backend routes, and MCP
tools while keeping draft artifacts isolated under project-local runtime state.
Transactions, viewer UI editing, and source promotion remain later steps.

Direct `promote_draft_to_source(part_id, target_file)` is intentionally not part
of the draft-only API. Promotion belongs behind transaction `accept()` and the
Phase 3 source-promotion tools, where Flow CAD can generate reviewable source
patches instead of hidden project-source mutations.

### 4. Use Geometry Transactions

Draft operations should be grouped into a transaction:

```text
begin_draft(part_id="panel_left")
create_box(...)
add_hole(...)
add_louver_pattern(...)
preview()
accept()
```

Until `accept()`, the transaction lives in local runtime state. It can be
discarded without touching project source or generated exports.

When accepted, Flow CAD can produce a source patch plus a focused validator
stub. The agent or user reviews the patch, applies it, and runs the source loop.

The initial transaction API is documented in `docs/DraftGeometryAPI.md`. It
supports begin, transactional box creation, feature edits, measurement, preview,
discard, and accept. Acceptance writes a reviewable source patch, generated part
source, validator stub, and acceptance manifest under project-local runtime
state without modifying project source or generated exports.

### 5. Create Focused Validators For Common Part Families

Full assembly checks are gates. They are not the right first check for every
part edit.

Focused validators need a real framework, not a pile of one-off scripts. The
work plan is documented in `docs/FocusedValidators.md`.

The runtime goal is to make focused validators:

- structured: stable metadata, issue schemas, expected/actual values, units, and
  coordinates
- fast: runnable outside the full handoff gate
- profiled: visible through the same profiler used for build/export/cache timing
- reusable: backed by Flow CAD helper APIs for cache, STEP, draft, transaction,
  and placement facts
- project-owned where appropriate: product dimensions, hardware rules, print
  intent, and mating contracts stay in project repos

The initial implementation should land as ticketed work:

- shared validator schema and report normalization
- focused validator runner and `flow validate` CLI
- profiler integration for standalone and handoff validator events
- common fact providers for cache, STEP, draft transactions, and placements
- first-class rectangular panel validator family
- placement/neighbor-review helper patterns
- starter project templates and reusable agent guidance
- MCP list/run tools for structured validator reports

Item 5 is complete only when the benchmark panel can be validated in seconds,
slow validator work is explained by `flow cad profile`, and new projects receive
the documented validator pattern through `flow init`.

### 6. Make Viewer Preview First Class

The viewer-preview roadmap is broken into verifiable tickets in
`docs/ViewerPreview.md`.

That plan covers:

- selected-part preview context
- constrained command-to-operation proposals
- draft transaction application and immediate preview display
- preview inspector facts, warnings, and current-vs-draft deltas
- acceptance into reviewable source-loop artifacts
- focused validator and benchmark proof

Item 6 is complete only when the viewer can display draft geometry before
project source changes, show the selected-part context and draft facts that led
to that preview, accept the draft into review artifacts without hidden source
mutation, and prove the benchmark panel flow through backend, frontend, and
focused-validator tests.

### 6A. Add Persistent Design Threads And Viewport-Aware Chat

The viewer-preview command pane is useful as a deterministic operation surface,
but it is not enough for real design review. Flow CAD also needs persistent
project design threads that preserve the conversation, viewport context,
screenshots, annotations, draft transactions, validation results, accepted
artifacts, and source-loop commands that led to a change.

The work plan is documented in `docs/CodexViewerReworkPlan.md`.

This work should provide value before any local model or streaming assistant is
integrated. The first useful slice is a real chat/history workspace that records
manual design notes, viewport context, screenshots, draft events, validator
events, profile summaries, and accepted artifact links. The assistant runtime is
a later layer on top of that persisted work context.

The early workbench slice covers:

- project-local design thread persistence under `.flow/design-threads/`
- context snapshots that combine camera, visible parts, selected parts,
  measurements, draft state, active assembly, backend revision, and authoritative
  backend facts
- a left-dock `Source | Chat` tab set so source review remains available while
  Chat becomes the normal design-review workspace
- screenshot capture and annotation attachments tied to thread context, with
  Chat owning attachment/reference history and `Edit > Annotate` owning the
  viewport drawing tools
- durable visual evidence artifacts for agent/manual-render views, with the
  contract in `docs/VisualEvidence.md`
- manual visual evidence uses a separate browser render context with named view
  presets instead of reading from the user's active viewport canvas
- draft preview, accept, discard, focused-validator, and profile events recorded
  into the thread history

The later assistant slice covers:

- a runtime-neutral streaming assistant adapter with CAD-safe tools rather than
  broad shell or filesystem access
- PS-0 from `docs/ProviderSupport.md`: a narrow Codex runtime bridge spike using
  the user's existing Codex auth before the broader provider framework
- a Hermes Agent style model-provider setup layer, documented in
  `docs/ProviderSupport.md`, so Flow CAD has a durable foundation without
  taking on Hermes-scale provider parity
- first-class LlamaStudio and LM Studio local-provider integrations without
  treating either one as the entire architecture
- first-class support for OpenAI, Gemini, local/OpenAI-compatible endpoints, and
  OpenRouter, with Anthropic treated as beta until there is a validation path

Item 6A is complete only when the viewer has a real chat interface with durable
history, can automatically attach full work context to a design turn, can retain
visual review evidence through screenshots, annotations, and agent/manual render
artifacts, and can show the draft/validator/source-loop evidence behind accepted
changes after reload.

### 7. Add A Shared Orientation Cube

Some of the slow loop is miscommunication, not validation. The viewer should
include a small orientation cube, similar in spirit to FreeCAD's navigation cube,
that both the user and the agent can refer to.

The cube should be project-aware:

- The project coordinate frame should be visible.
- Faces should have human labels, not only axis letters.
- Labels should be configurable from the project manifest when a project has
  domain-specific language such as front/rear/top/bottom.
- The UI should state whether each label maps to positive or negative X/Y/Z.
- The cube should be clickable for camera snaps.
- The cube should stay visible during part selection and draft preview.
- The selected part should be able to show its local axes next to the project
  cube.

A manifest-level sketch of this configuration could look like:

```yaml
viewer:
  coordinate_frame:
    x_positive: right
    x_negative: left
    y_positive: front
    y_negative: rear
    z_positive: top
    z_negative: bottom
```

This should reduce prompts like "put holes on the outside face" turning into a
wrong-face rebuild. A good LLM command pane can quote the same orientation state
before applying a draft operation:

```text
Selected part: panel_left
Project face requested: left
Part-local face resolved: rear
Operation: add_louver_pattern(...)
```

The cube is a performance feature because it shortens the human-agent feedback
loop before code changes, builds, or validators run.

### 8. Define Time Budgets

Initial targets:

- Draft box or panel creation: less than 2 seconds.
- Add or edit a simple hole pattern: less than 2 seconds.
- Draft STEP preview: less than 10 seconds.
- Focused part-family validator: less than 10 seconds.
- Promote accepted draft to source and rebuild touched part: less than 60
  seconds.
- Full handoff gate: allowed to take longer, but it must be profiled and
  predictable.

The key target is this: a user should be able to make, inspect, and correct a
simple part without waiting for the full gate.

## Part 2: Foreman Process For Hermes And Local Models

The assistant should act as a project director, not a single serial worker. That
requires durable subprocess contracts.

### Brownian Bridge Directed Goals

Use Brownian bridge directed goals for exploration:

- Start point: the current repo state and known constraints.
- End point: a concrete target artifact and acceptance test.
- Bridge anchors: small intermediate artifacts that must be true.
- Randomness: allow local exploration between anchors.
- Direction: every probe is conditioned on reaching the end point.

For CAD work, the bridge might be:

1. Identify the fixed part, moving part, slide direction, capture direction, and
   proud direction.
2. Extract current geometry facts.
3. Create a draft primitive or feature edit.
4. Run focused validators.
5. Preview with neighboring parts.
6. Promote to source.
7. Run the gate.

The local model can explore implementation details between anchors. It should not
be allowed to redefine the destination.

### Worker Task Shape

Hermes or a local model such as qwen3.6 should receive small work packets:

```text
Objective:
  Add a focused validator that checks panel louver orientation.

Allowed files:
  flow/validators/
  tests/

Forbidden:
  Do not edit generated exports.
  Do not edit Flow CAD runtime unless this packet explicitly allows it.
  Do not change part geometry.

Commands:
  python -m pytest tests/test_panels.py -q
  python -m flow.validators.check_panel_features

Evidence required:
  File paths changed.
  Validator output.
  Test output.
  Remaining uncertainty.
```

The project director reviews the worker output, applies or rejects patches, and
decides whether to run the next bridge anchor.

### Good Subtasks For Lower-Tier Models

Good:

- Read one generator and summarize dimensions.
- Add a focused regression test from an explicit expected value.
- Write a validator that checks one named contract.
- Compare two generated metadata files.
- Produce a timing table from build logs.
- Draft an MCP schema from an existing Python helper.

Risky:

- Broad architecture rewrites.
- Silent changes to project contracts.
- Multi-repo runtime changes.
- Geometry edits without a stated local frame.
- Handoff export changes without full gate validation.

### Project Director Checklist

Before delegating:

- State the exact end artifact.
- State the files the worker may edit.
- State the commands the worker must run.
- State what evidence counts as done.
- State what must not be touched.

After receiving work:

- Inspect the diff.
- Run the relevant commands locally.
- Promote repeated knowledge into a project skill or Flow CAD skill.
- Keep project-specific knowledge in the project repo.
- Keep reusable runtime knowledge in Flow CAD.

## MCP Roadmap

### Phase 1: Read-Only Facts

Add MCP tools that answer without changing source:

- `list_parts`
- `get_part_metadata`
- `get_part_bbox`
- `get_part_features`
- `get_part_placement`
- `measure_between_parts`
- `profile_last`
- `visual_evidence_list`
- `visual_evidence_get`
- `request_visual_evidence`
- `visual_evidence_requests_list`

This lets agents and local models inspect before editing.

### Phase 2: Draft Geometry

Add transaction-first draft tools as the default agent-facing path:

- `draft_begin_transaction`
- `draft_transaction_create_box`
- `draft_transaction_set_panel_thickness`
- `draft_transaction_add_hole`
- `draft_transaction_add_counterbore`
- `draft_transaction_add_slot`
- `draft_transaction_add_louver_pattern`
- `draft_transaction_mirror_features`
- `draft_transaction_measure`
- `draft_transaction_preview`
- `draft_transaction_accept`
- `draft_transaction_discard`
- `request_visual_evidence` for asking an active browser session to capture a
  named offscreen render without moving the user's viewport

These tools should write only local runtime draft state, temporary preview
artifacts, or thread-local visual evidence.

Direct `draft_*` primitives remain available only through the advanced MCP
toolset for debugging, tests, and power-user flows. The advanced toolset also
keeps `visual_evidence_create` for storing thread-local PNG evidence that an
existing renderer or browser session already produced. The default MCP toolset
should expose the transaction tools plus validator/profile and visual evidence
request/read tools so agents do not have to choose between duplicate direct and
transaction workflows or raw PNG upload paths.

### Phase 3: Source Promotion

Add controlled promotion tools:

- `draft_generate_source_patch`
- `draft_generate_validator`
- `draft_generate_test`
- `draft_accept_to_project`

Promotion should produce reviewable diffs, not hidden source edits.

### Phase 4: Model Provider Adapter For Design Threads

After persistent design threads exist, add a model-provider adapter that can use
read-only facts, draft transactions, focused validators, profiles, viewport
snapshots, and screenshot attachments from those threads. The assistant should
never need to guess the selected part, visible context, frame, measurements,
draft state, or accepted artifacts; the viewer and backend should attach those
facts automatically.

This phase should use the MCP/shared-service tools as the safe CAD operation
surface, but the user-facing experience is the project design thread, not a
single command box.

Provider setup is tracked in `docs/ProviderSupport.md`. The target is a
two-step path:

1. Run PS-0, a narrow Codex runtime bridge spike using the user's existing Codex
   auth and a compact CAD context packet.
2. Then build a Hermes-style `flow model` command with a deliberately small
   support promise: OpenAI, Gemini, LlamaStudio, LM Studio,
   local/OpenAI-compatible endpoints, OpenRouter, and beta Anthropic.

The config foundation now uses `FlowCadConfig` dataclasses backed by
`~/.flow/config.toml` or `$FLOW_CAD_HOME/config.toml` for user defaults and
project-local `.flow/config.toml` for overrides. Runtime code should pass this
resolved config object rather than partial provider/model fragments.

LlamaStudio is a first-class provider alongside LM Studio, not a generic
afterthought. Additional Hermes providers are out of scope for the first
production slice unless there is user demand and a validation path.

## Acceptance Criteria

The performance project is successful when:

- A simple rectangular panel can be drafted and previewed in less than 10
  seconds.
- A simple accepted panel edit can be promoted, rebuilt, and focused-tested in
  less than 1 minute.
- The full handoff gate remains strict and produces the same or better evidence
  than today.
- The build profiler identifies slow work by part and phase.
- The viewer can show draft geometry before project source is changed.
- The viewer has persistent design threads with message history, viewport
  context, screenshots, annotations, draft events, validator events, and accepted
  artifact links.
- `flow model` provides a Hermes-style provider setup experience with durable
  provider/model selection, model testing, capability metadata, first-class
  OpenAI/Gemini/LlamaStudio/LM Studio/local/OpenAI-compatible/OpenRouter
  support, and clear beta labeling for Anthropic until validated.
- Before `flow model` is broadened, the Codex bridge has been proved or rejected
  with evidence and, if successful, Codex is available as the first concrete
  design-thread runtime provider.
- The viewer has a project-aware orientation cube that makes configured
  front/rear/top/bottom labels and selected-part local axes visible.
- MCP tools can create boxes, holes, slots, and patterns as draft transactions.
- Local models can complete constrained subtasks without touching protected
  files or redefining the design target.

## Immediate Next Steps

1. Add build timing instrumentation in Flow CAD.
2. Add reusable helpers for focused part-family validators.
3. Prototype read-only MCP facts for part bbox, placement, and features.
4. Prototype draft box plus through-hole tools.
5. Add persistent design threads and viewport context snapshots.
6. Add a left-dock `Source | Chat` viewer workspace with real chat history.
7. Attach draft preview, validator, profile, screenshot, and accepted-artifact
   events to design threads.
8. Run PS-0 from `docs/ProviderSupport.md`: prove the local Codex runtime bridge
   can consume a CAD context packet using existing Codex auth.
9. If PS-0 succeeds, keep Codex as the first concrete design-thread
   `AgentRuntimeClient` provider.
10. Scaffold `flow model` provider support from `docs/ProviderSupport.md`,
   reusing Hermes Agent provider setup code where practical.
11. Add first-class provider adapters for OpenAI, Gemini, LlamaStudio, LM Studio,
   local/OpenAI-compatible endpoints, and OpenRouter.
12. Add Anthropic as beta only if it can be contract-tested and clearly labeled
    without implying full support.
13. Keep scoped provider declarations close enough to Hermes that future fixes
    can be manually cherry-picked without making automatic sync a first-pass
    requirement.
14. Add a small project-aware orientation cube to the viewer.
15. Add a worker-packet template for Hermes/local model subtasks.
16. Use the next simple panel change as the benchmark case.

The first benchmark should be concrete:

```text
Create a rectangular panel with length, width, thickness, two through holes, and
one side pattern. Preview it, measure it, promote it to source, rebuild only the
touched part, then run the focused panel validator.
```

If that path cannot complete in less than 1 minute, the profiler should explain
why.
