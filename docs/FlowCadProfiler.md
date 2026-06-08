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
- `report_generation`
- `active_cache_write`
- `handoff_bundle`

Skipped work is recorded as an event with status `skipped` and a reason. For
example, `flow cad build --no-snapshots` records skipped snapshot exports, and
`flow cad build --snapshots-only` records skipped STEP/STL exports.

Export events currently include cache metadata:

```json
{
  "artifact_cache_status": "rebuilt",
  "artifact_cache_reason": "full_build"
}
```

This reflects the current build behavior: Flow CAD does not yet have incremental
artifact cache hit/miss checks for exports.

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

The profiler covers the current build command. It does not yet launch project
validators, tests, viewer conversion, interference checks, or draft geometry
transactions. When those commands become Flow CAD entry points, they should use
the same profiler event model so `flow cad profile` can compare CAD kernel,
export, cache, validator, test, viewer, and review clocks in one place.

The profiler also reports all exports as rebuilt because the build pipeline does
not yet implement touched-artifact cache checks. Incremental build work should
replace that metadata with real hit/miss decisions and reasons.

## Test Coverage

Profiler behavior is covered by `tests/test_profiler.py`:

- JSON write/load and summary formatting.
- `flow cad build` integration on a starter project.
- `flow cad profile --last` and `flow cad profile --json`.
- Failed build profile writing.
