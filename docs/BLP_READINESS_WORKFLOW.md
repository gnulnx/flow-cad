# BLP Readiness Workflow

This is the working path for making Flow CAD useful to Base Layer Printing without turning the Flow CAD viewer into the BLP website. Expect this document to change as pricing, materials, and production rules mature.

## Goal

Provide a trustworthy CAD/STL analysis layer that a customer-facing BLP site can depend on for quoting, intake, and portfolio rendering.

## Workflow

1. **Geometry Intake**
   - Accept STL first for browser-only V1.
   - Treat STEP as a later server-side flow through Flow CAD conversion/parsing.
   - Preserve original uploaded geometry for physical metrics before any viewer centering or scaling.

2. **Mesh Metrics Contract**
   - Compute triangle count, physical bounds in mm, mesh volume in mm3/cm3, surface area in mm2/cm2, and basic quality warnings.
   - Keep this logic in a reusable TypeScript helper under `viewer/stl-viewer/src/` so another app can copy or package it.
   - Treat volume as reliable only when the mesh is closed enough for signed tetrahedron volume to be meaningful.

3. **Standalone Viewer Health**
   - `viewer/index.html` remains a zero-install sanity viewer.
   - It must report physical dimensions from original geometry, not the scaled render geometry.
   - It is allowed to keep its own inline browser code, but behavior should track the reusable helper contract.

4. **Estimator V1**
   - Use mesh volume, material density, selected material, infill assumption, setup fee, and a simple machine-time heuristic.
   - Show the result as an estimate, not a guaranteed quote.
   - Surface warnings for non-watertight meshes, huge dimensions, tiny dimensions, and unsupported formats.

5. **BLP Website Integration**
   - Build the customer-facing UI outside this repo.
   - Import or copy the tested mesh metrics helper into the BLP app until Flow CAD has a formal shared package boundary.
   - Keep order intake, contact data, Stripe, and customer files out of Flow CAD.

6. **Later Flow CAD Integration**
   - Add backend STEP analysis for B2B files.
   - Add server-side validation for uploaded files before checkout.
   - Add portfolio render exports from Flow CAD/B3 projects as static assets for the BLP site.

## Current Gates

- `npm --prefix viewer/stl-viewer test`
- `npm --prefix viewer/stl-viewer run build`
- `python -m pytest`
- Manual smoke check of `viewer/index.html` after a standalone viewer change.

## Open Decisions

- Material density and price table.
- Minimum setup fee and minimum order price.
- Machine-time heuristic.
- How conservative to be with open or non-manifold customer meshes.
- Whether the first BLP site imports Flow CAD source directly or vendors a copied helper.
