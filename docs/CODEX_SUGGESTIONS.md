# Erb CAD Project: Operating Improvements and Technical Debt Plan

Generated: 2026-05-18

## Executive Summary

The project is productive but operating more like an active design notebook than a software project. That is fine for early mechanical discovery, but it is now expensive: each CAD change causes Codex to reread a large context file, reason through a 2,046-line generator, remember which validation scripts matter, regenerate many artifacts, and then explain the same workflow again.

The right next move is not a broad rewrite. The right next move is to put a professional operating layer around the current workflow:

- one portable workflow that runs on workstation or laptop;
- one command that validates the design before print handoff on any machine;
- a small pytest suite for cheap geometry invariants;
- a print handoff manifest for Bambu Studio and cross-machine transfer;
- a lean Codex/agent instruction file so future sessions stop burning tokens rediscovering the project;
- a slower modular refactor only after the current generator is protected by tests.

QWEN's document correctly identifies the main pain points: monolithic CAD source, no unit-test infrastructure, hardcoded export lists, and too much manual validation. Its proposed full package rewrite is directionally reasonable but too aggressive for the current moment. This repo needs guardrails first, architecture second.

## Current State

### What Is Working

- `cad/erb_lower_chassis.py` is a real production source of truth. It builds parts, assembly occurrences, STEP exports, and a dimensional report.
- There are already meaningful validation scripts:
  - `scripts/check_assembly_interference.py`
  - `scripts/check_mounting_features.py`
  - `scripts/report_axle_insert_dimensions.py`
- Existing reports show the current assembly has zero reported solid overlaps and multiple packaging checks pass.
- STEP files stay in `exports/step/`, which is the correct handoff surface for Bambu Studio.

### What Is Costing Time and Codex Credits

- The main generator is a 2,046-line monolith. Codex must repeatedly search inside one large file to answer narrow questions.
- The initial `pyproject.toml` and pytest scaffold now exist; the next step is expanding coverage from path/tool discovery into CAD invariants.
- Validation exists, but it is script-based rather than a single obvious command.
- `scripts/sync_text_to_cad.py` and `scripts/sync_esp32_to_text_to_cad.py` duplicate workflow logic and hardcode STEP lists.
- Generated artifacts, `.pyc` files, `.DS_Store`, FreeCAD backups, STEP sidecars, 3MFs, and source files are mixed together in the tracked tree.
- FreeCAD scripts use macOS paths such as `/Applications/FreeCAD.app/...`, while this workstation checkout is under Linux. That makes the repo harder to operate consistently across workstation and laptop.
- There is no print-release manifest saying which STEP files are actually intended for Bambu Studio today.

## First Principles

This is a physical robot CAD project. The professional flow should optimize for:

1. **Traceability:** know which source generated which STEP files.
2. **Cheap checks first:** catch dimensional and connectivity mistakes before opening FreeCAD or Bambu Studio.
3. **One authoritative source:** the repo generates CAD with repo-relative paths; the workstation is the normal heavy-work machine, but the laptop can still check out, run Codex, generate, validate, and iterate.
4. **Small context for agents:** future Codex sessions should start from a concise workflow contract, not the whole design diary.
5. **No architecture heroics before tests:** refactor only after the existing behavior is pinned by validation.

## Recommended Project Shape

Keep the current generator in place initially, but add this operating layer:

```text
3DPrintBalanceBot/
├── AGENTS.md                    # Short Codex/Qwen operating instructions
├── CODEX_SUGGESTIONS.md         # This proposal
├── PRINT_MANIFEST.md            # Current Bambu handoff list and notes
├── pyproject.toml               # pytest + tooling config
├── cad/
│   ├── erb_lower_chassis.py     # Current production generator
│   └── ...
├── scripts/
│   ├── validate_all.py          # One validation entrypoint
│   ├── print_bundle.py          # Copy selected STEP files to a dated handoff folder
│   ├── sync_text_to_cad.py
│   └── ...
├── tests/
│   ├── test_params.py
│   ├── test_part_registry.py
│   ├── test_mounting_invariants.py
│   └── test_print_manifest.py
├── exports/
│   ├── step/                    # Generated STEP artifacts
│   └── print_bundles/           # Dated laptop/Bambu handoff folders
└── reports/
```

## Immediate Changes I Would Make

### 1. Add `AGENTS.md`

This is the highest leverage Codex-credit fix.

It should be short, maybe 80-120 lines, and say:

- The repo is authoritative; workstation is the normal heavy-generation machine, and laptop must remain a supported checkout.
- For active geometry facts, inspect `cad/erb_lower_chassis.py` and current reports first.
- Before any printable change, run the validation command.
- Never edit generated STEP/3MF files by hand.
- Keep Bambu handoff as exported artifacts and dated bundles, while still allowing laptop-side source iteration when dependencies are configured.
- Prefer updating concise current docs or manifests over creating long historical narratives.

This will reduce repeated agent rediscovery more than a `SKILL.md` alone. A Codex skill is useful later if the workflow becomes reusable across repos, but this repo first needs local operating instructions.

### 2. Add Portable Path and Environment Handling

The project should not depend on `/home/gnulnx/...`, `/Users/jfurr/...`, or `/Applications/FreeCAD.app/...` being true. Those are machine facts, not project facts.

Recommended approach:

- Derive project paths from `Path(__file__).resolve().parents[...]`.
- Use environment variables for external tools:
  - `TEXT_TO_CAD_ROOT`
  - `TEXT_TO_CAD_PYTHON`
  - `FREECAD_CMD`
- Support an ignored local config file such as `.env` or `.erb-cad.local.toml`.
- Keep a committed example file such as `.env.example`.
- Fail with clear messages when an optional external tool is missing.

Example `.env.example`:

```bash
# Optional. Defaults should work if text-to-cad is under ~/BLR/text-to-cad.
TEXT_TO_CAD_ROOT=~/BLR/text-to-cad
TEXT_TO_CAD_PYTHON=~/BLR/text-to-cad/.venv/bin/python

# Optional. Set per machine if FreeCAD exports are needed.
FREECAD_CMD=/path/to/freecadcmd
```

The repo should work in three modes:

- **Core mode:** generate STEP files and run Python validations.
- **Viewer mode:** additionally mirror to text-to-cad if configured.
- **FreeCAD mode:** additionally export `.FCStd` files if `FREECAD_CMD` exists.

This lets the workstation stay the main place for long CAD work while still letting the laptop check out the repo, run Codex, make a quick change, regenerate the relevant STEP files, and continue.

### 3. Add One Validation Command

Create `scripts/validate_all.py` or a `Makefile` target that runs the project checks in the right order:

```bash
python cad/erb_lower_chassis.py
python scripts/check_mounting_features.py
python scripts/check_assembly_interference.py --no-overlap-steps
```

FreeCAD-only checks should be optional because they are environment-specific. The key is that Codex and the user both have one command to trust before print handoff on either machine.

### 4. Add Minimal pytest Coverage

Do not start by moving files. Start by testing the current file.

Good first tests:

- `build_parts()` returns every name expected by `PART_FILENAMES`.
- every exported printable part fits the declared printer envelope.
- active assembly occurrences refer to valid part keys.
- service-fit shelf reliefs do not create a disconnected shelf layout.
- front/rear panel retention holes stay at the top-only Z level.
- bottom tray mount Y/Z axes match side-plate holes.
- print manifest files exist in `exports/step/`.

These tests will be much faster than full STEP generation and will stop future agents from breaking known mechanical contracts.

### 5. Create `PRINT_MANIFEST.md`

The laptop can operate from a full checkout, but it should not need to guess which files are print candidates. It should also be able to receive a small dated bundle and a note when the workstation produced the artifacts.

Example:

```text
Print bundle: exports/print_bundles/2026-05-18-service-shelf-fit/

Send these to Bambu Studio:
- erb_lower_chassis_left_side_plate.step
- erb_lower_chassis_right_side_plate.step
- erb_lower_chassis_front_panel.step
- erb_lower_chassis_rear_panel_detachable_body.step
- erb_lower_chassis_rear_panel_detachable_bumpout.step
- erb_lower_chassis_bottom_tray.step
- erb_equipment_shelf_service_fit.step
- erb_axle_insert_medium.step

Do not print:
- reference wheel/axle files
- assembly STEP
- top dome prototypes unless doing visual fit only
```

That one file will prevent a lot of “which STEP is current?” discussion.

### 6. Clean Generated and Local Junk Policy

The repo currently tracks Python bytecode and includes local artifacts such as `.DS_Store`, FreeCAD backups, STEP sidecars, and large slicer files. Some generated artifacts are useful to track, but the policy should be explicit.

Recommended policy:

- Track source Python, docs, validation reports, and selected current STEP outputs.
- Do not track `__pycache__`, `.pyc`, `.DS_Store`, swap files, viewer sidecars, or FreeCAD `.FCBak` backups.
- Treat `.3mf` as handoff artifacts. Track only intentional named snapshots, not every temporary slicer file.
- Add `.gitignore` and then clean tracked junk in a separate commit.
- Ignore `.env` and `.erb-cad.local.toml`; commit only example config files.

### 7. Stop Duplicating Export Lists

There are now multiple places that need to know the active STEP set. That causes misses.

The current generator already has `PART_FILENAMES`, `REFERENCE_FILENAMES`, and insert variants. Use those as the source for:

- STEP export;
- viewer sync;
- print manifest validation;
- tests.

Avoid blind auto-discovery as the default. It will copy stale experiments and legacy parts. Better approach: central explicit registry, then derive commands from it.

## Medium-Term Refactor

After the validation layer exists, refactor the monolith in small slices.

### Phase 1: Extract Constants and Registry

Move only these first:

- `ChassisParams`
- `PART_FILENAMES`
- `REFERENCE_FILENAMES`
- insert variant metadata
- printer envelope constraints

Target:

```text
erb_cad/
├── params.py
├── registry.py
└── validation.py
```

Keep `cad/erb_lower_chassis.py` importing from that package. Do not move geometry yet.

### Phase 2: Convert Validators Into Library Functions

Keep command-line scripts, but make them thin wrappers around importable functions. Then pytest can call the same checks without subprocess overhead.

Target:

```text
erb_cad/checks/
├── mounting.py
├── interference.py
├── upper_stack.py
└── axle_insert.py
```

### Phase 3: Extract One Part Family

Extract shelves first. They are small, variant-heavy, and have already caused disconnected-geometry risk.

Do not extract every part at once. A full architecture migration before tests would burn more credits than it saves.

### Phase 4: Split the Big Generator

Only after tests pass:

```text
erb_cad/parts/
├── side_plate.py
├── panels.py
├── bottom_tray.py
├── shelves.py
├── axle_insert.py
└── upper_blockout.py
```

The goal is not pretty modules. The goal is faster targeted changes with less context loading.

## Tool Calling and Agent Workflow

The current workflow is expensive because an agent has to infer the task graph each time. Fix that with explicit commands and short files.

### Add These Commands

```bash
python scripts/validate_all.py
python scripts/print_bundle.py --name service-shelf-fit
python -m pytest
```

Optional convenience targets:

```bash
make generate
make validate
make test
make bundle NAME=service-shelf-fit
make sync-viewer
```

Each command should be path-portable. If a command needs a non-repo dependency, it should discover it in this order:

1. explicit CLI argument;
2. environment variable;
3. ignored local config file;
4. common platform defaults;
5. clear error with the exact variable to set.

### Add `AGENTS.md` Sections

Recommended headings:

- Project Purpose
- Current Source of Truth
- Standard Commands
- Print Handoff Rules
- Validation Rules
- Files Not To Edit Directly
- How To Inspect Current State

### When a Codex Skill Makes Sense

A repo-local `AGENTS.md` should come first. A separate Codex `SKILL.md` is worth creating only if you want this CAD-agent workflow reusable beyond this repo.

If you do create a skill, it should not contain all project history. It should teach the procedure:

- inspect current manifest;
- read active generator/registry;
- make minimal geometry change;
- run validation;
- update print manifest;
- summarize changed STEP files.

## Workstation to Laptop/Bambu Flow

The clean operating model:

1. The git repo is portable and can be checked out on workstation or laptop.
2. Workstation is the normal heavy CAD generation and validation machine.
3. Laptop can still run Codex, edit source, generate STEP files, and validate when dependencies are installed or configured.
4. `scripts/print_bundle.py` creates a dated folder under `exports/print_bundles/` for Bambu Studio transfer.
5. The bundle contains only the STEP/3MF files intended for Bambu Studio plus a small manifest.
6. Any slicer changes that matter get recorded back into `PRINT_MANIFEST.md` or a dated print note.

This keeps CAD source control and slicer experimentation separate without making the laptop a second-class checkout.

## QWEN Document Assessment

### Good Calls

- It correctly calls out the monolithic generator.
- It correctly calls out missing unit tests.
- It correctly identifies hardcoded sync lists as a maintenance issue.
- It correctly suggests validating shelf connectivity as code.

### Weak Calls

- It jumps too quickly to a large package rewrite.
- It implies auto-discovery of all STEP files is inherently better. In this repo, that could copy stale alternates, reference geometry, and experiments into the active workflow.
- It treats pre-commit hooks as an immediate answer. For CAD, pre-commit can become annoying if it runs heavy generation every time. A manual `validate` command plus lightweight pytest is a better first step.
- Some example details are stale relative to current code, such as the service-fit shelf slot discussion.

## Proposed First Week

1. Add `.gitignore`.
2. Add `AGENTS.md`.
3. Add `.env.example` and optional local-config loading.
4. Replace hardcoded FreeCAD/text-to-cad paths with portable discovery.
5. Add `pyproject.toml` with pytest config.
6. Add `scripts/validate_all.py`.
7. Add `PRINT_MANIFEST.md`.
8. Add tests that import the current generator and validate registry/assembly invariants.
9. Run the full validation flow once on workstation and a lightweight validation flow on laptop.

That is the smallest change set that makes the project feel like software without disrupting the CAD work.

## Definition of Done for a Professional Print Iteration

A print iteration should end with:

- source change committed or clearly staged;
- STEP files regenerated;
- pytest passing;
- project validation passing;
- `PRINT_MANIFEST.md` updated if the print set changed;
- dated print bundle created for laptop transfer;
- short note explaining what changed mechanically and which files to slice.

Once that exists, Codex should spend tokens on actual design decisions instead of reconstructing the workflow every session.
