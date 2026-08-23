# B2 Top-Plate Iteration Performance Incident

Date: 2026-08-23  
Scope: Flow CAD rebuild workbench at UI `3000`, API `8001`, with the
`/home/gnulnx/flow_b2` downstream project.

This is the incident record requested after the B2 top-plate cable-bay change.
The broader performance roadmap remains in `docs/PERFORMANCE.md`. This document
records what actually happened in one supposedly simple iteration and turns it
into a concrete 3-5 minute acceptance benchmark.

## Outcome

The CAD operation was not slow. The focused production build completed in
`730.406 ms`:

| Build phase | Measured time |
| --- | ---: |
| Import project symbols | 20.8 ms |
| Load parameters | 0.2 ms |
| Generate geometry | 323.4 ms |
| Export STEP | 23.8 ms |
| Export STL | 137.4 ms |
| Hash artifacts | 0.9 ms |
| Publish viewer revision | 42.4 ms |
| Complete focused build | 730.406 ms |

The user-visible loop nevertheless took more than 30 minutes. Most of that time
was spent recovering missing workflow behavior, proving what the viewer was
showing, working around test/runtime conflicts, and manually bridging draft,
assembly, source, export, and validation states.

## Performance Issues Encountered

### 1. A draft part did not inherit the production assembly placement

The first preview appeared at identity placement away from the robot. It was a
valid isolated part, but it could not answer whether the cable bay aligned with
the Bosgame, dome, top plate, or existing fasteners.

This required implementing an ephemeral in-place preview replacement in Flow
CAD. A preview can now borrow the target part's occurrences while suppressing
the target to prevent z-fighting. That generic fix landed in commit
`b57e592d1fb5fcf61894b622536192070f9adbf0`.

Required product behavior:

- Every modification preview starts at the selected production part's assembly
  occurrences by default.
- An isolated origin view must be an explicit user choice, not the default.
- Preview, target, occurrence transform, and assembly revision must be shown
  together in the UI.

### 2. The rebuilt API no longer exposed the documented draft transaction path

The older workflow documentation referenced `/api/draft-transactions`, but the
active rebuild API on port 8001 did not expose those endpoints. The first draft
therefore had to be registered as a temporary inspection part through the
project manifest and metadata index.

That workaround crossed too many states for a disposable visual check:

```text
draft source -> draft STEP/STL -> temporary manifest entry -> flow sync
-> API reload -> search result -> viewer selection
```

Required product behavior:

- The active documentation and running API must describe the same preview
  contract.
- A disposable preview must not require a manifest edit or registry lifecycle
  entry.
- The API should advertise supported preview capabilities and provide a direct
  replacement-preview route.

### 3. Viewer metadata did not refresh after backend state changed

The browser inventory did not reliably notice a new project revision or
preview-placement state. Backend updates could succeed while the existing tab
continued showing stale metadata.

Lightweight project/view-state revision polling was added with the in-place
preview fix. The remaining acceptance requirement is that the browser visibly
acknowledge the new revision and model identity without a hard reload.

### 4. The preview was concealed by the installed dome

Once the plate was correctly placed, the new cable bay was beneath the dome, as
it will be on the physical robot. That is correct assembly geometry but poor
review ergonomics. The user had no obvious way to hide the dome or restore the
complete assembly afterward.

Required product behavior:

- Every part and occurrence row needs an obvious visibility control.
- Selecting an obscured part should offer `isolate`, `hide occluders`, and
  `show neighbors` actions.
- Add a prominent **Show fully assembled** action that restores all default
  occurrence visibility, clears isolation/preview suppression, reloads the
  active assembly, and frames the assembly.
- The action must be idempotent and must not mutate the project manifest.

### 5. The parts list lost useful organization

The rebuilt list is searchable but effectively flat. It does not present the
old family/hierarchy/assembly organization, and it does not make the distinction
between part definitions, assembly occurrences, references, inspection parts,
and temporary previews obvious.

Required product behavior:

- Provide an assembly occurrence tree grouped by subsystem and family.
- Keep search, but return results in their assembly context.
- Show lifecycle, material, printable/reference role, occurrence count, and
  visibility state without opening a detail pane.
- Preserve selection while switching between search results and the assembly
  tree.

### 6. There was no complete preview-to-printer workflow

Seeing the temporary part did not answer “how do I build this?” The preview was
not a production source change, was absent from the clean manifest, and had no
obvious promote/build/download action. The user also could not tell whether the
old top plate needed to be deleted or whether the dome had to be permanently
removed.

Required product behavior:

```text
preview in place -> accept -> patch existing production part
-> focused build -> focused validation -> download/open STEP or STL
```

- Promotion must retain the production part UUID and occurrence placement.
- The UI must distinguish temporary visibility from deleting an occurrence.
- A successful focused build should show artifact paths, hashes, size, revision,
  and a direct printer-file action.
- The user should not have to understand manifest/index/cache internals.

### 7. CLI command discovery added avoidable round trips

An expected `flow part build` path did not exist; the replacement command is
`flow cad build --part <key>`. Discovering the correct namespace required extra
help calls. The split between `flow part` lifecycle metadata and `flow cad`
geometry builds is defensible internally but not obvious during iteration.

Required product behavior:

- `flow part build <key>` should be a supported alias or print the exact modern
  command instead of only reporting `No such command`.
- Searchable UI actions should expose the equivalent CLI command.

### 8. A focused Flow CAD build did not emit the standard inspection sidecars

The production build successfully emitted STEP and STL, but the standard CAD
inspection command then refused to inspect the STEP because the adjacent hidden
Explorer GLB/topology artifact was missing:

```text
STEP topology validation requires the generated GLB artifact, but it is missing
```

This forced separate direct Build123d imports and Boolean comparisons even
though the authoritative STEP already existed.

Required product behavior:

- `flow cad build --part` should emit the same inspection sidecar contract as
  the supported CAD generation path, or
- the inspector should fall back to direct STEP facts when the optional viewer
  sidecar is absent.

Inspection must not require regenerating already-valid production geometry.

### 9. Clearing preview state produced an unbounded artifact dump

`flow refresh --clear-preview` completed quickly, but printed the identity of
the entire project artifact inventory. For a one-state operation this produced
dozens of unrelated lines and hid the relevant result.

Required product behavior:

- Default output should report the changed preview state, backend revision, and
  affected target/preview only.
- Full artifact inventory should require `--verbose` or a separate listing
  command.

### 10. API-only tests still collided with the live UI port

The first full downstream test run took `35.43 s` and ended with three failures.
Each test selected a free backend port and invoked `flow start --api-only`, but
startup still tried to reserve frontend port 3000. The real workbench was using
that port, so the API-only process exited with:

```text
Error: No available port found for 127.0.0.1:3000-3000
```

The workbench had to be stopped, the suite rerun for `36.42 s`, and the
workbench restarted. The second run passed all 31 tests.

Required product behavior:

- `--api-only` must not resolve, reserve, probe, or require a frontend port.
- API integration tests must coexist with an active user workbench.
- Test startup should report chosen ports before doing other work.

### 11. Verification setup was repeated and noisy

The downstream workflow requires reinstalling the active Flow CAD checkout
editable before verification. The install was correct and took about 8 seconds,
but pip printed a long dependency inventory even though dependencies were
already satisfied.

Required product behavior:

- Provide a quiet, version-aware downstream runtime check that skips reinstall
  when the editable checkout already resolves to the expected commit.
- When reinstall is required, show one concise progress line unless verbose
  output is requested.

### 12. Generated STEP text overwhelmed ordinary diff diagnostics

Running `git diff --check` over the downstream change produced hundreds of
trailing-whitespace reports from exporter-generated STEP text. This obscured
the actual source/documentation check and consumed output budget. The source
paths were clean when checked separately.

Required product behavior:

- Generated STEP/STL paths should be excluded from source-style whitespace
  diagnostics by the project template or validation command.
- Artifact integrity should use geometry facts and hashes, not text formatting.

### 13. The migration gate assumed active product source could never evolve

The downstream preservation check correctly protects the immutable B3 archive,
but its initial source-port test also assumed all active sources would remain
byte-identical to their first migrated form. The first intentional production
change therefore required a declared-evolution mechanism before normal tests
could pass.

This is downstream contract friction rather than CAD-kernel latency, but it is
part of the measured iteration experience. Preservation must protect the archive
without preventing the active product from evolving.

### 14. The strict baseline-equivalence release concept needs an evolution path

The migrated project still has a strict release validator intended to prove the
initial active artifacts match B3. An intentionally changed top plate is no
longer supposed to match that baseline. A production evolution needs an explicit
release contract that keeps the original baseline immutable while validating
the new approved artifact against its own dimensions, interfaces, and recorded
identity.

The full release gate was deliberately not run during this printer-first pass.
This should be resolved before treating strict baseline equivalence as the
permanent release rule for an evolving product.

### 15. Browser/window behavior was disruptive

Earlier troubleshooting opened multiple browser windows. The user had to
recover the intended workbench and explicitly require that all later work reuse
one existing window. `flow start` still defaults to opening a browser, which is
unsafe for agent-driven refresh/recovery work.

Required product behavior:

- Detect and reuse an existing project workbench by default.
- Opening a new browser window must be explicit when the same project already
  has a live UI/API pair.
- Refresh, reload, build, preview, and capture operations must never spawn a
  window.

### 16. Existing docs described implemented-looking workflows that were not in
the active rebuild

The repository contains detailed preview, draft transaction, chat, refresh, and
performance documents. During this task, some documented routes and workflows
were absent from the active rebuild while the documents read as though they were
available. That increased diagnosis time and caused false starts.

Required product behavior:

- Every workflow document needs an explicit status tied to a tested commit.
- The running workbench should expose a capabilities endpoint generated from
  the actual route/service registry.
- User documentation should be generated or checked against those capabilities.

## 3-5 Minute Acceptance Benchmark

The benchmark is an edit to an existing plate: add one rounded through-cut,
review it in assembly, accept it, build it, and obtain a printer file.

| Deadline | User-visible result |
| --- | --- |
| 0:15 | Existing part and occurrence context are selected automatically. |
| 0:45 | Draft cut appears in-place in the active assembly. |
| 1:15 | User can hide occluders, inspect alignment, and restore **Show fully assembled**. |
| 2:00 | Accepted preview is represented as a source patch against the existing part UUID. |
| 2:30 | Focused STEP/STL build completes and updates the existing browser tab. |
| 3:00 | Focused geometry/interface checks complete; artifact hashes and download actions are visible. |
| 5:00 | Contingency limit for one correction and rebuild. |

The timer starts when the edit request is submitted. It ends when the user can
send the STL to the slicer. Full-project tests, release bundles, full assembly
interference, and archival gates are not on this interactive critical path.

## Required Telemetry

One iteration id should connect:

- user request receipt
- selected project, assembly, part UUID, and occurrence ids
- preview generation and placement
- browser revision acknowledgement
- occluder/visibility actions
- source promotion
- focused build phases
- focused validator phases
- artifact paths, hashes, and download action
- final user-visible completion

The profiler must report both compute time and waiting/workflow time. A subsecond
kernel build must not allow a 30-minute interaction to be reported as a
performance success.

## Priority Order

1. Add **Show fully assembled**, explicit visibility controls, and assembly tree
   organization.
2. Complete preview-to-existing-part promotion and printer artifact actions.
3. Fix `--api-only` so tests coexist with the live workbench.
4. Unify focused build and inspection sidecar contracts.
5. Make preview/runtime capability discovery authoritative and keep docs tied to
   tested commits.
6. Reduce refresh, install, and diff diagnostic noise.
7. Add the 3-5 minute end-to-end benchmark to CI with separate draft, source,
   and gate-loop timing.
