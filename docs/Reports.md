# Reports And Audit Reporting

Date: 2026-06-09

## Purpose

Flow CAD already has useful reporting pieces, but they are not yet a complete
audit system. The current runtime can summarize exports, cache rows, timings,
focused validator results, draft geometry facts, and STEP snap features. It
cannot yet answer project-wide intent questions such as "list the purpose of
every screw hole" unless a downstream project has already declared that intent
in project-owned source or validators.

This document records the current capability, the gaps, and a concrete path to
rock-solid reporting.

## Current Reporting Surfaces

### CAD Report

`flow cad build` can write a text CAD report when reports are enabled. The
implementation lives in `src/flow_cad/core/report.py` and currently includes:

- full assembly bounding box when assembly geometry is built
- printable assembly bounding box when printable occurrences are available
- exported STEP file list
- version mass summary
- missing inertial metadata by part

The report is useful as a handoff summary, but it is not yet a structured audit
catalog. It does not include feature inventory, hole intent, placement deltas,
validator results, cache freshness, source provenance, or pass/fail criteria.

### Active Cache And Registry CLI

`flow registry list` and `flow registry show <component_id>` query the generated
active cache. The cache records:

- part id
- module id
- role
- metadata status and notes
- STEP path
- bounding box
- volume
- build id

This is good for "what parts were built?" and "what are their dimensions?" It is
not a geometry-feature or design-intent source of truth. A cache row does not
know why a hole exists, what hardware it accepts, what it mates to, or whether a
feature is protected.

Current checkout note: the bundled example has generated report/profile files,
but its active cache is not currently usable. `flow registry list` reports no
component rows, and the latest checked-in example profile shows a failed
`active_cache_write` event with `TypeError: asdict() should be called on
dataclass instances`. Treat that as a local-state/code issue to fix before using
the bundled example as reporting proof.

### Build And Validator Profiles

Every `flow cad build` writes JSON profiles under `.flow/profiles/`:

```text
.flow/profiles/latest-build-profile.json
.flow/profiles/build-profile-<timestamp>-<profile-id>.json
```

Standalone focused-validator runs write:

```text
.flow/profiles/latest-validator-profile.json
.flow/profiles/validator-profile-<timestamp>-<profile-id>.json
```

`flow cad profile --last` reads the newest build or validator profile and shows
phase totals plus slowest operations. The profile events currently cover build
phases such as params loading, part generation, STEP/STL export, snapshots,
assembly placement, report generation, active-cache writes, viewer-cache
refresh, interference checks, validators, project tests, and handoff bundling.

This is the strongest existing reporting foundation for performance work. It is
structured JSON, records failures, and includes phase-level metadata. It is not a
domain audit by itself.

### Focused Validator Reports

`flow validate list` and `flow validate run ... --json` provide structured
validator reports outside the full handoff gate. Reports include:

- validator metadata
- elapsed time
- input summary
- issue counts
- machine-readable issues
- expected and actual values
- units
- coordinates
- feature ids when available
- geometry authority
- remediation text when available

This is the right base for audits that need pass/fail behavior. The framework
can report precise problems, but it only knows about feature intent if a project
validator or draft transaction supplies that intent.

### Draft Geometry Facts

Draft geometry operations return structured facts for fast panel work:

- bounding box
- feature list
- hole centers
- axes
- diameters
- face
- minimum edge distance where available
- warnings
- preview STEP path

Accepted draft transactions also write an `acceptance.json` manifest under
`.flow/draft-transactions/<transaction-token>/accept/`.

This is currently the best feature-level reporting surface. It knows that a
draft feature is a hole, counterbore, slot, or louver-pattern slot. It still does
not know durable production intent unless the accepted source or validator stub
is extended with intent fields.

### STEP Snap Features

STEP-backed parts expose exact topology-derived snap features for the viewer.
The current extractor reports vertices, line edges, edge midpoints, and neutral
circle centers.

This is exact geometry, but it is intentionally not semantic hardware intent.
Generic circular STEP edges are labeled `circle_center`, not `hole_center`,
because bosses, fillets, roundovers, decorative arcs, and cut holes can all
produce circular geometry. A report must not claim "screw hole" from a circle
center alone.

### MCP Reporting Access

The MCP server currently exposes:

- draft geometry tools
- draft transaction tools
- `validator_list`
- `validator_run`
- `profile_last`

This gives agents and local models structured access to draft facts, validator
reports, and profile summaries. The MCP layer is not yet a general report
catalog or feature-intent query interface.

## Can We List Every Screw Hole Intent Today?

Not reliably.

Today we can list:

- draft holes for draft parts, because draft facts include `feature_list` and
  `hole_centers`
- expected holes checked by a project-specific focused validator, if that
  validator encodes them
- STEP circle centers, but only as neutral circle geometry
- cached part-level metadata, but not feature-level intent

Today we cannot generically list:

- every production screw hole across every project part
- why each hole exists
- what hardware each hole accepts
- whether it is clearance, threaded insert, heat-set insert, counterbore,
  countersink, pilot, access, alignment, or wiring relief
- what part or assembly feature it mates to
- whether the hole has been verified against the generated STEP
- whether its project docs, source params, validator expectations, and exports
  agree

That missing capability is exactly the gap a rock-solid audit reporting layer
should close.

## Reporting Principles

Rock-solid reporting should follow these rules:

- Do not infer design intent from mesh geometry.
- Treat STEP as exact geometry, not as the sole semantic source.
- Treat project source, params, registries, validators, and explicit feature
  intent declarations as the semantic source of truth.
- Mark every fact with authority: declared, verified, inferred, approximate, or
  missing.
- Keep Flow CAD generic. Screw brands, robot hardware, printer rules, and
  product-specific mating contracts belong in downstream projects.
- Every report should be reproducible from the project root.
- Every report should have JSON first, with Markdown/CSV as views of the same
  payload.
- Every generated report should record source provenance, artifact paths, build
  id, profile id, git state, command, and timestamp.
- Audits should produce structured issues; inventories should produce structured
  rows.
- Reports should fail loudly when their inputs are stale, missing, approximate,
  or authority-degraded.

## Proposed Reporting Model

### Report Types

Flow CAD should distinguish three related outputs:

- Inventory reports: list facts without judging them.
- Audit reports: compare facts to contracts and produce issues.
- Gate reports: bundle the inventories, audits, profiles, and generated
  artifacts used for handoff.

Focused validators already cover part of the audit-report layer. The missing
piece is a first-class report runner that can aggregate facts and write durable
report artifacts.

### Report Artifacts

Use one report run directory per command:

```text
reports/<report-id>/<run-id>/
  report.json
  report.md
  report.csv
  inputs.json
  profile.json
```

Also maintain stable latest paths:

```text
reports/latest-build-summary.json
reports/latest-feature-intents.json
reports/latest-hole-inventory.json
reports/latest-audit.json
```

The `report.json` payload should be canonical. Markdown and CSV should be
generated from that JSON.

### Report Manifest

Every report should declare:

- schema version
- report id
- report type: inventory, audit, or gate
- project id
- project root
- command
- started and finished timestamps
- git commit and dirty state
- build id
- profile id
- input artifacts
- geometry authority summary
- warnings
- rows or issues
- output files

### Feature Intent Contract

To answer screw-hole questions, Flow CAD needs a generic feature intent schema.
Flow CAD should own the schema and report machinery; projects should own the
actual feature declarations.

Suggested generic shape:

```python
FeatureIntent(
    id="lower_chassis:m4_battery_tray_front_left",
    part_id="lower_chassis",
    feature_id="m4_battery_tray_front_left",
    kind="hole",
    purpose="screw_mount",
    hardware="M4 clearance screw",
    face="top",
    frame="part_local",
    center_mm=(42.0, 18.0, 6.0),
    axis=(0.0, 0.0, 1.0),
    diameter_mm=4.4,
    through=True,
    head_style="socket_head",
    counterbore_diameter_mm=None,
    counterbore_depth_mm=None,
    mates_to=[
        {
            "part_id": "battery_tray",
            "feature_id": "m4_front_left",
            "relationship": "coaxial",
        }
    ],
    source="flow/feature_intents.py",
    authority="declared",
)
```

This should not be limited to screw holes. The same contract can cover slots,
wire passages, vents, alignment pins, datum points, keepouts, nut pockets,
heat-set insert pockets, access reliefs, bosses, tabs, and inspection-only
features.

### Feature Verification

A report should separate declared intent from verified geometry:

- Declared: project source says the feature should exist.
- Found: STEP or draft facts show matching geometry.
- Verified: declared and generated geometry match within tolerance.
- Degraded: only approximate mesh or neutral circle evidence exists.
- Missing: declared feature was not found in generated facts.
- Unclaimed: geometry exists but has no declared intent.

For screw holes, the hole inventory should include both declared rows and
unclaimed candidate geometry:

| Part | Feature | Purpose | Hardware | Face | Center mm | Diameter | Mates To | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| lower_chassis | m4_battery_tray_front_left | screw_mount | M4 clearance | top | 42,18,6 | 4.4 | battery_tray:m4_front_left | verified |
| lower_chassis | circle_center:17 | unknown | unknown | unknown | 12,44,6 | 9.2 | - | unclaimed |

The second row is important. It prevents silent drift where geometry exists but
no one has said what it is for.

## Proposed Commands

Add a first-class report command group:

```bash
flow report list
flow report run build-summary
flow report run part-inventory --json
flow report run feature-intents --format json,md,csv
flow report run hole-inventory --part <part-id>
flow report run gate --profile active
```

Keep validation pass/fail behavior under `flow validate`:

```bash
flow validate run feature-intents --tag holes --json
flow validate run project-hardware --part lower_chassis
```

The report runner should be read-only by default. It may write only under
`reports/` and `.flow/profiles/`.

## Proposed Built-In Reports

### Build Summary

Structured replacement for the current text CAD report. Include:

- assembly and printable bounding boxes
- exported artifacts
- cache state
- missing metadata
- profile summary
- validator summary
- gate status

### Part Inventory

One row per registered part:

- id
- module/family/version
- role
- source files
- STEP/STL paths
- bounding box
- volume
- mass/COM/inertia metadata
- metadata status
- placement count
- geometry authority
- cache freshness

### Feature Intent Inventory

One row per declared feature intent:

- part id
- feature id
- kind
- purpose
- hardware
- coordinates
- expected geometry
- mating targets
- source path
- declared authority
- verification status

### Hole Inventory

Specialized view over feature intents and candidate geometry:

- screw holes
- insert holes
- counterbores
- countersinks
- slots used as screw adjustment holes
- access holes
- unclaimed circular candidates

This is the report that should answer "what is every screw hole for?"

### Geometry Authority Report

List every part and whether its facts came from:

- declared source
- active cache
- STEP topology
- draft facts
- STL mesh
- missing artifacts

This should make it impossible to accidentally present STL-derived facts as
exact CAD facts.

### Drift Report

Compare source declarations, active cache, generated STEP, viewer cache, docs,
and report outputs. Flag:

- stale cache rows
- missing STEP files
- stale viewer snap-feature cache
- report generated from older build id
- declared feature not present in STEP
- generated candidate feature with no declared intent
- project docs mentioning removed parts or obsolete feature ids

### Gate Report

For handoff, write a single aggregate report that links:

- build profile
- CAD report
- part inventory
- feature inventory
- hole inventory
- validator reports
- project test results when run through Flow CAD
- handoff bundle path
- unresolved warnings/errors

## Implementation Plan

### RPT-1: Structured Report Contract

Add report dataclasses under `src/flow_cad/reporting/`:

- `ReportMetadata`
- `ReportInput`
- `ReportRow`
- `ReportIssue`
- `ReportArtifact`
- `ReportPayload`

Add JSON serialization tests and keep the schema small enough for MCP and future
viewer use.

### RPT-2: Report Runner And CLI

Add `flow report list` and `flow report run <report-id>`.

The runner should:

- load the active project
- collect facts through shared providers
- write canonical JSON
- optionally write Markdown and CSV
- return clear exit codes
- avoid source/export/cache mutation

### RPT-3: Feature Intent Schema

Add generic runtime types for feature intent declarations. Support project-local
providers through the manifest, for example:

```yaml
reports:
  feature_intents: flow.feature_intents:get_feature_intents
```

If the manifest shape needs to stay separate from report output paths, use a
dedicated section:

```yaml
feature_intents:
  provider: flow.feature_intents:get_feature_intents
```

Flow CAD should provide the type helpers and examples. Project repos should fill
in their hardware-specific declarations.

### RPT-4: Feature Verification Helpers

Add reusable helpers that compare feature declarations against draft and STEP
facts:

- center tolerance
- axis tolerance
- diameter tolerance
- counterbore depth tolerance
- through-hole evidence
- face/plane evidence
- mating coaxial alignment
- minimum edge distance

Do not call neutral STEP circles screw holes. Mark them as candidates until a
declared intent or conservative classifier verifies them.

### RPT-5: Hole Inventory Report

Implement `hole-inventory` as the first feature-intent report:

- list declared hole-like features
- list unclaimed STEP circle candidates separately
- mark authority and verification status
- emit JSON, Markdown, and CSV
- include warnings for missing or stale facts

### RPT-6: Audit Integration

Add focused validators that consume feature intent declarations:

- `feature-intents`
- `hole-intents`
- `mating-hole-alignment`
- `unclaimed-circular-features`

These validators should produce structured issues, while `flow report run
hole-inventory` produces inventory rows.

### RPT-7: MCP Read Tools

Add MCP wrappers only after the shared service exists:

- `report_list`
- `report_run`
- `part_inventory`
- `feature_intents`
- `hole_inventory`

Keep payloads bounded. Large reports should return a summary plus paths to
generated artifacts.

### RPT-8: Viewer Inspector Integration

Once reports exist, the viewer can show:

- part report status
- feature intent rows for selected part
- unclaimed geometry candidates
- stale/missing authority warnings
- links to generated report artifacts

The viewer should read report JSON; it should not reimplement audit logic.

## Testing Requirements

Reporting work should add tests for:

- JSON schema stability
- Markdown/CSV generated from the same payload
- report runner read-only behavior
- project manifest provider loading
- missing provider diagnostics
- stale cache and stale STEP warnings
- declared hole verified against draft facts
- declared hole verified against STEP facts
- unclaimed circle candidate reporting
- focused validator consumption of feature intents
- `flow init` starter project examples
- MCP wrapper registration and forwarding if MCP tools are added

For downstream project verification, reinstall Flow CAD editable, run the report
from the downstream project root, and keep project-specific feature declarations
in that project.

## Suggested Near-Term Path

The most valuable first slice is:

1. Add the structured report contract and `flow report` runner.
2. Add project-owned `FeatureIntent` provider support.
3. Add `hole-inventory` JSON and Markdown output.
4. Add one focused validator that fails on declared holes missing from draft or
   STEP facts.
5. Add starter examples copied by `flow init`.

That would turn the screw-hole question from an inference problem into a
repeatable command:

```bash
flow report run hole-inventory --format md,json,csv
flow validate run hole-intents --json
```

At that point Flow CAD can answer "show every screw hole and what it is for" for
any project that declares feature intent, while still refusing to invent intent
from geometry alone.
