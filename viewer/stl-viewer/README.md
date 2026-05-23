# STL Viewer

React/Three.js viewer for inspecting generated STL exports.

Run from the repository root:

```bash
npm --prefix viewer/stl-viewer install
npm --prefix viewer/stl-viewer run dev
```

Then open:

```text
http://127.0.0.1:3000/
```

Drag/drop STL files, use Open File, or load a generated export directly:

```text
http://127.0.0.1:3000/?stl=/exports/stl/lower_chassis/b3_lower_chassis_simple_mounting_plate.stl
```

The app source lives here. Generated STL artifacts stay under `b3/exports/stl/`.
