# B2 v3 URDF Composite Inertia Fix Ticket

## Purpose

Build a versioned `B2_v3.urdf` path that preserves the current B2 visual and
collision geometry while replacing the current simple-box chassis inertia model
with a measured-component composite inertia model.

This is a Flow CAD plus B3 CAD project ticket. It is not a Dojo training, VCB,
or reward ticket.

## Non-Negotiables

- Do not overwrite or regenerate `B2_v2.urdf` as the final artifact for this
  work.
- Do not edit Dojo training code, VCB code, active training configs, or deploy
  configs as part of this ticket.
- Do not hand-edit generated URDF XML. Edit generator/source code and regenerate
  the explicit target.
- Do not silently default missing mass, COM, inertia, wheelbase, wheel radius,
  or frame data.
- Any estimate must be labeled as estimated in the report, with the source and
  method recorded.
- Heavy missing components must fail loud instead of disappearing from the mass
  model.

## Current Verified State

The old `URDF_BUG.md` is now partly stale. The current Dojo asset:

```text
/home/gnulnx/BLR/DojoV2/src/dojo/assets/B2_v2.urdf
```

does include many CAD-derived occurrence visual and collision boxes on
`chassis_link`, including wheel boxes and compartment bodies. The remaining
critical problem is the inertial model:

- `chassis_link` still has placeholder inertials:
  - `{CHASSIS_MASS}`
  - `{COM_X}`
  - `{COM_Z}`
  - `{IXX}`
  - `{IYY}`
  - `{IZZ}`
- Dojo fills `IXX/IYY/IZZ` from `flow_cad_chassis_box` using simple box inertia.
- Dojo can then multiply loaded pitch inertia with
  `chassis_pitch_inertia_multiplier`.
- The CAD report has useful component mass and COM evidence, but the exported
  runtime inertia remains a collapsed simple box, not a component-derived tensor.

This ticket exists because the simple-box inertia path is not a trustworthy
physics authority for B2.

## Ownership Boundary

### Flow CAD Owns

Reusable exporter/reporting behavior:

- composite inertia tensor math
- missing metadata validation
- generated URDF/report schema
- reusable tests for composite inertia and fail-loud metadata handling

Likely source files:

```text
/home/gnulnx/flow-cad/src/flow_cad/urdf_export.py
/home/gnulnx/flow-cad/src/flow_cad/urdf_inertia_report.py
/home/gnulnx/flow-cad/tests/test_urdf_export.py
/home/gnulnx/flow-cad/tests/test_urdf_inertia_report.py
```

### B3 Robot Owns

B2-specific geometry, measured masses, estimated panel masses, and the new
target registration:

```text
/home/gnulnx/b3_robot/flow/urdf.py
/home/gnulnx/b3_robot/flow/registry.py
/home/gnulnx/b3_robot/flow/assemblies/robot.py
/home/gnulnx/Downloads/B2 parts weights - Sheet1.csv
```

### Dojo Owns

The consumer/load path. Dojo changes are out of scope unless review proves the
new `B2_v3.urdf` cannot be consumed correctly without a small, explicit Dojo
asset-loading patch.

Relevant Dojo files for review only:

```text
/home/gnulnx/BLR/DojoV2/src/dojo/assets/B2_v2.urdf
/home/gnulnx/BLR/DojoV2/src/dojo/sim/balance_bot_sim_adapter.py
/home/gnulnx/BLR/DojoV2/src/dojo/worlds/balance_world_v2.py
/home/gnulnx/BLR/DojoV2/src/dojo/worlds/utils.py
/home/gnulnx/BLR/DojoV2/src/dojo/scripts/b2_physical_plant_report.py
/home/gnulnx/BLR/DojoV2/docs/b2/physical_plant_diagnostic_2026-06-25.md
```

## Target Artifacts

Add a new B3 URDF target:

```text
target name: b2_v3
robot name:  B2_v3
output:      /home/gnulnx/BLR/DojoV2/src/dojo/assets/B2_v3.urdf
report:      /home/gnulnx/BLR/DojoV2/src/dojo/assets/B2_v3.urdf.report.json
```

Keep the existing `b2_v2` target unchanged.

The generated `B2_v3.urdf` must preserve these Dojo-facing names unless a
separate Dojo review explicitly approves otherwise:

```text
base_link
chassis_link
left_wheel
right_wheel
chassis_joint
left_wheel_joint
right_wheel_joint
```

Wheel parameters must remain anchored to measured/current B2 values:

```text
wheel_base_m ~= 0.51
wheel_radius_m ~= 0.13
left/right wheel mass ~= 5.80595 kg each
```

## Required Physics Model

`B2_v3` must compute the non-wheel body as a collapsed `chassis_link` inertial
body while leaving the two wheel links as separate wheel masses.

### Inclusion Rules

Include all non-wheel active assembly occurrences that have mass and spatial
bounds/COM evidence.

Exclude from the collapsed chassis body:

- `left_wheel`
- `right_wheel`
- `reference_wheel` occurrences
- any wheel-only reference geometry
- the fixed base/dummy axle mass already represented by `base_link`

Do not double count wheel masses in the collapsed body mass or COM.

### Component Mass Requirements

For every included occurrence, record:

- occurrence name
- part id
- mass kg
- mass source
- local COM source
- assembly COM
- bounds source
- inertia source
- whether the mass/inertia is measured, estimated, or placeholder

If a component is heavy and required for dynamics, missing mass or missing
placement data must fail loud. Do not treat it as zero.

Suggested initial heavy threshold:

```text
0.100 kg
```

This threshold can be configurable, but it must not be a silent hidden default.

### Missing 3 mm Panel Mass Estimation

Missing 3 mm panels must be estimated from the other measured panels that are
already present instead of being ignored.

Implementation requirement:

1. Find same-family sibling panels with measured mass where possible.
   Examples include measured side panels or top plates in the B3 registry.
2. Compute a mass-per-area or mass-per-volume basis from measured siblings:

```text
mass_per_area = measured_mass_kg / measured_panel_area_mm2

estimated_mass_kg =
  mass_per_area
  * missing_panel_area_mm2
  * (missing_panel_thickness_mm / measured_panel_thickness_mm)
```

3. Prefer same material, thickness, shell count, and infill settings.
4. If same-family siblings are unavailable, use a project-level 3 mm panel
   estimator only if it is explicitly named and reported.
5. If material differs, do not reuse the estimate without a material correction
   or a fail-loud warning. TPU and PETG panels should not be mixed silently.
6. Record every estimated panel in the report with:

```text
mass_source = "estimated_from_measured_panel_area"
metadata_status = "estimated"
source_panel_ids = [...]
area_ratio = ...
thickness_ratio = ...
estimated_mass_kg = ...
```

7. Report the total estimated panel mass separately from measured mass.

This is acceptable for small panels because ignoring them biases COM/inertia and
makes the report look cleaner than the model really is. The report must make it
obvious which mass is measured and which mass is inferred.

### Inertia Tensor Requirements

Compute the full collapsed body inertia tensor about the collapsed body COM in
the `chassis_link` inertial frame.

Required tensor fields:

```text
ixx
ixy
ixz
iyy
iyz
izz
```

Use SI units:

```text
kg
m
kg*m^2
```

Local component inertia source order:

1. Use explicit `inertia_kg_m2` metadata when present.
2. Otherwise estimate local inertia from the occurrence bounding box and mass.
3. Mark the box-derived value as estimated.

For every component:

1. Convert the local component inertia into the assembly/chassis frame.
2. Shift it to the collapsed body COM with the parallel-axis theorem.
3. Sum tensor terms.

The current `compute_chassis_pitch_inertia_report()` style is a useful starting
point, but `B2_v3` needs the full tensor, not only pitch `IYY`.

### Frame Requirements

Use the current B3/Flow CAD frame mapping explicitly:

```text
B3 / Flow CAD:
  +X = robot left/right width
  +Y = robot front/rear depth
  +Z = vertical

URDF / Dojo:
  +X = fore/aft
  +Y = left/right
  +Z = vertical
```

All emitted URDF origins and inertias must be expressed in the link frame named
by the URDF element.

`chassis_link` is fixed above `base_link` by `chassis_joint`. Its inertial origin
is the collapsed body COM expressed in `chassis_link`, not whole-robot COM.

## Dojo Consumer Gate

The current Dojo render path formats the URDF template and computes simple box
inertia from `flow_cad_chassis_box`.

That means a generated numeric inertia tensor in `B2_v3.urdf` is not enough by
itself unless Dojo actually respects it.

Before this ticket is accepted, prove one of these:

1. `B2_v3.urdf` remains a template but includes enough metadata for Dojo to fill
   component-derived `IXX/IYY/IZZ` instead of simple box inertia.
2. `B2_v3.urdf` emits numeric inertial fields and Dojo can load it without
   replacing them with simple box values.
3. A separate, explicit Dojo patch is proposed for review that makes the B2
   load path respect the generated tensor.

Do not hide this as a Flow CAD-only success. If Dojo still overwrites the tensor
with simple box inertia, the physics fix has not landed.

Also verify whether the B2 PyBullet load should use `URDF_USE_INERTIA_FROM_FILE`.
If not changed, the report must state whether Bullet-adjusted inertia or
URDF-file inertia is the simulation baseline.

## Report Requirements

`B2_v3.urdf.report.json` must include:

- target name and output path
- assembly id and active profile
- whole assembly mass and COM
- wheel mass total and individual wheel masses
- base/dummy axle mass
- collapsed non-wheel body mass
- collapsed non-wheel body COM in root and `chassis_link` frames
- full collapsed body inertia tensor about collapsed body COM
- per-component inertia contributions
- measured mass total
- estimated mass total
- missing/skipped mass total
- estimated 3 mm panel ledger
- excluded wheel/reference ledger
- comparison against old simple-box `flow_cad_chassis_box` inertia
- effective ratio between composite `IYY` and old simple-box `IYY`
- comparison to recent Dojo multiplier values such as `x3`, `x5`, `x6`, and `x9`

The report should make it easy to answer:

```text
How much of the current x9 behavior can be explained by better measured
component inertia, and how much remains unexplained?
```

## Tests Required

Flow CAD tests:

- composite full-tensor inertia math for at least two offset components
- wheel/reference mass exclusion from collapsed chassis body
- fixed base/dummy mass exclusion
- missing heavy mass fails loud
- missing heavy bounds/COM fails loud
- missing 3 mm panel mass gets estimated from measured sibling panels and is
  reported as estimated
- generated `b2_v3` report includes measured/estimated/missing mass ledgers
- generated URDF preserves Dojo-facing link and joint names

B3 project tests or validators:

- `b2_v2` target still exists and points at `B2_v2.urdf`
- `b2_v3` target exists and points at `B2_v3.urdf`
- current active assembly placements still include wheel boxes, loaded trays,
  reference wheels, battery compartment, VESC tray, buck tray, and compute shelf
- no generated B2 v3 source path hardcodes unrelated workstation paths beyond
  the existing explicit target output path

Dojo review/smoke checks:

- B2 v3 URDF XML parses
- PyBullet loads the generated/rendered model
- `left_wheel_joint` and `right_wheel_joint` resolve by name
- `chassis_link` mass, COM, and inertia loaded in Bullet match the B2 v3 report
  within an explicit tolerance
- if Bullet adjusts inertia without `URDF_USE_INERTIA_FROM_FILE`, report the
  adjusted values and decide deliberately whether that is acceptable

## Suggested Validation Commands

From Flow CAD:

```bash
cd /home/gnulnx/flow-cad
python -m pytest tests/test_urdf_export.py tests/test_urdf_inertia_report.py
```

After Flow CAD runtime changes:

```bash
python -m pip install -e /home/gnulnx/flow-cad
```

From B3:

```bash
cd /home/gnulnx/b3_robot
flow cad build
```

Then generate only the explicit new URDF target with the current Flow CAD CLI
syntax for URDF targets. Confirm the command before running it; do not guess if
the CLI surface has changed.

From Dojo, run the existing B2 physical plant report/smoke path against a config
that points at `B2_v3.urdf`. The exact config should be review-created, not
silently edited into an active training config.

## Acceptance Criteria

This ticket is accepted only when:

- `B2_v2.urdf` remains unchanged unless a separate approval says otherwise.
- `B2_v3.urdf` and `B2_v3.urdf.report.json` are generated from source.
- Current B2 occurrence visual/collision geometry is preserved.
- The non-wheel body mass excludes wheel links and base dummy mass.
- Missing 3 mm panel masses are estimated from measured sibling panels and
  reported as estimates.
- Heavy missing masses or placements fail loud.
- The report contains a full component ledger, not just summary values.
- The report contains full `IXX/IXY/IXZ/IYY/IYZ/IZZ` composite inertia.
- Dojo either consumes the composite tensor or the remaining Dojo blocker is
  explicitly documented with the exact file/function that must change.
- PyBullet-loaded mass, COM, and inertia are checked against the report.

## Reviewer Checklist

When Codex reviews this work, reject it if any of these are true:

- The work overwrites `B2_v2.urdf` instead of creating `B2_v3.urdf`.
- The visual/collision boxes are updated but inertial physics is still simple
  box inertia.
- Measured B3 registry weights are ignored.
- Missing panel masses are treated as zero.
- Estimated panels are mixed with measured masses without source labels.
- Wheel masses are double counted into `chassis_link`.
- `COM_Z` is whole-robot COM instead of collapsed non-wheel body COM relative to
  `chassis_link`.
- The full tensor is not reported.
- Dojo still overwrites the tensor with `flow_cad_chassis_box` simple-box
  inertia and the work claims success anyway.
- Any active training, VCB, reward, or deploy behavior is modified as part of
  this ticket without explicit approval.

