---
name: flow-cad-project
description: Use inside Flow CAD initialized projects for CAD source edits, build and viewer refreshes, generated export handoffs, placement-aware reviews, and project validator workflow.
---

# Flow CAD Project Workflow

Use this skill after the project `AGENTS.md` for non-trivial work in a repo
initialized by `flow init`.

## Core Rules

- Edit project source in `flow/`; do not hand-edit generated files in `exports/`
  or local runtime state in `.flow/`, except for intentional project-local
  runtime preferences in `.flow/config.toml`.
- Use `~/.flow/config.toml` for user-wide model/profile defaults and
  `.flow/config.toml` for project-local overrides. Do not store provider secrets
  or account tokens in project-local config.
- Keep reusable Flow CAD runtime/tooling changes in the Flow CAD source repo,
  then reinstall that runtime editable before verifying the project.
- Run `flow cad build` before viewer review or handoff. It refreshes STEP/STL
  exports, reports, snapshots when enabled, handoff bundles when enabled, and
  the active cache used by the viewer.
- If multiple parts must appear together in the viewer, model their placements
  in the project assembly source and add a focused validator or test.
- Update the project mating-interface docs when a durable fit, placement, or
  hardware-access contract changes.
- Update the project print manifest when printable/reference/inspection handoff
  intent changes.

## Normal Checks

Prefer focused tests or validators first, then broaden:

```bash
flow validate list
flow validate run panel-basic --part <part-id>
python -m pytest
flow cad build
python -m flow.validators.project
```

Run additional project-specific validators documented in the local `AGENTS.md`,
`docs/PART_INTERFACES.md`, or project-local skills.

Use `flow validate run <validator-id> --json` when an agent needs structured
issue coordinates, expected/actual values, or profiler-visible focused checks.
Keep robot-specific dimensions and hardware contracts inside project validators;
Flow CAD supplies the reusable runner, fact providers, and generic panel/
placement helpers.

## Agent Screen Review

When an agent needs to inspect the current Flow CAD browser view, use the
project-local agent screen path instead of guessing from stale screenshots:

1. Call MCP `agent_screen_request` for the active project.
2. Wait briefly for the running browser workbench to fulfill the request.
3. Call MCP `agent_screen_latest` and open the returned `image_url` or stored PNG
   metadata.

This is explicit viewport capture, not ambient desktop capture. It writes under
`.flow/agent-screen/` and should not affect exports, reports, handoff bundles,
or project source.
