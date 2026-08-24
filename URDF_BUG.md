# B2 URDF Export Bug

## Context

The current `B2_v2.urdf` export is XML-valid and loads in Dojo/PyBullet, but it is not a faithful enough physics model for B2 balance training.

The live Flow CAD view shows the real B2 assembly has large wheel-box/lower-body structures beside and above the axle. Those structures are not represented in the exported URDF collision model. The generated URDF currently simplifies the robot to:

- `base_link`: small axle cylinder at wheel axle midpoint.
- `chassis_link`: one simplified body box fixed above the axle.
- `left_wheel` / `right_wheel`: primitive wheel cylinders.

That simplification misses the low wheel-box contact geometry that controls how the robot contacts the ground during large pitch/roll excursions.

## Observed Failure

In the current generated Dojo asset:

- `/home/gnulnx/BLR/DojoV2/src/dojo/assets/B2_v2.urdf`
- `/home/gnulnx/BLR/DojoV2/src/dojo/assets/B2_v2.urdf.report.json`

the wheel-box structures visible in Flow CAD are absent from URDF visual/collision geometry. This means PyBullet can train with a different fall/contact envelope from the real robot.

This matters for B2 because the wheel boxes are large enough to define real ground contact before the simplified body shape would. A policy trained against the simplified URDF can learn recovery/fall behavior that does not match the physical robot.

## Separate COM Recommendation Bug

The sidecar report currently recommends:

```toml
com_dx_range = [-0.0000300168, -0.0000300168]
com_dz_range = [-0.093146026, -0.093146026]
urdf_chassis_mass_choices = [7.320275]
```

That `com_dz_range` appears to be derived from the whole-robot assembly COM while the URDF still keeps wheel masses as separate links. Applying it directly to `chassis_link` double-counts the wheel masses' low COM effect.

With the current URDF structure:

- `base_link` dummy mass: `0.1 kg`
- wheel links: roughly `5.9 kg` each
- `chassis_link` placeholder mass: `7.320275 kg`
- `chassis_joint` z offset: `0.144 m`

using `COM_Z = -0.093146026` places the non-wheel body lump about `0.051 m` above the axle. Because the wheels are already modeled separately at the axle, the total robot COM becomes roughly `0.019 m` above the axle, not the report's whole-robot COM of roughly `0.051 m` above the axle.

The recommendation should instead compute the `chassis_link` COM for the non-wheel body lump after subtracting the wheel/base links that remain in the URDF. For the current exported masses, that value is closer to:

```toml
com_dz_range = [-0.011, -0.011]
```

not `-0.093`.

## Likely Owning Code

Start in:

- `src/flow_cad/urdf_export.py`
  - `_build_dojo_balance_bot_template(...)`
  - `_dojo_config_recommendations(...)`
  - report mass-property aggregation around `recommended_chassis_mass_kg`

The downstream target hook is in the B3 project, not this runtime repo. Re-check the current project hook before editing exact target parameters.

## Fix Direction

Keep the Dojo adapter contract stable:

- Preserve `left_wheel_joint` and `right_wheel_joint` names.
- Preserve the placeholders Dojo fills at runtime:
  - `{CHASSIS_MASS}`
  - `{COM_X}`
  - `{COM_Z}`
  - `{IXX}`
  - `{IYY}`
  - `{IZZ}`
- Do not overwrite `B2.urdf`; regenerate `B2_v2.urdf` or a versioned sibling.

Improve the exported physics model:

1. Add lower-body / wheel-box collision geometry to the generated URDF.
   - Prefer extra `<collision>` primitives on an existing fixed body link if possible, so wheel joint indexing is not disturbed.
   - If extra fixed links are required, add a Dojo adapter smoke test to prove wheel joint lookup still resolves correctly by name.
2. Keep visuals simple if needed, but collision geometry must include the wheel-box contact envelope.
3. Fix recommended COM values so `CHASSIS_MASS` and `COM_Z` represent the collapsed non-wheel body lump, not whole-robot COM when wheel links remain separate.
4. Emit enough report fields to audit:
   - whole assembly mass/COM
   - wheel link mass total
   - fixed base/dummy mass
   - recommended collapsed chassis/body mass
   - recommended collapsed chassis/body COM relative to `chassis_link`

## Validation Needed

After regenerating:

1. Parse generated URDF XML.
2. Load in PyBullet.
3. Run the Dojo balance-bot adapter smoke check and confirm left/right wheel joints resolve correctly.
4. Inspect or test URDF collision geometry to verify the wheel-box/lower-body contact envelope is present.
5. Compare the sidecar report's recommended Dojo config against the generated URDF masses:
   - whole-robot COM should match the assembly report
   - collapsed body COM should only account for mass not already represented by wheel/base links
6. Re-run B2 training with the corrected URDF and corrected Dojo config values.

## Current Working Notes

The current lower-authority B2 training config was already adjusted manually toward:

```toml
wheel_base_m = 0.51
wheel_radius_m = 0.127
torque_limit = 4.5
torque_slew_limit = [0.16, 0.24]
current_limit_a = 2.4
max_action = 1.0
action_slew_per_sec = 4.0
```

Do not treat those as final exporter defaults. They are current B2 bring-up values and should remain project/config-owned unless generalized deliberately.
