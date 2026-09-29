# Measurement and part examination

Open **Measure** with its toolbar button, **Ctrl/Cmd+M**, or **M**. Shortcuts do
not consume typing in an editor, search box, or selector. Measurement uses the
selected visible part; the panel names that part.

## Automatic gestures

- **Click a straight edge** to show its full length.
- **Drag from an edge or point** to another target to measure their distance.
- **Click two points** for the same distance without holding the mouse button.
- A live green tape and value follow the second target. Completed tapes keep a
  constant 3.5-pixel width as the camera zooms.
- **Escape** cancels an unfinished measurement; Escape again exits Measure.
- Right/middle drag pans, and the wheel zooms. Exit Measure to orbit normally.

Vertices have a small picking preference over nearby edges, so corners remain
selectable. **Snap** can restrict picking to vertices, edges, or circle centers.
The circle-center filter is useful for screw-hole spacing; hovering also shows
the circle diameter. A circular edge is not automatically classified as a hole.
**Edge length only** is available when every click should target a straight edge.

STEP vertices, circle centers, and straight-edge points use exact topology.
Perspective edge interpolation includes depth rather than treating screen-space
fractions as world-space fractions. Sampled mesh inputs remain approximate.
Labels show total distance, signed X/Y/Z deltas, and measurement quality. They
can be hidden, pinned, moved, deleted, or cleared. Existing thread/revision-bound
measurement persistence remains in use.

## Free space

Free points are opt-in. Choose **View plane**, **XY**, **XZ**, or **YZ**. Before
the start is chosen, the plane passes through the selected part's displayed
center. After choosing the start, it passes through that point. Exact snaps
still take precedence. Plane-based endpoints and their distances are labeled
**Approximate**: the plane supplies depth; a screen click alone cannot establish
an arbitrary 3D point. Edge-on planes and points outside the canvas are rejected.

## Dimensions

**Dimensions** displays width X, depth Y, and height Z, with callouts beside the
geometry. Choose **Selected part** or **All visible parts**. Hidden parts are
excluded. While geometry is loading, the panel marks the result incomplete.

These are approximate, axis-aligned **display bounds in world coordinates**.
They are not a minimum oriented box or a manufacturing tolerance measurement.
Use exact feature measurements for hole spacing and interface dimensions. Mass
is not inferred from a bounding box; a future mass summary needs known component
masses or material density and trustworthy solid volume.

## Scope

This pass covers measurement within the selected part, including a composite
STEP review view, and dimensions across the visible scene. Exact distances
between separately registered parts need an assembly-level endpoint/revision
contract before saved measurements can track both inputs correctly. Curved-edge
arc length, face clearance, wall thickness, and automatic hole classification
are separate analysis features.

Topology is requested when Measure is opened, rather than during ordinary part
browsing. Annotation drawing and measurement gestures are mutually exclusive;
switching tools preserves existing annotations and completed measurements.
