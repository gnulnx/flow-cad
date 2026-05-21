# 3D Part Viewer

A browser-based 3D model viewer built with Three.js for validating CAD parts before printing.

## Features

- **File Loading**: Supports STL, OBJ, and GLTF/GLB file formats
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

## Architecture

This viewer follows the "Browser-Based Single Page App" approach:

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

## Technical Notes

- Uses Three.js v0.160.0 loaded from unpkg CDN
- No build step required - pure HTML/CSS/JavaScript
- All file processing happens client-side via FileReader API
- No server-side dependencies needed

## Future Enhancements (See Brainstorm Document)

Potential features for future tickets:
- Measurement tools (vertex-to-vertex, edge measurements)
- Model comparison side-by-side
- Export annotated screenshots
- Mesh repair/simplification options
- Support for larger files via Web Workers

## License

Same as parent project.
