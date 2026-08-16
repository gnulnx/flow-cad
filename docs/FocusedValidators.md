# Focused Validators Work Plan

Date: 2026-06-09

## Purpose

Focused validators are the source-loop guardrails for Flow CAD projects. They
answer narrow geometry questions quickly enough to use during iteration, before
the full handoff gate runs.

This work stream turns ad hoc project validators into a reusable Flow CAD
validator framework with clear contracts, profiler visibility, project-local
extension points, and starter patterns for common part families.

## Scope

Flow CAD owns the reusable validator runtime:

- validator result schemas
- validator execution context
- CLI and MCP runner surfaces
- profiler integration
- starter templates copied by `flow init`
- generic helpers for cache, STEP, draft, and placement facts
- documentation, examples, and tests for the framework

Project repos own project-specific validator content:

- part-family dimensions and tolerances
- hardware clearances
- material and print-process rules
- mating-interface contracts
- protected bosses, shelves, tabs, captures, sensors, and actuator envelopes
- handoff-specific checks

Focused validators must not replace the handoff gate. They are fast checks for
source-loop confidence. Handoff still runs the full build, reports, cache,
exports, bundle, broad validators, project tests, and any project-specific gate
scripts.

## Target Workflow

A normal source-loop validator flow should look like this:

```bash
flow validate list
flow validate run panel-basic --part panel_left
flow validate run panel-basic --part panel_left --json
flow cad profile --last
```

After accepting a draft transaction:

```bash
flow validate run panel-basic --draft-transaction <transaction-token>
flow cad build --part panel_left
flow validate run panel-basic --part panel_left
```

For handoff:

```bash
flow cad build --handoff
flow cad profile --last
```

The profiler must make validator time and slow checks visible in the same place
as build/export/cache timings.

## Implemented Runtime Surface

The reusable runtime implementation lives under `src/flow_cad/validation/`:

- `contracts.py`: validator metadata, issue, report, severity, authority, and
  legacy-result normalization.
- `facts.py`: project definition, active-cache, STEP, draft, draft transaction,
  and viewer-placement fact providers.
- `panel.py`: the reusable `panel-basic` family helper.
- `placement.py`: generic placement/neighbor issue helpers.
- `runner.py`: focused validator discovery and execution for built-in and
  project-manifest validators.
- `cli.py`: `flow validate list` and `flow validate run`.

The MCP wrappers are in `src/flow_cad/mcp/server.py` as `validator_list`,
`validator_run`, and `profile_last`. New projects initialized with `flow init`
receive structured starter validators under `flow/validators/`.

## Validator Contract

Each focused validator has a stable id, a declared scope, and a structured
result.

Validator metadata:

- `id`: stable machine id, such as `panel-basic`
- `family`: part family or generic family, such as `panel`
- `description`: one concise sentence
- `mode`: `draft`, `source`, `cache`, `viewer`, or `gate`
- `inputs`: required facts, such as STEP, draft facts, active cache, placements
- `budget_ms`: expected runtime budget
- `tags`: `fast`, `source-loop`, `handoff`, `placement`, `print`, or project
  tags

Validator issues must be structured. Text-only failures are not enough.

Issue fields:

- `severity`: `error`, `warning`, or `info`
- `check_id`: stable check id
- `part_id`: part id when available
- `family`: part family when available
- `message`: human-readable summary
- `expected`: expected value or range
- `actual`: observed value
- `units`: units when numeric
- `point_mm`: coordinate of the issue when available
- `axis`: normal or direction vector when available
- `feature_id`: hole, slot, louver, or named feature when available
- `artifact_path`: source STEP, draft STEP, or cache artifact used
- `geometry_authority`: `step`, `draft`, `cache`, `mesh`, or `unknown`
- `remediation`: short suggested fix when obvious

Validator reports must include:

- validator metadata
- elapsed time
- input artifact summary
- issue counts by severity
- machine-readable issues
- warnings for degraded authority, missing cache rows, or approximate geometry

## Profiler Contract

Every validator run through Flow CAD must record profiler events.

Minimum event metadata:

- `validator_id`
- `family`
- `part_id` or `draft_token` when applicable
- `mode`
- `check_count`
- `issue_count`
- `error_count`
- `warning_count`
- `geometry_authority`
- `budget_ms`
- `over_budget`

Build-integrated validator events continue to use the `validator` phase. The
standalone runner should also write a profile file under `.flow/profiles/` so
`flow cad profile --last` can explain validator latency without requiring a
build.

Runtime targets:

- single simple panel validator: less than 2 seconds
- focused part-family validator with STEP/cache facts: less than 10 seconds
- placement validator with neighboring parts: less than 10 seconds
- full handoff gate validators: profiled, allowed to run longer

## Ticket Plan

### FV-1: Define Validator Schemas And Runtime Types

Goal: Create the shared contract for focused validator metadata, issues, and
reports.

Requirements:

- Add a runtime module for validator contracts under `src/flow_cad/`.
- Define typed structures for validator metadata, issue, report, and severity.
- Provide helpers for success, warning, error, and report serialization.
- Preserve compatibility with existing project validators that return lists,
  dicts, or empty results.
- Document the schema in this file and API doc comments.

Verification:

- Unit tests cover serialization, issue counts, empty reports, and compatibility
  coercion.
- Existing `python -m pytest` remains green.

Done means:

- Flow CAD can normalize any validator result into a structured report without
  losing existing behavior.

### FV-2: Build The Focused Validator Runner

Goal: Add a reusable runner that executes selected validators outside the full
handoff build.

Requirements:

- Add a runner service that loads the active project and validator registry.
- Support selecting validators by id, family, tag, part id, changed part, draft
  token, or draft transaction token where data is available.
- Keep validators pure by default: no source, export, report, cache, or handoff
  writes.
- Return structured reports and stable process exit codes.
- Keep existing handoff validator execution working.

Verification:

- Tests cover selection by id/tag/family/part.
- Tests prove no project source or exports are written by the runner.
- Tests prove existing project validators still run through `flow cad build
  --handoff`.

Done means:

- Runtime code can execute focused validators without invoking the whole build.

### FV-3: Add `flow validate` CLI

Goal: Make focused validators a first-class developer and agent command.

Requirements:

- Add `flow validate list`.
- Add `flow validate run <validator-id>` with `--part`, `--family`, `--tag`,
  `--draft-token`, `--draft-transaction`, `--json`, and `--profile`.
- Print concise human output by default.
- Emit full report JSON with `--json`.
- Use clear non-zero exit behavior for validator errors.
- Do not require heavy CAD evaluation when active-cache facts satisfy the
  validator input contract.

Verification:

- CLI tests cover list, run success, run failure, JSON output, missing
  validators, and missing project manifests.
- Tests prove commands are usable from a freshly initialized project.

Done means:

- A user can run one focused validator in seconds without using `flow cad build
  --handoff`.

### FV-4: Integrate Focused Validators With The Profiler

Goal: Make validator runtime cost visible and enforceable.

Requirements:

- Standalone validator runs write `.flow/profiles/latest-validator-profile.json`
  and update the standard latest profile view when appropriate.
- `flow cad profile --last` can show validator events from the latest build or
  standalone validator run.
- Each validator event includes the metadata in the profiler contract.
- Over-budget validators are marked in metadata and surfaced in summary output.
- `flow cad build --handoff` keeps validator timing in the build profile.

Verification:

- Tests cover standalone validator profile creation and profile summary output.
- Tests cover over-budget metadata without making tests timing-fragile.
- Regression test proves handoff validator events retain validator ids and
  issue counts.

Done means:

- If focused validation is slow, the profiler explains which validator/check is
  slow.

### FV-5: Add Fact Providers For Common Validator Inputs

Goal: Give validators stable access to compiled facts without duplicating path
and parsing logic.

Requirements:

- Provide helpers for active cache rows, project definitions, draft facts, draft
  transaction facts, STEP-backed bounding boxes, STEP snap/feature facts, and
  viewer placements.
- Mark geometry authority explicitly for every fact source.
- Prefer STEP and draft facts for exact geometry; treat STL/mesh as approximate.
- Fail with actionable messages when requested facts are stale or missing.

Verification:

- Tests cover cache-only, STEP-backed, draft, and missing-fact cases.
- Tests prove helper paths are project-relative and portable.
- Tests cover stale cache diagnostics.

Done means:

- Project validators can ask for common facts without hand-rolled file discovery.

### FV-6: Ship The Rectangular Panel Validator Family

Goal: Establish the first fully supported common part-family pattern.

Requirements:

- Add a reusable panel validator helper that can check:
  - bounding box dimensions
  - thickness
  - hole centers, axes, and diameters
  - minimum edge distances
  - slots and louver patterns by face
  - selected protected keep-out rectangles on a face
- Support draft transaction facts and source/STEP facts where possible.
- Return coordinates for every failure.
- Include tolerance handling and unit labels.

Verification:

- Tests cover passing and failing panel facts.
- Tests cover draft transaction acceptance output feeding the panel validator.
- Tests cover precise issue coordinates and expected/actual values.

Done means:

- The benchmark panel from `docs/PERFORMANCE.md` can be validated with one
  focused command.

### FV-7: Add Placement And Neighbor Review Validators

Goal: Cover the common case where a part is locally correct but placed or
reviewed incorrectly in the workbench.

Requirements:

- Add generic helpers for checking that a part appears in expected viewer or
  assembly placements.
- Support expected translation, rotation, visibility/default-review status, and
  neighboring part ids.
- Keep project-specific placement contracts in project validators, not this
  runtime repo.
- Return coordinate deltas and offending placement ids.

Verification:

- Tests use a starter project fixture with known placements.
- Tests prove missing, extra, and mispositioned placements produce structured
  issues.

Done means:

- Projects can write B3-style placement validators without duplicating the
  placement/report plumbing.

### FV-8: Add Scaffolding And `flow init` Templates

Goal: Make the recommended validator structure easy to copy into new projects.

Requirements:

- Update starter project validator files with the structured report pattern.
- Add a generated focused-validator example under `flow/validators/`.
- Add docs explaining where project-specific contracts belong.
- Update bundled skills if needed so agents prefer focused validators for
  repeated geometry contracts.

Verification:

- `flow init` tests cover copied validator templates.
- Starter project tests prove the example validator can run through
  `flow validate`.

Done means:

- New projects start with the focused-validator pattern instead of ad hoc
  scripts.

### FV-9: MCP Read/Run Validator Tools

Goal: Expose focused validators to agent workflows without shell parsing.

Requirements:

- Add MCP tools for `validator_list`, `validator_run`, and `profile_last`.
- Return bounded JSON reports.
- Enforce the same project-root policy as draft geometry tools.
- Do not expose broad hidden workflows through MCP; keep handoff as a CLI gate.

Verification:

- Fake FastMCP tests cover registration and forwarding.
- Filesystem-boundary tests prove read/run tools do not mutate protected paths.

Done means:

- An agent can inspect and run focused validators through MCP with structured
  results.

### FV-10: Performance Benchmark And Release Gate

Goal: Prove item 5 is complete against the iteration benchmark.

Requirements:

- Add a benchmark fixture for a rectangular panel with holes and one side
  pattern.
- Run the source-loop path: accept draft transaction, build touched part, run
  focused panel validator, inspect profile.
- Define pass/fail budgets in docs and tests where deterministic.
- Document manual benchmark commands for downstream projects.

Verification:

- Automated tests cover the deterministic parts of the benchmark.
- Manual command transcript in docs shows the intended loop.
- `flow cad profile --last` identifies validator time by validator/check.

Benchmark command transcript:

```bash
flow validate run panel-basic --draft-transaction <transaction-token> --json
git apply .flow/draft-transactions/<transaction-token>/accept/source.patch
# Register the reviewed generated part source in flow/assemblies/robot.py.
flow cad build --part benchmark_panel --no-stl --no-snapshots --no-reports
flow validate run panel-basic --part benchmark_panel --json
flow cad profile --last
```

The deterministic regression for this loop is
`tests/test_focused_validators.py::test_benchmark_panel_source_loop_accepts_builds_and_profiles`.
It accepts the benchmark panel transaction, applies the review patch, registers
the generated part, rebuilds only that touched part, runs `panel-basic` on the
draft and STEP-backed source paths, and asserts the focused validator and source
loop budgets.

Done means:

- A simple rectangular panel can be focused-validated in seconds, and slow
  validation is visible through the profiler.

## Completion Criteria For Item 5

Item 5 is complete when all of these are true:

- Focused validator schemas are implemented and documented.
- `flow validate` can list and run validators outside handoff builds.
- Validator runs produce structured reports and non-zero failures.
- Validator timing appears in profiler output.
- Common fact providers cover cache, STEP, draft, transaction, and placement
  inputs.
- A rectangular panel validator family exists with tests and draft/source-loop
  coverage.
- Starter project templates and docs teach the pattern.
- MCP tools can list/run focused validators with bounded JSON.
- The benchmark panel can be validated within the stated time budget.

## Non-Goals

- Do not move project-specific contracts into Flow CAD runtime.
- Do not make SQLite the source of geometry truth.
- Do not make focused validators silently rebuild or mutate project source.
- Do not replace the strict handoff gate.
- Do not require viewer UI automation for validator correctness.
