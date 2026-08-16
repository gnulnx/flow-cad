---
name: "draft-mode"
description: "Rapid visual CAD iteration for Flow CAD and build123d projects. Use when the user says draft mode, quick draft, rough part, preview, get it on screen, show me a part, visual review, or when a CAD request clearly prioritizes immediate on-screen feedback over formal validation, handoff packaging, reports, or production-ready exports."
---

# Draft Mode

## Priority

Optimize for the shortest path from request to visible geometry. A draft is allowed to be temporary, incomplete, unvalidated, or isolated from project source as long as it is clearly labeled and visible for user review.

For first review, prefer this order:

1. Create or modify the smallest viable geometry.
2. Get it into the active viewer or CAD Explorer.
3. Tell the user the review URL or exact artifact path.
4. Run only the minimum check needed to avoid showing the wrong part or stale state.
5. Defer full validation, reports, handoff bundles, print manifests, and cleanup until the user accepts the direction or asks for productionization.

## Trigger Handling

When the user explicitly says draft mode, stay in draft mode for that turn unless they ask for final/production/gate/handoff quality. When the user asks for a simple visual part, infer draft mode even if they do not name it.

Do not spend the first iteration on:

- exhaustive skill/reference loading beyond the directly relevant CAD/viewer instructions
- registry cache debugging
- full project validators
- report generation
- broad build profiles
- CAD Explorer dependency repair
- unrelated source refactors
- formal manufacturing claims

## Flow CAD Fast Path

In a Flow CAD project, prefer the fastest available preview path:

```bash
flow cad build --part <part_id> --assembly-preview --no-reports
flow reload
```

If `--assembly-preview` is inappropriate or unavailable, use:

```bash
flow cad build --part <part_id> --no-reports
flow reload
```

If the workbench is not running, start it and return the local URL:

```bash
flow start
```

Use `flow registry`, full validator runs, STEP facts, and report inspection only after the part is visible or when a cheap check is needed to prevent stale/wrong geometry.

## Draft Geometry API Fast Path

When the project exposes Flow CAD draft endpoints or MCP draft tools, prefer isolated draft state over source edits for disposable previews. Keep draft artifacts under `.flow/drafts` or the tool-provided draft token. Do not let draft previews enter release exports, print manifests, or handoff bundles unless the user asks to accept/promote them.

For primitive requests such as a box, sphere, cylinder, hole, slot, or counterbore, use the draft API/tooling if it can render faster than source edits and project rebuilds.

## Source Edit Fast Path

If source edits are the fastest route:

- add the smallest part function or parameter change
- register only the needed part if the project requires registry discovery
- build only that part
- refresh the viewer immediately
- avoid broad formatting or cleanup

For simple dimensional primitives, write direct, readable parameters such as `SPHERE_DIAMETER_MM = 10.0`.

## Minimum Checks

Before claiming the user can review, confirm at least one of:

- the viewer/workbench reload succeeded
- the expected STEP/STL/artifact path exists and has a fresh timestamp
- the live `/api/parts` or viewer payload includes the expected part id
- a direct preview URL was returned by CAD Explorer or the workbench

State draft status plainly: "Visible draft; not production validated."

## Removing Draft Previews

When asked to remove a draft from the viewer, distinguish the three draft surfaces:

- Project parts from `/api/parts`, such as a registered `draft_sphere`.
- Active draft transaction files and endpoints under `/api/draft-transactions/<token>`.
- Frontend-only preview meshes loaded from design-thread `content.preview_model` records.

Do not assume a server-side discard removes what is already on screen. The React workbench stores draft preview meshes in client state as `previewModels`; those clear through the frontend discard/accept flow, a revision-observed app reload, selecting a different part, or a full browser refresh. Design-thread messages can also re-activate previews because the app scans active thread messages for `content.preview_model`.

For cleanup, prefer this sequence:

1. Identify whether the visible object is a registered part id or a `draft:<transaction-token>` preview.
2. If it is a transaction preview, call the discard endpoint and verify the model endpoint returns inactive or 404.
3. Clear the browser-side preview state by using the workbench discard action, forcing a real page reload, or switching active selection so `clearDraftState()` runs.
4. If the preview reappears after reload, inspect the active design-thread messages for `preview_model`; archive/switch the thread or record a discard event instead of only deleting `.flow` files.
5. Verify visually or through the frontend model list, not only through `/api/parts`.

If direct GUI control is not available, report that backend state is clean but the open browser tab may still hold an already-loaded preview mesh.

## Escalation To Production

Switch out of draft mode only when the user approves the shape or requests production readiness. Then run the normal CAD workflow: source cleanup, STEP-first generation, facts/measurements, validators, reports, manifests, handoff packaging, and CAD Explorer review as appropriate.
