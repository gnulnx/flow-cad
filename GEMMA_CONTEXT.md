# GEMMA_CONTEXT.md - B2 Robot Chassis Refactor

## Current State & Goal
We are in the middle of a mechanical refactor for the Erb B2 balance bot lower chassis. The primary goal is to fix a critical assembly issue with the **detachable rear panel bumpout**.

### The Core Issue (The "T-Slot" Problem)
The T-slot tongues on the detachable bumpout shell were flush with the perimeter walls of the part. This meant that when attempting to slide the bumpout into the rear panel, the outer walls hit first, preventing the T-slots from ever entering their corresponding slots in the rear panel.

**Required Fix:** The T-slots must extend horizontally (X-axis) beyond the side boundaries of the bumpout shell to provide a "lead-in" that allows them to engage with the rear panel before the main body makes contact.

## Recent Failures & Pitfalls
1.  **Wrong Axis Extension**: An attempt was made to fix this by extending the T-slots, but they were extended along the Z-axis (vertical), causing them to poke through the top and bottom of the part.
2.  **Build Volume Violation**: A 10mm extension was attempted for visibility, which pushed the total part width beyond the P2S build volume limit (256mm). The current target is a modest **2mm extension**.
3.  **Assembly Corruption**: Recent changes to `make_assembly` in `cad/erb_lower_chassis.py` have broken the final assembly export. Most parts are now missing from the `erb_lower_chassis_assembly.step` file, leaving only a few floating components.

## Technical Details
- **Primary Source**: `cad/erb_lower_chassis.py`
- **Target Function**: `make_rear_panel_detachable_bumpout_shell()`
- **Key Parameters**: `P.rear_slide_tongue_height` (used for the extension width), `P.rear_bumpout_width`.
- **Assembly Logic**: The logic in `make_assembly` needs to be restored so that all components defined in `ASSEMBLY_PLACEMENTS` are correctly included in the final `Compound`.

## Pending Tasks
1.  **Fix Assembly**: Restore `make_assembly` so all chassis parts (side plates, front panel, tray, shelves, etc.) appear in the assembly STEP file.
2.  **Correct Bumpout Geometry**: Ensure T-slots extend ~2mm along the X-axis beyond the shell walls, NOT the Z-axis.
3.  **Verify Build Volume**: Ensure `rear_panel_detachable` stays under 256mm.
4.  **Sync to Viewer**: Run `python cad/erb_lower_chassis.py && python scripts/sync_text_to_cad.py --skip-cad-generate`.
