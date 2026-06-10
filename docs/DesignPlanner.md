# Design Planner V1

Date: 2026-06-10

## Scope

Design Planner V1 defines how natural-language requests, sketch/annotation input, and
deterministic adapters become visible draft work inside Flow CAD. It is a runtime
contract with a narrow deterministic planner implementation, not a full CAD
execution engine.

This document applies to:

- design-thread chat paths
- deterministic preview-command adapters
- draft transaction and registry-driven planning
- viewer-visible planning evidence in thread history

## End-to-End Flow

The planner treats every user request as:

1. **Intent sources**
   - Chat prompt text
   - Sketch/annotation geometry from active viewport artifacts
   - Selected part context and active draft context
   - Existing validators and available operations
2. **DesignBrief**
   - A normalized record of what the user asked, assumptions, missing constraints,
     and applicable scope.
3. **DesignPlan**
   - A structured list of steps with operation references and plan kind.
4. **Execution**
   - Apply operations through draft transaction paths only.
5. **Preview/validation loop**
   - Preview the draft, surface warnings and failed steps, and keep all writes within
     runtime state until accepted.

Every stage is persisted as structured thread evidence so failures are diagnosable and
retryable.

## Plan Types

### 1) `questions`

Purpose: resolve ambiguity before any mutation.

Behavior:

- Planner emits required clarifying questions when inputs are incomplete or
  conflicting.
- No registry operations are executed in this state.
- The question set is persisted so the user sees exactly what blocked progression.

Example:

> User: `make a robot head`  
> Planner emits `questions` asking for key dimensions, mounting interface, wall
> style, and material assumptions.

This avoids the chat path failing or canceling silently when intent is broad.

### 2) `draft_plan`

Purpose: produce a concrete registry-backed mutation path.

Behavior:

- Planner has enough constrained info to map request intent to registered
  operations.
- Each step references a stable registry operation ID.
- Draft operations are proposed, and then applied in the thread-approved draft flow:
  propose -> apply -> preview -> (optional validate) -> accept/discard.
- The plan can be deterministic when confidence is high; low-confidence plans are
  still visible before mutation.

Example:

```text
1. create_box(part_id=plate_left, length=100, width=100, thickness=10)
2. add_hole(center_x=10, center_y=10, diameter=5, depth=8) x4
3. preview()
```

### 3) `concept_plan`

Purpose: hold exploratory design alternatives without immediate mutation.

Behavior:

- Planner can propose multiple concept options from a partial brief.
- A concept plan may include notes, assumptions, and unresolved tradeoffs.
- Concept plans do not auto-run mutation adapters unless later promoted to a
  `draft_plan` by user confirmation.

Use this type for non-registry concepts, high-level product ideation, or incomplete
briefs that are broader than the current mutation surface.

## Constrained Sketch / Plate Path

Sketches and annotations are first normalized into **intent primitives**. They are
not applied directly to geometry.

Current supported primitives in V1 include:

- closed outline
- hole mark
- wall region
- keepout region
- dimension callout
- symmetry hint
- face/plane hint

The mapping path is:

1. ingest sketch/annotations as intent primitives
2. infer dimensions and position intent within the currently selected face/selection context
3. produce a `draft_plan` with operation IDs (for example
   `create_box`, `add_hole`, `add_raised_wall`, `mirror_features`)
4. run through draft transaction preview/validation.

## Planned Execution Model

Design Planner V1 is registry-first and draft-first:

- Valid operation IDs must exist in `docs/REGISTRY.md`.
- A plan step can include operation arguments and source evidence references.
- Planner execution targets are draft transactions and preview-safe services only.
- Accepted drafts remain review artifacts until source-loop action is explicitly run.

Planned thread-visible lifecycle states:

- `proposed`
- `applied`
- `previewed`
- `validated`
- `accepted`
- `discarded`
- `blocked`

When blocked, the plan should preserve the exact failure reason, failed step, and
the next ask to continue.

## V1 Boundaries

Design Planner V1 is intentionally narrow:

- It does **not** execute arbitrary domain generators yet.
- It does **not** perform exact visual-to-model projection.
- It does **not** claim full autonomy for unconstrained “concept art” prompts.
- It assumes constrained operations from registered registry IDs and deterministic
  draft mutation.

Approximate projection behavior currently used for annotated raised walls remains a
fast visual mapping path and may not match exact topology picks.

Exact annotation-to-face projection is tracked separately in
`docs/REGISTRY_TICKETS.md`.

## Related Docs

- `docs/REGISTRY.md`: registry schema, descriptors, and v1 operation inventory
- `docs/REGISTRY_TICKETS.md`: milestone sequencing (planner queue, adapters,
  and exact projection roadmap)
- `docs/ViewerChatTriage.md`: current chat implementation and remaining runtime
  gaps for design-thread behavior
