# 3D Part Viewer

A browser-based 3D model viewer built with Three.js for validating CAD parts before printing.

## Features

- **File Loading**: Supports STL, OBJ, GLTF/GLB file formats natively in browser
- **No Server Required**: Drag-and-drop STL files directly into the browser — zero setup
- **Interactive Navigation**: OrbitControls for rotate, pan, and zoom
- **Auto-centering**: Models are automatically centered and scaled to fit the view
- **Status Information**: Displays model name, triangle count, and bounding box dimensions
- **Responsive Design**: Adapts to different screen sizes

## Quick Start (No Server Needed)

### 1. Build your CAD parts (generates both STEP and STL):

```bash
cd ~/flow-cad
flow cad build
```

This creates:
- `b3/exports/step/` — Parametric STEP files (for FreeCAD, archival)
- `b3/exports/stl/` — Mesh STL files (for quick viewing, 3D printing)

### 2. Open the viewer in your browser:

```bash
# Linux
xdg-open ~/flow-cad/viewer/index.html

# Or just double-click viewer/index.html in your file manager
```

### 3. Drag-and-drop any `.stl` file from `b3/exports/stl/` into the browser!

**That's it.** No server, no installation, no configuration.

---

## Why STL Instead of STEP?

**STEP files are complex CAD formats** with parametric surfaces, assemblies, and manufacturing metadata. They cannot be parsed natively in browsers without heavy WASM libraries or a backend converter server.

**STL files are simple mesh formats** that browsers can load instantly via Three.js. The geometry fidelity is more than sufficient for:
- Visual inspection before printing
- Checking fit/clearance between parts  
- Verifying orientation and scale
- Measuring dimensions (visually)

The STL export happens automatically during `flow cad build` — you get the best of both worlds:
- **STEP** for archival, parametric editing in FreeCAD
- **STL** for instant browser-based visual validation

## Usage

### Opening Directly in Browser (Simplest)

1. Open `index.html` directly in a modern web browser:
   ```bash
   # On Linux with xdg-open
   xdg-open viewer/index.html
   
   # Or simply double-click the file in your file manager
   ```

2. Click "Open File" or drag-and-drop any `.stl`, `.obj`, or `.gltf`/`.glb` file.

### Using a Local HTTP Server (Optional, for best compatibility)

Some browsers restrict certain features when opening files directly via `file://`. For best results:

```bash
# Using Python's built-in server
python -m http.server 8080 --directory viewer

# Then open in browser:
# http://localhost:8080
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `R` | Reset camera view |
| `?` | Toggle info panel |

## Mouse Controls

| Action | Control |
|--------|---------|
| Rotate | Left-click + drag |
| Pan | Right-click + drag or Middle-click + drag |
| Zoom | Scroll wheel |

## Supported File Formats

- **STL** (`.stl`) — Standard for 3D printing, binary format, instant browser loading ⭐
- **OBJ** (`.obj`) — Wavefront object format with geometry data
- **GLTF/GLB** (`.gltf`, `.glb`) — Modern web-friendly 3D format

> **Note:** STEP files are exported alongside STL during `flow cad build` for archival and FreeCAD editing, but the browser viewer uses STL files for instant, serverless viewing.

## Architecture

This viewer is intentionally simple — a single HTML file that loads 3D models directly in the browser.

```
┌─────────────────────────────────────┐
│         index.html                  │
│                                     │
│  ┌───────────────────────────────┐  │
│  │   Three.js Scene              │  │
│  │   ├── Camera (Perspective)    │  │
│  │   ├── Renderer (WebGL)        │  │
│  │   ├── Lighting                │  │
│  │   └── Model Mesh              │  │
│  └───────────────────────────────┘  │
│                                     │
│  ┌───────────────────────────────┐  │
│  │   Loaders (via CDN)           │  │
│  │   ├── STLLoader               │  │
│  │   ├── OBJLoader               │  │
│  │   └── GLTFLoader              │  │
│  └───────────────────────────────┘  │
│                                     │
│  ┌───────────────────────────────┐  │
│  │   UI Components               │  │
│  │   ├── Toolbar                 │  │
│  │   ├── Status Bar              │  │
│  │   ├── Info Panel              │  │
│  │   └── Loading Overlay         │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

**No backend server required.** All file processing happens client-side via the browser's FileReader API.

## Technical Notes

- Uses Three.js v0.160.0 loaded from unpkg CDN
- No build step required — pure HTML/CSS/JavaScript
- All file processing happens client-side via FileReader API
- **No server needed** — just open `index.html` and drag-drop STL files
- STL files are automatically generated alongside STEP during `flow cad build`

## Future Enhancements

Potential features for future tickets:
- Measurement tools (vertex-to-vertex, edge measurements)
- Model comparison side-by-side
- Export annotated screenshots
- Mesh simplification options for large files
- Support for loading multiple parts simultaneously

## License

Same as parent project.
