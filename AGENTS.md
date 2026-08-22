# Agent Operating Guide

This repository is the Flow CAD reusable workbench/runtime and public project
SDK. It owns the `flow` CLI, declarative manifest contract, project bootstrap,
SQLite lifecycle index, jobs, artifacts, viewer backend/frontend integration,
measurement, annotation, persistent chat/thread infrastructure, exporters,
generic validation, tests, docs, and reusable agent skills.

Product-specific CAD projects, such as `/home/gnulnx/b3_robot`, own their own
geometry source, parameters, registries, validators, generated exports, print
intent, and project-local skills. Do not put robot-specific geometry contracts
or print handoff facts in this runtime repo unless they are examples or fixtures.

## Rebuild Authority

The professional replacement contract is
`docs/FLOW_CAD_REBUILD_SPEC.md`. Read it completely before starting the Flow CAD
rebuild, changing project bootstrap behavior, or creating the `flow_b2`
downstream project.

- Treat the current implementation as a preserved reference, not as permission
  to copy its architecture into the replacement.
- Build the replacement on a dedicated rebuild branch and preserve the legacy
  baseline with an immutable tag.
- The user-created `git@github.com:gnulnx/flow_b2.git` repository is the only
  authority for `/home/gnulnx/flow_b2`. Clone it only when the replacement
  `flow init` contract is ready, then initialize it with that command.
- Never delete or rewrite `/home/gnulnx/b3_robot`. Its part source and generated
  artifacts are migration authorities and must be preserved byte-for-byte with
  SHA-256 and `cmp` verification.
- Enforce the Flow CAD/`flow_b2` ownership boundary in SDK imports and CI. Do not
  rely on this guide alone.
- Performance budgets in the rebuild specification are release gates. Any work
  exceeding one second needs visible feedback, and work exceeding ten seconds
  must be a cancellable background job.

## Project Relationship

- `flow-cad` owns reusable runtime/tooling: `flow` CLI, `flow init`, `flow sync`,
  `flow part`, build jobs, `flow start`, viewer services, exporters, indexes,
  reports, project loading, generic validators, and reusable skills.
- Flow CAD projects own their CAD source. A typical project has
  `flowcad.project.yaml`, a project-named Python package containing `params.py`,
  `parts/`, and `validators/`, plus `docs/`, `tests/`, generated exports, and
  ignored `.flow/` state. Projects do not define registries or build/viewer
  adapters.
- When debugging a project such as B3, edit project geometry in that project
  repo. Edit this repo only when the issue is generic Flow CAD runtime behavior.
- After changing this repo, reinstall it editable in downstream projects before
  verifying project behavior:

```bash
python -m pip install -e /home/gnulnx/flow-cad
```

## Source Of Truth

- Python package root: `src/flow_cad/`
- Public CLI entry point: `src/flow_cad/cli.py` via `flow`
- Public project API and manifest types: `src/flow_cad/sdk/`
- Replacement project bootstrap: `src/flow_cad/bootstrap.py`
- Replacement metadata index and lifecycle operations: `src/flow_cad/registry/`
- Byte-exact preservation primitives: `src/flow_cad/artifacts/`
- Downstream ownership enforcement: `src/flow_cad/validation/ownership.py`
- Build command implementation: `src/flow_cad/main.py`
- Preserved legacy project adapter: `src/flow_cad/project.py`; do not extend it
  for replacement manifest, bootstrap, or registry behavior.
- Flow CAD user/project runtime config model: `src/flow_cad/config.py`
- Core export, cache, report, snapshot, and metadata logic: `src/flow_cad/core/`
- Viewer API and STEP-first geometry authority: `src/flow_cad/viewer/`
- Browser viewer frontend: `viewer/stl-viewer/`
- Generic path/tool discovery: `src/flow_cad/paths.py`
- Reusable runtime skills: `skills/`
- Runtime tests: `tests/` and `viewer/stl-viewer/src/**/*.test.*`
- Architecture and workflow docs: `docs/`

### Replacement Architecture Map

```text
project geometry -> flow_cad.sdk -> manifest/index/build/artifact services
                                      -> thin viewer and application APIs
                                      -> isolated viewer feature stores
```

Downstream projects may import `flow_cad.sdk` and only explicitly approved
stable geometry helpers. They may never import registry, database, build,
viewer, export, validation, CLI, or other internal modules. List/query commands
are metadata-only and may not import or execute Build123d/OCP code.

This repo no longer owns active robot-specific modules such as
`src/flow_cad/params.py`, `src/flow_cad/registry.py`, or `src/flow_cad/parts/`.
If guidance refers to those as Flow CAD source of truth, treat it as stale.
Those files belong in downstream project repos.

## Standard Commands

Initialize a new Flow CAD project layout:

```bash
flow init
```

Rebuild the disposable metadata index and query lifecycle state:

```bash
flow sync
flow part list
flow part show <part_key_or_alias>
flow part rename <part_key_or_alias> <new_key>
flow part retire <part_key_or_alias>
```

Build a Flow CAD project from that project repo:

```bash
flow cad build
```

Start and reload the project-local workbench:

```bash
flow start
flow reload
flow refresh --part <part_id> --force-model-refetch
```

Query the preserved legacy build cache only when working on an unmigrated
legacy project:

```bash
flow registry list
flow registry show <component_id>
```

Run the fast replacement-foundation gate:

```bash
python -m pytest tests/foundation tests/test_artifact_preservation.py
```

Run Flow CAD Python tests from this repo:

```bash
python -m pytest
```

Run browser viewer tests from this repo:

```bash
npm --prefix viewer/stl-viewer test
```

Build the browser viewer:

```bash
npm --prefix viewer/stl-viewer run build
```

If the shell Python lacks test dependencies, use this checkout's virtualenv:

```bash
.venv/bin/python -m pytest
```

## Runtime Config

Flow CAD runtime configuration is represented by dataclasses in
`src/flow_cad/config.py` and should be passed as a `FlowCadConfig` object through
runtime code. Do not pass partial config fragments, loose provider dictionaries,
or one-off model settings through unrelated APIs.

- User defaults live in `~/.flow/config.toml`, or `$FLOW_CAD_HOME/config.toml`
  when `FLOW_CAD_HOME` is set.
- Project-local overrides live in `.flow/config.toml` under the Flow CAD project
  root.
- `FlowCadProject.paths.config` is the project-local config path and
  `FlowCadProject.config` is the resolved config object.
- Environment variables remain a temporary/CI escape hatch and should be folded
  into `FlowCadConfig` at the boundary.
- Secrets and OAuth tokens do not belong in project-local `.flow/config.toml`.
  Store only provider/profile selection and non-secret endpoint/model metadata
  there.

## Validation Rules

For any Python code change, run:

```bash
python -m pytest
```

For viewer/frontend changes, run the focused Vitest target when possible, then
the viewer test suite:

```bash
npm --prefix viewer/stl-viewer test
```

For CLI, viewer, project-loader, cache, export, or bootstrap changes, add or
update contract tests under `tests/` rather than relying on manual smoke checks.
For interaction behavior, prefer pure behavior tests that survive UI restyling
over assertions tied to button labels or layout structure.

If a downstream project is affected, reinstall Flow CAD editable and verify in
that project repo with its AGENTS guide and validators.

## Agent Screen Verification

For Flow CAD viewer work, agent-screen capture is a protected workflow.

When the user asks what is visible, points to an annotation, asks for screen
review, or says to verify the current viewer state, do not rely on offscreen
renders, metadata, old screenshots, or model assumptions.

Use the project-local `agent_screen_*` MCP path:

1. Call `agent_screen_request` for the active project root.
2. Wait for the running browser workbench to fulfill the request.
3. Call `agent_screen_latest`.
4. Open the stored `.flow/agent-screen/<capture-id>.png`.
5. Report only what is visible in that actual PNG.

The capture must preserve the live viewport camera and in-app annotation overlay.
`render_context: viewport-canvas` is the expected path for annotated screen
review. Offscreen rendering is only a fallback when the live canvas is missing or
blank, and must be called out explicitly.

Do not call viewer/screen verification complete unless the actual PNG has been
opened and inspected.

## Geometry Authority

Flow CAD is STEP-first for authoritative CAD data:

- STEP-backed parts expose exact topology, exact snap targets, and exact
  measurement inputs through the viewer API.
- STL-only inputs are mesh-only: viewing and approximate measurements are fine,
  but STL is not CAD-authoritative and must not be treated as exact editable
  geometry.
- The browser viewer should consume explicit capability labels from the backend
  instead of assuming STEP and STL have equivalent authority.
- Cache invalidation should account for source artifact freshness and contract
  metadata versions, not mtime alone.

## Path Rules

Keep this repo portable across workstation and laptop.

- Prefer repo-relative paths derived from `Path(__file__).resolve()`.
- Do not hardcode `/home/gnulnx/...`, `/Users/jfurr/...`, or
  `/Applications/FreeCAD.app/...` in new runtime code.
- External tool paths should come from CLI args, environment variables, ignored
  local config, or clear discovery.
- Useful environment variables include `FLOW_CAD_PROJECT_ROOT`,
  `VITE_FLOW_CAD_API`, `FREECAD_CMD`, `TEXT_TO_CAD_ROOT`, and
  `TEXT_TO_CAD_PYTHON`.
- If an optional dependency is missing, fail with a clear message explaining
  exactly what to install or which variable to set.

## Skill Ownership

This repo should grow reusable agent skills that make Flow CAD work reliable
across projects. Add or update a skill in `skills/` when the guidance is about
Flow CAD runtime/tooling behavior rather than one robot's geometry. The
replacement `flow init` keeps its scaffold minimal and does not copy runtime
implementation or skills into downstream repositories.

Put these in Flow CAD `skills/`:

- Build, export, viewer, reload, active-cache, and handoff workflow.
- Generic placement-review and validator patterns.
- Generic STEP/STL/manifest/cache troubleshooting.
- Reusable instructions for creating project validators.
- Cross-project CAD agent workflow that `flow init` should copy everywhere.

Put these in project-local `skills/`:

- Product or robot-specific part families and mating contracts.
- Project-specific coordinate conventions beyond the generic Flow CAD frame.
- Hardware-specific washer/nut/insert/sensor/actuator access rules.
- Print profiles, material choices, handoff bundles, and shop-specific checks.
- Repeated repair workflows whose facts live in that project source/docs.

When a local project skill becomes useful to multiple Flow CAD projects, promote
the generic portion into this repo's `skills/` and keep the project-specific
contract locally.

## Legacy And Cleanup Policy

This checkout has historically contained robot-specific experiments and older
standalone viewer/converter paths. Treat the current `src/flow_cad/` package,
`viewer/stl-viewer/`, `skills/`, `tests/`, and docs as authoritative for Flow
CAD runtime work.

Legacy code or generated artifacts should be removed or clearly archived when
they are no longer referenced by tests, CLI entry points, project bootstrap, or
documented workflows. Keep cleanup commits separate from runtime behavior
changes.

Do not hand-edit generated project outputs when fixing behavior. Fix the source
or generator, regenerate, and report what changed.

## Context Policy

Do not rely on historical narrative docs as current project state. Inspect
current source, tests, generated reports, manifests, and the downstream project
repo before changing behavior.

For most tasks:

1. Inspect current source and tests first.
2. Read `docs/GEOMETRY_FOUNDATION.md` for STEP/STL authority questions.
3. Read `docs/FlowArchitecture.md` for current viewer/runtime contracts.
4. Check downstream project AGENTS files before changing project-specific
   geometry or validation workflow.
5. Preserve concise updates. Avoid long running narratives unless the user asks
   for one.

## Change Style

- Keep changes small and mechanical.
- Prefer improving the current workflow before large refactors.
- Add tests/validators around existing behavior before extracting modules.
- Run the relevant test suite before reporting code changes as complete.
- Keep public commands top-level: `flow init`, `flow sync`, `flow part`, `flow
  cad build`, `flow start`, `flow reload`, and `flow refresh`. `flow registry`
  remains a legacy-cache command during migration.
- Keep generated caches, local runtime state, and dependency folders out of
  commits.
- Do not mix Flow CAD runtime changes and downstream project geometry changes in
  one commit.

## Git Hygiene

The working tree may contain user or other-agent changes.

- Do not revert unrelated changes.
- Do not delete untracked files unless the user asks.
- Treat agent-authored docs as user-visible work.
- Separate cleanup of tracked junk, generated files, or ignore rules into its
  own explicit commit when possible.
- Always commit every completed change before ending the task. Never leave this
  worktree with modified, staged, or untracked task files.
- Preserve pre-existing work; checkpoint it in an explicit commit instead of
  discarding it or leaving it dirty.
- When work spans Flow CAD and a downstream project, commit each repository
  separately with an ownership-appropriate message.
- Run `git status --short` after the final commit. A task is not complete until
  the output is empty.
