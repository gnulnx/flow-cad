# Revert Chat Branch Audit

Date: 2026-06-11

## Scope

This document audits the current `performance` branch against local `main`.

Baseline:

- `main`: `bb2e28596433e458d40ff96c75f468f466cc5a16`
- `performance` HEAD: `3da66a335b127a6e29af754628d85eaa3bd0b352`
- Merge base: `bb2e28596433e458d40ff96c75f468f466cc5a16`
- Committed branch delta: 29 commits, 83 tracked file divergences, `34207 insertions`, `345 deletions`
- Live worktree delta at audit time: 2 modified tracked files, 1 untracked file

Commands used:

```bash
git branch --show-current
git rev-parse --verify main
git rev-parse HEAD
git merge-base main HEAD
git log --oneline --decorate --no-merges main..HEAD
git diff --stat main...HEAD
git diff --name-status main...HEAD
git diff --stat HEAD
git diff --name-status HEAD
git ls-files --others --exclude-standard
```

## Executive Decision

Treat this branch as a failed integration branch.

Do not merge `performance` wholesale. The branch mixes several separable ideas:

- Useful runtime foundations: profiler, split build profiles, draft geometry, focused validators.
- Possibly useful viewer interaction work: annotations, markup attachment capture.
- Failed workbench/chat integration: design-thread chat, Codex worker jobs as chat default, visual-evidence loops, provider/runtime adapters, and LLM-source-edit UX.
- Speculative or distracting docs: Gemini/provider/chat plan documents.

The safest recovery path is:

1. Start a clean branch from `main`.
2. Reapply only the `KEEP` items below in small reviewed slices.
3. Rebuild chat from a clean product contract, or integrate LlamaStudio's proven chat surface deliberately.
4. Do not preserve the current chat/worker path as default behavior.

## Keep / Toss Summary

### Keep

Keep these ideas, preferably by cherry-picking or reimplementing from clean commits:

- Build profiling and profile reports.
- Split build profiles such as `--part`, `--changed`, `--assembly-preview`, and `--handoff`.
- Draft geometry transactions and isolated `.flow/drafts` preview artifacts.
- Focused validator framework and panel validator.
- Generic MCP draft geometry/toolset exposure if kept separate from chat UX.
- Annotation toolbar and viewport markup overlay, but only as independent viewer tools.
- AGENTS/source-of-truth cleanup if it still matches the repo.

### Toss

Toss these from the branch unless redesigned from scratch:

- Viewer chat composer starting Codex/source worker jobs.
- `CodexWorkerJobManager` as the default chat implementation.
- Design-thread chat UI as currently built.
- LLM provider runtime adapters inside the viewer.
- Visual-evidence worker loop as a prerequisite for basic chat.
- Chat-specific roadmaps that justified the failed UX.
- Gemini/OpenAI/provider comparison docs that are not tied to shipped runtime value.

### Rebuild Later

Rebuild later only with a tighter product contract:

- Persistent design threads, if they are event history for a good UI rather than the UI itself.
- Source promotion from draft geometry, after draft preview works fast and visibly.
- Offscreen visual evidence, only after the basic chat/draft loop is usable.
- LLM-backed editing, only behind an explicit action such as `Promote to source`, never normal `Send`.

## Branch Commit Inventory

Commits on `performance` over `main`, newest first:

| Commit | Subject | Recommendation |
| --- | --- | --- |
| `3da66a3` | `hod this hot mess` | Toss as integrated branch state. It contains failed chat-worker behavior. |
| `c3b2bb7` | `Save gemini's proposal document` | Toss unless separately archived outside runtime docs. |
| `e8ac5aa` | `hold` | Review only for non-chat fixes; likely toss with branch. |
| `90604e4` | `Iterating on LLM drawing capability` | Toss. This is the failed chat/LLM drawing path. |
| `94d2b5b` | `Before registery` | Review only if it contains pre-registry runtime fixes. |
| `30fce01` | `Added httpx to project` | Toss unless a kept HTTP runtime path still requires it. |
| `deb4209` | `Created proper menu an dhot keys for annotation` | Keep annotation/menu work if it is decoupled from chat. |
| `0278c6d` | `Add Flow CAD MCP toolsets` | Keep if MCP surface remains useful and tested without chat dependency. |
| `7579a47` | `Add agent requested visual evidence flow` | Toss for this revert. Consider later, not in basic chat path. |
| `046cd2c` | `Render visual evidence in separate browser context` | Toss for this revert. Consider later if visual evidence is redesigned. |
| `015e3ea` | `Add design thread visual evidence artifacts` | Toss with visual-evidence/chat branch. |
| `44257eb` | `Add first-class Flow CAD runtime config` | Keep if config model is still needed for runtime/provider settings. |
| `22a9772` | `Autodetect Codex viewer chat runtime` | Toss. |
| `82ba4d5` | `Add Codex-backed viewer chat runtime` | Toss. |
| `18b2864` | `Doc updates` | Review, likely toss if chat/provider docs. |
| `7a7d5cf` | `ProvideSupport` | Toss or archive; not core runtime. |
| `2f11244` | `Implement design thread events and streaming adapter` | Toss as implemented. Rebuild only if a clean chat UI needs event storage. |
| `1e31a36` | `Add viewport markup attachments for design threads` | Keep the annotation attachment idea only if decoupled from design-thread chat. |
| `97a11fa` | `CVr1-3` | Review; likely mixed viewer/chat work. |
| `bf4d201` | `performance doc updates` | Keep only non-chat roadmap corrections. |
| `8e947c9` | `first pass on Command interface and view revamp docs` | Toss chat-command docs; keep only independent viewer notes if still useful. |
| `cb6bb83` | `Implement focused validator framework` | Keep. |
| `5723db2` | `Add draft geometry transactions` | Keep. |
| `be0caeb` | `Add draft feature mirroring API` | Keep if still covered by tests. |
| `3685c02` | `Add draft geometry MCP API` | Keep if draft API remains part of product. |
| `1378462` | `Complete performance foundation before draft geometry` | Keep if tests still pass cleanly. |
| `9320c59` | `Step 2:  Split Build Profiles` | Keep. |
| `d771625` | `Step 2:  Split Build Profiles` | Keep, but squash/clean duplicate step history. |
| `ce94a73` | `Step 1:  Profiler` | Keep. |
| `99d0c54` | `performance doc` | Keep only if rewritten to reflect the actual salvage plan. |

## File-By-File Divergence Matrix

Legend:

- `KEEP`: Keep or reapply on a clean branch.
- `TOSS`: Revert with the branch.
- `SPLIT`: Keep only a decoupled subset.
- `REVIEW`: Needs inspection before deciding; do not merge blindly.

| Status | Path | Decision | Notes |
| --- | --- | --- | --- |
| M | `AGENTS.md` | KEEP | Repo ownership/source-of-truth cleanup is useful if still accurate. |
| M | `README.md` | REVIEW | Keep only command/docs updates tied to kept runtime features. |
| A | `docs/CodexViewerReworkPlan.md` | TOSS | It rationalized the failed chat direction. Rebuild a shorter product contract later. |
| A | `docs/DesignPlanner.md` | TOSS | Tied to failed planner/chat path. |
| A | `docs/DraftGeometryAPI.md` | KEEP | Useful if draft geometry API is salvaged. |
| A | `docs/FlowCadMCP.md` | SPLIT | Keep draft/MCP toolset facts; remove chat/agent overreach. |
| A | `docs/FlowCadProfiler.md` | KEEP | Profiler documentation should survive. |
| A | `docs/FocusedValidators.md` | KEEP | Validator docs should survive. |
| A | `docs/GeminiDraftingProposal.md` | TOSS | Speculative provider/proposal doc, not runtime value. |
| A | `docs/PERFORMANCE.md` | SPLIT | Keep profiler/build/draft/validator goals; rewrite or remove chat claims. |
| A | `docs/ProviderSupport.md` | TOSS | Provider abstraction did not help this feature. |
| A | `docs/REGISTRY.md` | REVIEW | Keep only if registry changes are independent and useful. |
| A | `docs/REGISTRY_TICKETS.md` | REVIEW | Keep only if registry work remains planned. |
| A | `docs/Reports.md` | KEEP | Reporting/audit docs are useful if accurate. |
| A | `docs/ViewerChatTriage.md` | TOSS | Chat branch triage, not a kept product path. |
| A | `docs/ViewerLLMInterfaceRework.md` | TOSS | Replace with a new LlamaStudio-informed design if revisited. |
| A | `docs/ViewerPreview.md` | KEEP | Viewer preview/draft workflow is relevant. |
| A | `docs/VisualEvidence.md` | TOSS | Too entangled with failed chat/agent flow for this revert. |
| M | `pyproject.toml` | SPLIT | Keep dependencies only required by kept features; likely drop chat/provider deps. |
| M | `skills/flow-cad-project/SKILL.md` | REVIEW | Keep only generic workflow updates that match the salvaged runtime. |
| M | `src/flow_cad/cli.py` | KEEP | Keep CLI additions for profiler/build/validation if tested. |
| A | `src/flow_cad/config.py` | REVIEW | Keep if first-class config is still needed outside provider chat. |
| M | `src/flow_cad/core/exporter.py` | KEEP | Keep exporter/profile/build support if tied to performance foundation. |
| A | `src/flow_cad/design_planner.py` | TOSS | Design planner belongs to failed chat/planner path. |
| A | `src/flow_cad/draft_geometry.py` | KEEP | Core salvage item. |
| A | `src/flow_cad/draft_operations.py` | KEEP | Keep with draft API. |
| M | `src/flow_cad/main.py` | KEEP | Keep build profile/profiler changes; review for accidental chat coupling. |
| A | `src/flow_cad/mcp/__init__.py` | SPLIT | Keep only if MCP server survives. |
| A | `src/flow_cad/mcp/__main__.py` | SPLIT | Keep only if MCP server survives. |
| A | `src/flow_cad/mcp/server.py` | SPLIT | Keep draft/validator toolsets; remove chat-driven surface if any. |
| A | `src/flow_cad/preview_commands.py` | KEEP | Useful deterministic preview command parser. |
| A | `src/flow_cad/profiler.py` | KEEP | Core performance foundation. |
| M | `src/flow_cad/project.py` | KEEP | Keep project/runtime path support needed by profiler/draft/config. |
| A | `src/flow_cad/sketch_intent.py` | SPLIT | Keep only if annotation-to-draft is salvaged; otherwise toss with visual evidence. |
| A | `src/flow_cad/tools/__init__.py` | REVIEW | Keep only if tool registry survives. |
| A | `src/flow_cad/tools/registry.py` | REVIEW | Tool registry may be useful, but not required for basic CAD iteration. |
| A | `src/flow_cad/validation/__init__.py` | KEEP | Keep focused validator framework. |
| A | `src/flow_cad/validation/cli.py` | KEEP | Keep validator CLI. |
| A | `src/flow_cad/validation/contracts.py` | KEEP | Keep validator contracts. |
| A | `src/flow_cad/validation/facts.py` | KEEP | Keep validation fact providers. |
| A | `src/flow_cad/validation/panel.py` | KEEP | Keep panel validator. |
| A | `src/flow_cad/validation/placement.py` | KEEP | Keep generic placement validation if independent. |
| A | `src/flow_cad/validation/runner.py` | KEEP | Keep validator runner. |
| A | `src/flow_cad/viewer/agent_runtime.py` | TOSS | Failed provider/chat adapter path. |
| M | `src/flow_cad/viewer/app.py` | SPLIT | Keep draft/preview endpoints; toss chat/planner/visual-evidence/worker default plumbing. |
| M | `src/flow_cad/viewer/cli.py` | REVIEW | Keep only unrelated viewer CLI improvements. |
| M | `src/flow_cad/viewer/service.py` | SPLIT | Keep draft transaction and preview service methods; toss chat/visual evidence coupling. |
| A | `src/flow_cad/viewer/threads.py` | TOSS | Current design-thread implementation is part of failed chat branch. Rebuild later if needed. |
| A | `src/flow_cad/viewer/worker_jobs.py` | TOSS | Explicitly failed default chat worker path. |
| A | `tests/test_build_profiles.py` | KEEP | Keep with build profiles. |
| A | `tests/test_codex_worker_jobs.py` | TOSS | Worker jobs should not survive this branch as a default path. |
| A | `tests/test_config.py` | REVIEW | Keep only if `config.py` is salvaged. |
| A | `tests/test_design_planner.py` | TOSS | Toss with design planner. |
| A | `tests/test_draft_geometry.py` | KEEP | Keep with draft geometry. |
| A | `tests/test_draft_operations.py` | KEEP | Keep with draft operations. |
| A | `tests/test_focused_validators.py` | KEEP | Keep with validators. |
| A | `tests/test_mcp_server.py` | SPLIT | Keep if MCP server survives; trim chat/provider assumptions. |
| A | `tests/test_profiler.py` | KEEP | Keep with profiler. |
| M | `tests/test_project.py` | KEEP | Keep only project changes required by salvaged features. |
| A | `tests/test_sketch_intent.py` | SPLIT | Keep only with annotation-to-draft salvage. |
| A | `tests/test_sketch_to_part_workflow.py` | SPLIT | Keep only if annotation-to-draft is retained. |
| A | `tests/test_tool_registry.py` | REVIEW | Keep if tool registry survives. |
| A | `tests/test_viewer_agent_runtime.py` | TOSS | Toss with provider/chat adapters. |
| M | `tests/test_viewer_cli.py` | REVIEW | Keep only independent viewer CLI changes. |
| A | `tests/test_viewer_design_threads.py` | TOSS | Toss with current design-thread/chat implementation. |
| A | `tests/test_viewer_preview_commands.py` | KEEP | Keep deterministic preview command tests. |
| M | `tests/test_viewer_service.py` | SPLIT | Keep draft/preview service coverage; remove chat/visual-evidence/worker coverage. |
| M | `viewer/stl-viewer/src/App.test.tsx` | SPLIT | Keep annotation and preview tests; toss chat/worker/default composer changes. |
| M | `viewer/stl-viewer/src/App.tsx` | SPLIT | Keep annotation/preview UI if decoupled; toss chat/worker/default composer implementation. |
| A | `viewer/stl-viewer/src/components/AnnotationToolbar.tsx` | KEEP | Best salvage from viewer work, if kept independent. |
| A | `viewer/stl-viewer/src/components/CommandPane.tsx` | REVIEW | Keep only if preview command surface remains useful. |
| A | `viewer/stl-viewer/src/components/DesignThreadDock.tsx` | TOSS | Current chat UI is not acceptable. |
| M | `viewer/stl-viewer/src/components/FileDropZone.tsx` | REVIEW | Keep only minor independent improvements. |
| M | `viewer/stl-viewer/src/components/SourcePanel.tsx` | REVIEW | Keep only source panel improvements not tied to chat layout. |
| M | `viewer/stl-viewer/src/components/Toolbar.test.tsx` | KEEP | Keep if tied to annotation toolbar/menu shortcuts. |
| M | `viewer/stl-viewer/src/components/Toolbar.tsx` | KEEP | Keep annotation/menu/hotkey improvements if independent. |
| M | `viewer/stl-viewer/src/components/Viewer.tsx` | REVIEW | Keep only if needed by annotation/preview. |
| A | `viewer/stl-viewer/src/components/ViewportMarkupOverlay.tsx` | KEEP | Keep as independent annotation overlay. |
| M | `viewer/stl-viewer/src/index.css` | SPLIT | Keep annotation/preview styles; toss chat-specific styling. |
| A | `viewer/stl-viewer/src/shortcuts.ts` | KEEP | Keep if toolbar hotkeys survive. |
| M | `viewer/stl-viewer/src/types.ts` | SPLIT | Keep draft/annotation types; toss chat/worker/provider types. |
| A | `viewer/stl-viewer/src/visualEvidenceRender.test.ts` | TOSS | Toss with visual-evidence flow. |
| A | `viewer/stl-viewer/src/visualEvidenceRender.ts` | TOSS | Toss with visual-evidence flow. |

## Live Worktree Divergences Not Yet Committed

These are on top of `performance` HEAD at audit time.

| Status | Path | Decision | Notes |
| --- | --- | --- | --- |
| M | `viewer/stl-viewer/src/App.tsx` | TOSS | Emergency patch removing worker jobs from composer. Correct direction, but it belongs in a clean rewrite, not this branch. |
| M | `viewer/stl-viewer/src/App.test.tsx` | TOSS | Tests for emergency chat routing patch. Do not preserve as-is. |
| ?? | `docs/GEMINI_PERFORMANCE_REVIEW.md` | TOSS | Untracked review/proposal artifact. Not part of runtime recovery. |

## What To Keep In A Clean Rebuild

### Slice 1: Performance Foundation

Keep:

- `src/flow_cad/profiler.py`
- build profile changes in `src/flow_cad/main.py`
- relevant CLI additions in `src/flow_cad/cli.py`
- `docs/FlowCadProfiler.md`
- `tests/test_profiler.py`
- `tests/test_build_profiles.py`

Completion condition:

```bash
.venv/bin/python -m pytest tests/test_profiler.py tests/test_build_profiles.py
```

### Slice 2: Draft Geometry Foundation

Keep:

- `src/flow_cad/draft_geometry.py`
- `src/flow_cad/draft_operations.py`
- `src/flow_cad/preview_commands.py`
- draft/preview service methods in `src/flow_cad/viewer/service.py`
- draft/preview endpoints in `src/flow_cad/viewer/app.py`
- `docs/DraftGeometryAPI.md`
- `docs/ViewerPreview.md`
- `tests/test_draft_geometry.py`
- `tests/test_draft_operations.py`
- `tests/test_viewer_preview_commands.py`

Completion condition:

```bash
.venv/bin/python -m pytest tests/test_draft_geometry.py tests/test_draft_operations.py tests/test_viewer_preview_commands.py
```

### Slice 3: Focused Validators

Keep:

- `src/flow_cad/validation/`
- validator CLI wiring
- `docs/FocusedValidators.md`
- `tests/test_focused_validators.py`

Completion condition:

```bash
.venv/bin/python -m pytest tests/test_focused_validators.py
```

### Slice 4: Annotation UI

Keep only after separating it from chat:

- `viewer/stl-viewer/src/components/AnnotationToolbar.tsx`
- `viewer/stl-viewer/src/components/ViewportMarkupOverlay.tsx`
- `viewer/stl-viewer/src/shortcuts.ts`
- relevant `Toolbar.tsx`, `Toolbar.test.tsx`, `App.tsx`, `index.css`, and `types.ts` changes

Completion condition:

```bash
npm --prefix viewer/stl-viewer test -- App.test.tsx Toolbar.test.tsx
npm --prefix viewer/stl-viewer run build
```

## What To Throw Away

Throw away the current implementation of:

- Design-thread chat dock.
- Codex worker jobs as chat engine.
- Agent runtime/provider adapters.
- Visual evidence as part of chat turn execution.
- Design planner as a mandatory chat step.
- Chat-specific docs and Gemini/provider proposal docs.

Reason:

These pieces made basic user intent slower and less reliable. They turned the
viewer chat into a worse terminal-agent transcript instead of a CAD interaction.

## Replacement Product Contract

Any future chat rebuild should start from this contract:

1. `Send` must show an assistant row immediately.
2. Simple geometry prompts must produce a visible draft preview first.
3. Source edits must be an explicit command, not the default response.
4. Commands/tool calls must be collapsed by default.
5. Chat must not spam one card per shell command.
6. The viewport must update before the assistant writes a long summary.
7. LLM work must never be required to create a rectangle, plate, hole, slot, or counterbore draft.
8. If LlamaStudio already does the chat interaction well, reuse its interaction model directly instead of re-inventing it inside the viewer.

## Recommended Revert Procedure

Do not try to manually revert individual failed chat files inside this branch.
The branch is too mixed.

Recommended:

```bash
git switch main
git switch -c performance-salvage
```

Then reapply kept slices one at a time with focused tests. If cherry-picking
turns into conflict resolution around chat files, stop and manually port only
the relevant runtime code.

Suggested order:

1. Profiler and build profiles.
2. Draft geometry and preview commands.
3. Focused validators.
4. MCP draft surface if still wanted.
5. Annotation UI decoupled from chat.

Do not bring over current `DesignThreadDock`, `worker_jobs.py`, or
`agent_runtime.py` unless the product direction changes and they are rebuilt
behind explicit, non-default commands.
