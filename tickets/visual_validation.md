# Project B3: Visual Regression Snapshots Implementation Tickets

This document defines the structured engineering roadmap and tickets for implementing **Visual Regression Snapshots (Item #3 from Gemini Suggestions)**.

## Architectural Goal
To accelerate human design reviews and enable automated agentic self-correction loops, we will implement an automatic 2D projection and SVG export pipeline within the B3 build process. For every registered part, `flow cad build` will export three principal orthographic views (Top, Front, Side) as text-diffable vector graphics under `b3/exports/snapshots/`.

---

## Phase 1: Core Projection & Exporter Infrastructure

### VIS-1.1: Core 2D Projection Utility
* **Goal**: Implement a clean 2D projection function leveraging `build123d`'s camera projection API.
* **Requirements**:
  - Create `src/flow_cad/core/snapshots.py`.
  - Implement a core function `project_part_views(shape, part_id: str) -> dict[str, tuple[Edges, Edges]]` that projects a 3D solid or shape onto three orthogonal views:
    - **Top (XY)**: Looking down from `+Z` towards the part center.
    - **Front (XZ)**: Looking from `-Y` through to the back of the part.
    - **Side (YZ)**: Looking from `-X` through to the right of the part.
  - Call `.project_to_viewport()` with orthographic settings (`focus=None`).
  - Correctly extract and return the tuple of `(visible_edges, hidden_edges)` for each view.
* **Verification**:
  - Write unit tests in `test/test_snapshots.py` that pass a basic shape (e.g., `Box(10, 20, 30)`) to the projection function and verify that it returns three views with non-empty edge lists.
* **Completed**:
  - Implemented `project_part_views` inside `src/flow_cad/core/snapshots.py` generating Top (XY), Front (XZ), and Side (YZ) orthographic views using `.project_to_viewport(focus=None)`.
  - Added unit test coverage in `tests/test_snapshots.py`.

### VIS-1.2: Styled SVG Exporter with Margin Scaling
* **Goal**: Render the projected 2D edges to SVG files with clean line styles and proportional viewport bounds.
* **Requirements**:
  - Integrate `build123d.ExportSVG` inside `src/flow_cad/core/snapshots.py`.
  - Establish standard layers and line weights:
    - **Visible Layer**: Solid black lines (`stroke="#000000"`, `stroke-width="0.5"`) representing outer contours and through-features.
    - **Hidden Layer**: Dashed gray lines (`stroke="#808080"`, `stroke-width="0.3"`, `stroke-dasharray="2,2"`) representing internal cavities, insert pilots, and pocket steps.
  - Dynamically calculate the bounding box of the projected 2D geometry for each view.
  - Apply a uniform 10% padding/margin around the bounding box to ensure shapes never clip the SVG viewport boundary.
  - Add XML comment headers inside each generated SVG file embedding part metadata (e.g., generating package version, part ID, bounding box dimensions, and timestamp).
* **Verification**:
  - Verify that the generated SVGs can be parsed cleanly by standard XML libraries and open perfectly in modern web browsers (e.g., Chrome, Firefox).
* **Completed**:
  - Added `export_part_snapshots` in `src/flow_cad/core/snapshots.py` using `build123d.ExportSVG` with standard styling (solid black visible, dashed gray hidden).
  - Implemented dynamic bounding box margins (10% padding, minimum 5mm) and `fit_to_stroke=True`.
  - Configured custom XML post-processing to prepend a detailed comment header block with part ID, view, physical bounding box size, and timestamp.
  - Verified SVG compatibility through XML-parsing unit tests in `tests/test_snapshots.py`.

---

## Phase 2: CLI Integration & Registry Build Loop

### VIS-2.1: Integrate Snapshots into the Part Exporter
* **Goal**: Hook snapshot generation directly into the main `Exporter` build sequence.
* **Requirements**:
  - Modify `src/flow_cad/core/assembly.py` where part files are written.
  - Ensure that after writing a part's `.step` file, the exporter calls the projection and SVG export pipeline.
  - Save output files under `b3/exports/snapshots/{module_id}/{part_id}_{view}.svg` (e.g., `b3/exports/snapshots/lower_chassis/b3_lower_chassis_left_side_plate_top.svg`).
  - Ensure folders are automatically created during the build if they do not exist.
  - Skip snapshotting for reference-only parts or non-printable assemblies unless explicitly desired.
* **Verification**:
  - Run `flow cad build` and verify that the `b3/exports/snapshots/` folder is cleanly populated with SVGs matching all registered printable parts.
* **Completed**:
  - Integrated `export_part_snapshots` call within the `Exporter.export()` workflow in `src/flow_cad/core/assembly.py`.
  - Snapshots are written to `b3/exports/snapshots/{module_id}/{part_id}_{view}.svg`.
  - Wrapped snapshot generation with `is_printable` check to only snapshot printable parts (skipping the full assembly and non-printable items).

### VIS-2.2: Add CLI Control Flags
* **Goal**: Add CLI arguments to `flow cad build` to control snapshot behavior.
* **Requirements**:
  - Modify `src/flow_cad/cli.py` click command parameters.
  - Add a `--no-snapshots` boolean flag to the `build` command to skip snapshot rendering completely (useful for fast step-only builds).
  - Add a `--snapshots-only` boolean flag to regenerate ONLY the SVG snapshots without rebuilding the heavy `.step` geometry files (useful for fast style-tweak iterations).
* **Verification**:
  - Run `flow cad build --no-snapshots` and verify no SVGs are generated.
  - Run `flow cad build --snapshots-only` and verify that SVGs are refreshed while existing STEP files remain unmodified.
* **Completed**:
  - Added `@click.option("--snapshots/--no-snapshots", default=True)` and `@click.option("--snapshots-only", is_flag=True, default=False)` to the `build` command in `src/flow_cad/main.py`.
  - Configured `Exporter` to dynamically accept and act on these flags.
  - Ensured `Exporter.clear()` is bypassed when `--snapshots-only` is provided, preserving existing STEP files.

---

## Phase 3: CI/CD & Regression Verification

### VIS-3.1: Automated Regression/Consistency Test
* **Goal**: Prevent accidental commits of broken or empty snapshots and protect geometry consistency.
* **Requirements**:
  - Add a comprehensive unit test suite in `test/test_visual_snapshots.py`.
  - Loop over every registered part in the `REGISTRY` and verify that:
    - SVGs can be built for each of the three standard views.
    - SVG files contain actual vector paths (e.g., `<path>`, `<circle>`, `<line>`), flagging errors if an empty/blank SVG is produced.
  - Implement a basic git-safety checker script to ensure visual snapshots are tracked and updated whenever a CAD source file is modified.
* **Verification**:
  - Run `python -m pytest` to confirm that all visual snapshot tests pass.
