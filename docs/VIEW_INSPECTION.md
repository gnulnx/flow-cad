# Inspecting parts inside a view

Open a saved view or an assembly in the normal workbench. Its individual display
components are selectable immediately; they do not need separate catalog builds.

- **Click a part**, then **Hide** or **Isolate** in the inspection toolbar.
- Turn on **Click to hide** to peel away covers with successive clicks. Dragging
  still rotates the view. Press **Escape** to leave this mode.
- **Parts in view** opens a searchable list of the loaded components. Select a
  name to highlight it, or use its **Hide/Show** button.
- The **N hidden** button opens that list filtered to hidden components. Every
  hidden component remains available there, even when the entire view is hidden.
- **Undo** restores the previous visibility state, including the state before
  isolation. **Show all** restores all components in the currently loaded view.
- **Frame selected part** zooms to a selected visible component. **Fit** frames
  all visible geometry. Hiding or restoring does not change the camera.

Shortcuts outside text fields: **H** hides the selection, **I** isolates it,
**U** undoes visibility changes, and **Shift+H** shows all.

Visibility changes do not rebuild, refetch, retessellate, or discard the loaded
geometry. Duplicate labels receive occurrence numbers. State resets when the
requested view, occurrence placement, or source revision changes; selecting a
different component or refreshing unchanged metadata preserves visibility.
Isolation also hides components that finish loading afterward.

These controls affect the browser display only. They do not edit CAD source,
STEP exports, catalog status, or assembly placements. An STL artifact contains
one selectable mesh per occurrence; a component-rich STEP display scene exposes
its separate components.

## Measurement and annotation

Exit measurement or annotation before changing visibility. Dimensions and
framing use the visible component bounds. Exact topology remains STEP-backed.
For a partially hidden STEP view, restore its parts with **Show all** before
using exact snapping: the current topology API addresses the whole STEP artifact
and cannot safely exclude hidden component targets. The UI explains this instead
of snapping to invisible geometry. Mesh picking excludes hidden occurrences.

Live screen captures retain the camera/annotation path and include component
visibility in metadata. An occurrence is reported visible only while at least
one of its components is visible.

## Verification

Normal validation:

```sh
npm --prefix viewer/stl-viewer test
npm --prefix viewer/stl-viewer run typecheck
npm --prefix viewer/stl-viewer run build
```

Optional downstream GLB acceptance, using an existing display artifact:

```sh
FLOW_CAD_INSPECTION_GLB=/absolute/path/to/display.glb \
FLOW_CAD_INSPECTION_COMPONENT_COUNT=499 \
npm --prefix viewer/stl-viewer test -- tests/displayInspection.acceptance.test.tsx
```

The component count is optional. This exercises real R3F scene objects, loading,
isolation, hiding every component, restoration, and geometry/color preservation.
It uses a renderer stub and does **not** replace browser pixel verification.

For delivery, open a fresh browser on the active project's actual runtime URL.
Check click selection, peeling, list recovery, isolate/undo, camera stability,
and all-hidden recovery. Then use the protected project-local agent-screen
workflow and inspect the captured PNG. Do not report live verification complete
from the tests alone.
