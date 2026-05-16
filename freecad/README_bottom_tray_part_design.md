# Bottom Tray Part Design Editing Model

Open:

`/Users/jfurr/3DPrintBalanceBot/exports/freecad/native/erb_bottom_tray_part_design.FCStd`

This file is for manual FreeCAD editing. It is a single Part Design Body named
`Bottom Tray Body - edit this`.

## Basic Edit Workflow

1. Switch to the `Part Design` workbench.
2. In the model tree, double-click `Bottom Tray Body - edit this` to activate it.
3. Expand the Body.
4. Select a named feature:
   - `Pad_*` features add material.
   - `Pocket_*` features remove material.
5. In the lower-left `Data` tab, edit:
   - `Length`, `Width`, `Height` for pads.
   - `Radius`, `Height` for cylindrical pockets.
   - `Placement -> Position` to move a feature.
6. Press `F5` or use `Edit -> Refresh/Recompute`.

## Adding Material

1. Activate `Bottom Tray Body - edit this`.
2. Use Part Design's additive tools, such as `Additive Box`, or create a sketch
   on a face and use `Pad`.
3. Keep the new feature touching the existing tray body.

## Removing Material

1. Activate `Bottom Tray Body - edit this`.
2. Use `Subtractive Cylinder`, `Subtractive Box`, or create a sketch and use
   `Pocket`.
3. Place the subtractive feature so it intersects the solid.
4. Recompute.

## Important Limitation

This editable FreeCAD file is for visual/manual exploration. The production
STEP files are still generated from the Python CAD model. Once a manual edit is
confirmed, port the dimension or feature back into the Python generator.
