<p align="center">
  <img src="docs/logo.svg" alt="Flow CAD Logo" width="600">
</p>

# Flow CAD

Flow CAD is a reusable project-local CAD workbench. It provides the `flow` CLI,
project bootstrap, STEP/STL export plumbing, active-cache metadata, report
generation, reusable skills, and a source-backed browser viewer for Flow CAD
projects.

Robot or product geometry does not live in this runtime repo. Downstream
projects, such as `/home/gnulnx/b3_robot`, own their own `flow/` source tree,
print intent, validators, generated exports, and project-local skills.

## Setup

Use Python 3.11 or newer. A local virtual environment is recommended:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

For a runtime-only editable install without test dependencies:

```bash
python -m pip install -e .
```

After changing this checkout, reinstall it editable in any downstream project
you want to test:

```bash
python -m pip install -e /home/gnulnx/flow-cad
```

## Initialize A Project

Create a new Flow CAD project layout in an existing repo:

```bash
flow init
```

`flow init` creates a project manifest, `flow/` source layout, docs stubs, local
runtime directories, and a `skills/` directory. Bundled reusable skills from
this repo's `skills/` directory are copied into the project.

## Project Workflow

Run these commands from a Flow CAD project repo, not necessarily from this
runtime repo.

Run a default build:

```bash
flow cad build
```

Start the source-backed browser workbench:

```bash
flow start
```

`flow start` runs the viewer API and frontend, scans for nearby free ports when
the preferred ports are busy, and opens the browser by default. Use
`--no-open-browser` for server-only startup. Agent/model defaults resolve from
`~/.flow/config.toml` and project-local `.flow/config.toml`; if no runtime is
configured and the local `codex` CLI is available, `flow start` selects Codex for
the viewer process.

Ask a running workbench to refresh project source, registry, geometry, and cache
state:

```bash
flow reload
```

Query generated project cache state:

```bash
flow registry list
flow registry show <component_id>
```

## CLI Reference

Flow CLI commands are available from a project checkout:

```bash
flow --help
flow init [--force]
flow start [options]
flow reload [--backend-url <url>]
flow refresh [--project-root <path>] [--part <part_id>] [--force-model-refetch]
flow registry list|show <component_id>
flow cad --help
flow cad build [options]
flow cad profile [options]
```

### Core `flow` commands

- `flow init --force`
  Initialize or overwrite starter files for a project.

- `flow start [--backend-host HOST] [--backend-port PORT] [--frontend-host HOST]
  [--frontend-port PORT] [--port-search-span N] [--open-browser/--no-open-browser]`
  Start the workbench.

- `flow reload [--backend-url http://127.0.0.1:8000]`
  Ask the running viewer to refresh project state.

- `flow refresh [--project-root PATH] [--part PART_ID] [--force-model-refetch]`
  Refresh the project-aware live viewer process and print rendered artifact
  identity for the selected part or all parts.

- `flow registry list`
  Print active cache entries.

- `flow registry show <component_id>`
  Print one cached component detail record.

### `flow cad build` options

- `--profile <all|active|<version-id>>`
  Select which part profile to build. Default: `all`.

- `--part <part_id>`
  Build one part only (direct part exports).

- `--changed`
  Rebuild parts that changed since last build metadata.

- `--assembly-preview`
  Refresh assembly + placement artifacts for viewer updates without handoff packaging.

- `--handoff`
  Enforce strict release build behavior (bundle, cache update, reports, STL,
  snapshots, and assembly enabled).

- `--stl/--no-stl`, `--snapshots/--no-snapshots`, `--reports/--no-reports`,
  `--bundle/--no-bundle`, `--cache/--no-cache`
  - Control optional export/report/cache stages.

- `--snapshots-only`
  Regenerate only SVG snapshots.

Important: `--part`, `--changed`, `--assembly-preview`, and `--handoff` are
mutually exclusive. `--handoff` also enables `--bundle`, `--cache`, `--stl`,
and `--reports` even if disabled in the same command.

### `flow cad profile`

- `flow cad profile --last`
  Show the latest build profile summary.

- `flow cad profile --json`
  Emit raw profile JSON.

- `flow cad profile --limit N`
  Show only the top `N` slow profile events.

## Viewer

The current browser viewer lives in `viewer/stl-viewer/` and is launched by
`flow start`. The FastAPI backend under `src/flow_cad/viewer/` provides project
parts, display meshes, source context, capabilities, and STEP-derived snap
features.

Flow CAD uses a STEP-first authority model:

- STEP-backed project parts expose exact topology, exact snap targets, and exact
  measurement inputs.
- STL-only uploads are viewable and measurable as mesh-only approximate
  geometry.
- Capability labels from the backend define what the viewer may safely promise.

## Agent Skills

Flow CAD is intended to support LLM-first CAD workflows. Reusable skills that
apply to every initialized Flow CAD project belong in this repo under `skills/`,
and `flow init` copies them into project repos.

Project-local skills belong in the project repo when they encode robot, fixture,
product, customer, material, printer, or hardware-specific contracts.

Use this split:

- Put reusable build/viewer/cache/export/validator workflow in Flow CAD skills.
- Put project-specific geometry, print, hardware, and validator contracts in the
  project repo's `skills/`.
- When a local skill becomes broadly useful across Flow CAD projects, promote it
  back to this repo and update `flow init` coverage/tests.

## Development

Run the Python test suite from this repo:

```bash
python -m pytest
```

Run the viewer frontend tests:

```bash
npm --prefix viewer/stl-viewer test
```

Build the viewer frontend:

```bash
npm --prefix viewer/stl-viewer run build
```

Optional machine-specific tool paths can be set in the environment or in a local
`.env` copied from `.env.example`:

- `FREECAD_CMD`
- `TEXT_TO_CAD_ROOT`
- `TEXT_TO_CAD_PYTHON`

See `AGENTS.md` for the agent operating guide and ownership rules.
