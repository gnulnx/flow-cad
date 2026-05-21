# 3D Part Viewer

A browser-based 3D model viewer built with Three.js for validating CAD parts before printing.

## Features

- **File Loading**: Supports STL, OBJ, GLTF/GLB, and STEP file formats
- **STEP Support**: CAD STEP files (.step/.stp) converted via lightweight backend server
- **Interactive Navigation**: OrbitControls for rotate, pan, and zoom
- **Auto-centering**: Models are automatically centered and scaled to fit the view
- **Status Information**: Displays model name, triangle count, and bounding box dimensions
- **Responsive Design**: Adapts to different screen sizes

## Usage

### Opening Directly in Browser (Simplest)

1. Open `index.html` directly in a modern web browser:
   ```bash
   # On Linux with xdg-open
   xdg-open viewer/index.html
   
   # Or simply double-click the file in your file manager
   ```

### Using a Local HTTP Server (Recommended for best compatibility)

Some browsers restrict certain features when opening files directly. For best results, serve the files via HTTP:

```bash
# Using Python's built-in server
python -m http.server 8080 --directory viewer

# Then open in browser:
# http://localhost:8080
```

Or with Node.js:
```bash
npx serve viewer
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

- **STL** (`.stl`) - Standard for 3D printing, binary and ASCII supported
- **OBJ** (`.obj`) - Wavefront object format with geometry data
- **GLTF/GLB** (`.gltf`, `.glb`) - Modern web-friendly 3D format
- **STEP** (`.step`, `.stp`) - CAD exchange format (requires converter server)

### STEP File Support

STEP files require the converter server to be running. Start it before opening the viewer:

```bash
# Start the STEP converter server
python viewer/step_converter.py
```

The server runs on `http://localhost:8765` by default and converts STEP files to STL format on-the-fly using cadquery.

**Custom port/host:**
```bash
python viewer/step_converter.py --host 0.0.0.0 --port 8080
```

If you get a "Failed to fetch" error when loading a STEP file, make sure the converter server is running.

## Architecture

This viewer follows a hybrid approach:

### Client-Side (index.html)

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
│  │   ├── GLTFLoader              │  │
│  │   └── STEP Handler → Server   │  │
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

### Server-Side (step_converter.py)

```
┌─────────────────────────────────────┐
│      step_converter.py              │
│                                     │
│  ┌───────────────────────────────┐  │
│  │   FastAPI Server              │  │
│  │   POST /convert               │  │
│  └───────────────────────────────┘  │
│                                     │
│  ┌───────────────────────────────┐  │
│  │   cadquery (OCCT)             │  │
│  │   ├── STEP Importer           │  │
│  │   └── STL Exporter            │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

**Data Flow for STEP Files:**
1. User selects `.step` file in browser
2. Browser sends file to `http://localhost:8765/convert`
3. Server uses cadquery to parse STEP and export as STL
4. STL data returned to browser
5. Three.js STLLoader displays the model

## Technical Notes

- Uses Three.js v0.160.0 loaded from unpkg CDN
- No build step required - pure HTML/CSS/JavaScript
- All file processing happens client-side via FileReader API (except STEP)
- **STEP files require the converter server** (`step_converter.py`) to be running
- Converter uses cadquery with OpenCascade for accurate STEP parsing

## Future Enhancements (See Brainstorm Document)

Potential features for future tickets:
- Measurement tools (vertex-to-vertex, edge measurements)
- Model comparison side-by-side
- Export annotated screenshots
- Mesh repair/simplification options
- Support for larger files via Web Workers

## License

Same as parent project.
