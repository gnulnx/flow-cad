# Visual Regression & Validation Strategy (Visual Snapshots)

This document details the architecture, benefits, and implementation details for **Visual regression snapshots (Item #3 from Gemini Suggestions)**.

## 1. Problem Statement & Motivation

Currently, validating a parametric CAD change in the B3 chassis requires:
1. Re-running the generator script to export new `.step` files.
2. Opening the STEP files in a heavy external graphical tool (such as FreeCAD or Bambu Studio), or syncing them to a three.js browser viewer.
3. Manually rotating and examining the geometry to verify that screw holes align, dovetails match, and wall boundaries are clear.

This introduces a high "feedback loop latency" for human developers and creates an extreme bottleneck for agentic AI workflows. An LLM agent cannot easily "look" at a 3D STEP file to verify if its parametric changes are correct or if they caused unintended regressions (like moving a hole off-center or burying a relief pocket inside a wall).

## 2. The Move: Automatic Orthographic SVG Previews

We will integrate an automatic, lightweight 2D projection pipeline directly into the export process. For every registered part, `flow cad build` will export three highly-detailed 2D SVG snapshots corresponding to the principal coordinate planes:
- **Top View (XY Plane)**: Looking from +Z down towards the bottom of the part.
- **Front View (XZ Plane)**: Looking from -Y through to the back of the part.
- **Side View (YZ Plane)**: Looking from -X through to the right of the part.

These SVGs are saved alongside the `.step` files under the project exports folder:
```text
b3/
├── exports/
│   ├── step/
│   │   └── lower_chassis/
│   │       └── b3_lower_chassis_left_side_plate.step
│   └── snapshots/
│       └── lower_chassis/
│           ├── b3_lower_chassis_left_side_plate_top.svg
│           ├── b3_lower_chassis_left_side_plate_front.svg
│           └── b3_lower_chassis_left_side_plate_side.svg
```

### Why SVG (Vector Graphics)?
- **Git Diffs**: SVGs are plain XML text. If a circle moves or a boundary changes, the git diff will show exactly which coordinate shifted.
- **Ultra-Lightweight**: SVGs are a few kilobytes, making them highly portable, cheap to commit, and rapid to load.
- **Browser-Native**: They render natively in any modern web browser, markdown editor, or file explorer, enabling instant review.
- **Resolution-Independent**: They can be scaled infinitely without losing edge crispness, which is essential for reading fine dimensions.

---

## 3. Technical Implementation Details (build123d)

We will leverage `build123d`'s technical drawing and projection capabilities to create these snapshots:

### 3.1 `project_to_viewport` for Orthographic Projections
To project a 3D solid onto a 2D viewport without perspective distortion, we call `.project_to_viewport()` with no focal distance (`focus=None`, which is the default).
We define three projection perspectives based on the part's bounding box:

```python
# 1. Top View (XY)
visible_xy, hidden_xy = part.project_to_viewport(
    viewport_origin=(0, 0, distance),
    viewport_up=(0, 1, 0),
    look_at=(0, 0, 0)
)

# 2. Front View (XZ)
visible_xz, hidden_xz = part.project_to_viewport(
    viewport_origin=(0, -distance, 0),
    viewport_up=(0, 0, 1),
    look_at=(0, 0, 0)
)

# 3. Side View (YZ)
visible_yz, hidden_yz = part.project_to_viewport(
    viewport_origin=(distance, 0, 0),
    viewport_up=(0, 0, 1),
    look_at=(0, 0, 0)
)
```

### 3.2 Styled Vector Line Representation
To produce readable blueprints, we will use `build123d`'s `ExportSVG` class. We will use a standard layer structure to separate visible outer features from internal/hidden features:

- **Visible Layer**: Black lines (`stroke="#000000"`, `stroke-width="0.5"`) representing outer boundaries, tabs, and open through-holes.
- **Hidden Layer**: Dashed gray lines (`stroke="#808080"`, `stroke-width="0.3"`, `stroke-dasharray="2,2"`) representing internal cavities, pocket lips, heat-set insert pilot holes, and washer counterbores.

### 3.3 Dynamic Viewport & Margin Scaling
Rather than using arbitrary zoom levels, we will calculate the bounding box of the projected 2D shapes and apply a small padding/margin (e.g. 5-10%). This ensures that parts of any scale (from a tiny 30mm insert to the full 256mm chassis) fit perfectly within their SVG viewports and remain highly legible.

---

## 4. Workflows and AI-Agent Benefits

### 4.1 Automated AI Self-Correction Loops
An agent implementing a feature (e.g., adding an insert retention flange) can:
1. Write the Python CAD code.
2. Run `flow cad build` to generate the new STEP and SVG snapshots.
3. Compare the newly generated SVG lines with the previous git commit.
4. Programmatically inspect the SVG paths (or count elements/circles) to verify that the required holes and flanges were added without breaking existing features.

### 4.2 Supercharged Human Code Review
When a PR is opened, the user does not have to pull the branch, run FreeCAD, and load the STEP files. Instead, they can simply inspect the file diff in Git.
- Git will show the vector text changes (e.g., `cx="75.0" cy="-75.0" r="2.75"` changing to `cx="75.0" cy="-70.0"`).
- Many git hosting services (like GitHub or GitLab) render visual SVG diffs side-by-side or as swipable overlays, allowing the user to spot physical regressions in seconds.

### 4.3 Documentation Autogen
The generated SVGs can be directly referenced in parts documentation, the `PRINT_MANIFEST.md`, or the `docs/PART_INTERFACES.md` files. This ensures that the documentation's illustrations are always 100% aligned with the parametric CAD source code.
