# Flow CAD Profiler

Date: 2026-06-08

## Purpose

The Flow CAD profiler records where build time goes so the workbench can move
toward the iteration targets in `docs/PERFORMANCE.md`. The first implementation
profiles the existing `flow cad build` path without changing the artifacts that
build command produces.

Every build writes a structured JSON profile under the active project's local
state directory:

```text
.flow/profiles/latest-build-profile.json
.flow/profiles/build-profile-<timestamp>-<profile-id>.json
```

`latest-build-profile.json` is the stable path for humans, scripts, and future
MCP tools. The timestamped files preserve build history.

## Commands

Run a normal build:

```bash
flow cad build
```

The command records a profile automatically and prints the latest profile path
when the build succeeds.

Show the latest profile summary:

```bash
flow cad profile
flow cad profile --last
```

Show the raw profile JSON:

```bash
flow cad profile --json
```

Limit the slow-operation table:

```bash
flow cad profile --limit 10
```

## What Is Timed

The profiler records named events with a phase, label, duration, status, optional
part id, and metadata. The current build path records:

- `build_total`
- `params_load`
- `params_validation`
- `export_cleanup`
- `part_generation`
- `printability_check`
- `step_export`
- `step_normalize`
- `stl_export`
- `snapshot_export`
- `assembly_generation`
- `assembly_placement`
- `viewer_cache_update`
- `interference_check`
- `validator`
- `project_tests`
- `report_generation`
- `active_cache_write`
- `handoff_bundle`

Skipped work is recorded as an event with status `skipped` and a reason. For
example, `flow cad build --no-snapshots` records skipped snapshot exports, and
`flow cad build --snapshots-only` records skipped STEP/STL exports.
`flow cad build --changed` records cache-hit skip events for unchanged
artifacts, including successful no-op builds where every requested artifact is
already current.

Export and cache-hit events include cache metadata:

```json
{
  "artifact_cache_status": "rebuilt",
  "artifact_cache_reason": "full_build"
}
```

This reflects the current build behavior:

- `step_export` and `stl_export` include artifact cache status and reason.
- Skipped changed-mode artifacts are marked with cache hits and reason.
- Rebuilt artifacts include rebuild reasons such as `full_build`, `source_changed`, `artifact_missing`, or `artifact_stale`.
- Parameter snapshot changes are treated as rebuild inputs and reported as
  `params_changed`.

## JSON Shape

The top-level profile contains:

- `schema_version`
- `profile_id`
- `project_id`
- `project_root`
- `command`
- `build_profile`
- `started_at`
- `finished_at`
- `duration_ms`
- `status`
- `events`
- `summary`

Each event contains:

```json
{
  "phase": "step_export",
  "label": "example_block.step",
  "duration_ms": 42.0,
  "status": "ok",
  "started_at": "2026-06-08T12:00:00.000Z",
  "part_id": "example_block",
  "metadata": {
    "path": "exports/step/example/example_block.step"
  }
}
```

The summary contains phase totals and the slowest non-aggregate events. The
`build_total` event is kept in the raw events but excluded from the slowest list
because it would otherwise hide the actionable phase timings.

## Failure Profiles

If a build fails after the project has loaded, Flow CAD still writes a failed
profile. The failed event includes `error_type` and `error` metadata. This makes
early failures, such as an unknown build profile, visible through the same
latest-profile path.

## Current Limits

The profiler now captures:

- project build/test/profile phases
- cache hit/miss metadata for exports
- validator events (handoff only by default)
- pairwise interference checks
- viewer cache refresh timing

Draft geometry transactions are not yet covered by profiling here.

## Test Coverage

Profiler behavior is covered by `tests/test_profiler.py`:

- JSON write/load and summary formatting.
- `flow cad build` integration on a starter project.
- `flow cad profile --last` and `flow cad profile --json`.
- Failed build profile writing.
