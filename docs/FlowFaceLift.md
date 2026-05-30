# Flow CAD 3D Viewer FaceLift Proposal
*Prepared by: Gemini (Lead UX Engineer)*

The Flow CAD 3D Viewer is a powerful validation tool for high-precision parametric designs. However, the current visual styling and layout suffer from a clunky, dated dark-blue/neon-pink palette, overlapping panels that crowd out the 3D model, and a lack of fluid transitions. 

This document proposes **FlowFaceLift**, a comprehensive visual and interactive overhaul to make the viewer feel like a premium, state-of-the-art engineering workspace (comparable to modern CAD slicers like Bambu Studio or interactive web tooling like Spline and Figma).

---

## 🎨 1. Design System & Styling Tokens

We will replace the harsh high-contrast gaming aesthetic with a mature, high-precision CAD aesthetic.

### Modern Color Palette

```
┌─────────────────────────────────────────────────────────────┐
│  Dark Slate Background (Neutral Dark)     │  #090d16        │
├───────────────────────────────────────────┼─────────────────┤
│  Glassmorphic Panel Fill (Semi-Trans)     │  rgba(15,22,38,0.7)
├───────────────────────────────────────────┼─────────────────┤
│  High-Precision Primary (Electric Cyan)   │  #06b6d4        │
├───────────────────────────────────────────┼─────────────────┤
│  Secondary Action/Focus (Indigo-Violet)   │  #6366f1        │
├───────────────────────────────────────────┼─────────────────┤
│  Interactive Success (Emerald Green)     │  #10b981        │
├───────────────────────────────────────────┼─────────────────┤
│  Critical Warning/Alert (Amber Gold)      │  #f59e0b        │
└───────────────────────────────────────────┴─────────────────┘
```

- **Canvas Background**: Sleek dark space (`#090d16`) with radial gradient.
- **Glass Panels**: `backdrop-filter: blur(16px)` with thin borders (`rgba(255,255,255,0.06)`).
- **Accents**: Electric Cyan (`#06b6d4`) for precise CAD selections and Snaps; Indigo (`#6366f1`) for toolbar interactions; Gold (`#f59e0b`) for active warnings.

### Typography
- **UI Copy & Labels**: **Inter** or **Outfit** via Google Fonts. High legibility, neutral, clean geometric shapes.
- **Coordinates & Numeric Metrics**: **Fira Code** or **JetBrains Mono**. Monospace makes numbers perfectly legible and prevents column shifting.

---

## 📐 2. Layout Overhaul: The "Fluid Workspace"

### The Problem: Floating Overlaps
Currently, `SourcePanel` (left) and `ModelList` (right) float absolutely over the canvas. When open, they block the left and right thirds of the 3D view. On a 1080p screen, this leaves a narrow slot in the middle for the model. Collapsing them leaves awkward floaters on the screen.

### The Solution: The Integrated Docking Sidebar
We will refactor `App.tsx` and `index.css` to use a flex-docked workspace layout:

```
┌─────────────────────────────────────────────────────────────┐
│                    Sleek Glass Toolbar                      │
├───────────────┬─────────────────────────────┬───────────────┤
│               │                             │               │
│               │                             │               │
│  Collapsible  │        WebGL Canvas         │  Collapsible  │
│  Source Dock  │   (Centering recalculates   │  Parts Dock   │
│  (Left panel) │    on sidebar transitions)  │ (Right panel) │
│               │                             │               │
│               │                             │               │
├───────────────┴─────────────────────────────┴───────────────┤
│                    Status & Metrics Bar                     │
└─────────────────────────────────────────────────────────────┘
```

- **True Split View**: Expanding sidebars will resize the 3D viewport. The Three.js canvas auto-resizes seamlessly, and the camera auto-frames the model center relative to the remaining space.
- **Spring Animations**: Collapsing and expanding sidebars will slide smoothly using CSS transitions (`cubic-bezier(0.16, 1, 0.3, 1)`) with no layout jumps.
- **Minified Sidebars**: When collapsed, the sidebars shrink into beautiful vertical utility strips with iconic representations (e.g., a simple code symbol `</>` for Source, list symbol `☰` for Parts), saving every pixel of viewport.

---

## ⚡ 3. High-Precision Micro-Interactions

### A. Snap Visualizer Feedback
When the cursor nears an edge, center, or vertex, snapping should feel satisfying and instant:
- **Snap Ring**: An animated ring (`#06b6d4`) pulsing outward from the cursor focus point.
- **Glow Highlight**: A subtle emissive color boost on the edge segments or vertices that are active.
- **Cursor State Change**: The default cursor crosshair swaps to a high-precision targeting reticle.

### B. High-Fidelity Measurement Cards
Instead of black rectangular text boxes, measurement annotations will render as beautiful HUD cards:
- **Styling**: `rgba(13, 20, 35, 0.85)` background, glass blur, color-coded border depending on authority (Exact snap vs Mesh-only).
- **Layout**: Clean grid formatting of delta coordinates ($dx$, $dy$, $dz$) with color-coded labels (red for $X$, green for $Y$, blue for $Z$).
- **Micro-Actions**: Hovering over a card shows a subtle delete `x` with scale transitions.

### C. Immersive Full-Screen Drag-and-Drop
When dragging an STL onto the page:
- A glassmorphic overlay slides into view over the whole viewport: `rgba(9, 13, 22, 0.7)` with `backdrop-filter: blur(8px)`.
- A dashed container glows with the accent color, accompanied by a clean SVG bounce animation of a 3D model dropping into a box.
- Seamlessly fades out when dragging leaves or drops.

---

## 🏗️ 4. Step-by-Step FaceLift Roadmap

To ensure zero regressions in Python backend code and vitest logic, we will execute the facelift in modular, incremental steps.

### Phase 1: Global Style Foundations (The Skin)
- [ ] Install modern fonts (Inter & Fira Code) via web import.
- [ ] Overhaul `index.css` variables with the obsidian/cyan palette.
- [ ] Refactor button, inputs, select, and status elements for a consistent glassmorphic UI.
- [ ] Redesign custom measurement annotation HTML styles.

### Phase 2: Docked Workspace Refactor (The Bones)
- [ ] Modify `App.tsx` layout structure to support flex docked sidebars instead of absolute layers.
- [ ] Wrap `Viewer.tsx` inside a container that automatically adjusts Three.js aspect ratio when sidebars animate.
- [ ] Add smooth CSS transition transitions for sidebar slide states.
- [ ] Implement mini iconic utility strips for collapsed states.

### Phase 3: The "Flow" Transitions & Micro-interactions (The Muscle)
- [ ] Re-engineer the Drag-and-Drop UI with a beautiful, full-screen blur transition.
- [ ] Overhaul the snaps and highlights in `Viewer.tsx` to add electric cyan ring pulses.
- [ ] Design a beautiful "Empty State" component for when no part is active.
- [ ] Add the missing Drag-and-Drop event handlers inside the legacy `viewer/index.html` file to align it with project claims.

### Phase 4: Validation & Quality Control
- [ ] Ensure all 28 Vitest tests in the viewer workspace pass without any issues.
- [ ] Verify responsive behavior on mobile/tablet viewports.
- [ ] Run the backend test suite (`python -m pytest`) to ensure absolute system stability.

---

## 🙋 5. Open Questions for Feedback

Before coding, let's align on a few design options to make sure we nail the perfect flow:

> [!IMPORTANT]
> **Q1: Sidebar Flex-Resize vs. Overlap Overlay**
> Resizing the 3D canvas on sidebar expansion is extremely precise, but it can trigger minor rendering overhead on low-end machines. Alternatively, we can let sidebars slide out as floating panels but add a visual drop-shadow/blur underneath so they look separate, or support both (resizable panels). Which behavior do you prefer?
> 
> **Q2: Brand Identity/Logo Accent**
> The current system has no official logo. Do you want a subtle animated SVG logo for **Flow CAD** in the top-left (e.g. dynamic waves or geometric vertices that flow)?
> 
> **Q3: Keyboard Shortcuts HUD Overlay**
> We have keyboard shortcuts like `R` to reset, `?` to toggle controls, and `M` for measurement mode. Would you like a dedicated keyboard shortcut helper/hint drawer that opens as an elegant tray from the bottom?

---

Let's make **Flow CAD** look and feel like the modern CAD engine it is! Please review this plan, answer any of the questions, and we will begin crafting the ultimate workspace facelift!
