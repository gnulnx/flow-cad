---
name: flow-cad-project
description: Use inside Flow CAD initialized projects for CAD source edits, build and viewer refreshes, generated export handoffs, placement-aware reviews, and project validator workflow.
---

# Flow CAD Project Workflow

Use this skill after the project `AGENTS.md` for non-trivial work in a repo
initialized by `flow init`.

## Core Rules

- Edit project source in `flow/`; do not hand-edit generated files in `exports/`
  or local runtime state in `.flow/`.
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
python -m pytest
flow cad build
python -m flow.validators.project
```

Run additional project-specific validators documented in the local `AGENTS.md`,
`docs/PART_INTERFACES.md`, or project-local skills.
