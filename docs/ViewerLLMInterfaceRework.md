# Viewer LLM Interface Rework

## Background

The current viewer command pane is built around:

* Select part
* View part context
* Enter command
* Generate proposal
* Preview
* Accept

This works for explicit operations but does not match how real design review happens.

In practice, users spend most of their time:

* Reviewing assemblies, not individual parts
* Looking for issues visually
* Discussing design tradeoffs
* Referring to objects visible in the current viewport
* Iterating through multiple proposals before accepting a change

The current interface behaves like a CAD command console. We want to evolve it into a design conversation workspace.

---

## Goal 1: Persistent Design Threads

Replace the single command workflow with persistent project threads.

A thread should become a durable design artifact.

Examples:

* Battery Tray Revision
* VESC Cooling
* IMU Mount Isolation
* B3 Side Panel Review

Threads should preserve:

* Conversation history
* Generated proposals
* Accepted/rejected operations
* Measurements
* Validation results
* Accepted source artifacts

The goal is to make design intent discoverable long after a change was made.

---

## Goal 2: Viewport-Aware Conversation Context

The assistant should understand more than the selected part.

Conversation context should include:

* Current project
* Current assembly
* Current camera pose
* Visible parts
* Selected parts
* Active measurements
* Active draft transactions

Users should be able to say:

> These holes do not align.

without manually describing every visible object.

The viewer already knows much of this context and should provide it automatically.

The selected part remains useful, but it should not be the primary source of context.

---

## Goal 3: Screenshot And Annotation Workflow

Add the ability to capture the current viewport and attach it to a design thread.

Future annotation support should allow:

* Arrows
* Circles
* Notes
* Highlighted regions

The goal is to allow visual communication of design intent without requiring detailed text descriptions.

Example workflow:

* Capture viewport
* Circle mounting holes
* Add note
* Ask assistant to correct alignment

The assistant should receive both the image and associated viewport context.

---

## Goal 4: Conversation First, Commands Second

The primary workflow should become:

* Discuss
* Review
* Annotate
* Propose
* Preview
* Accept

The current command box may still exist, but it should become a secondary tool rather than the primary interaction model.

The center of the experience should be the design conversation.

Context, measurements, selected parts, draft state, and operations should support the conversation rather than replace it.

---

## Existing LlamaStudio Evaluation

Before building a new conversation system from scratch, review whether portions of LlamaStudio can be reused or embedded.

Repository location:

```text
/home/gnulnx/LlamaStudio
```

Current assumptions:

* FlowCad remains the owner of the CAD viewer, viewport, measurements, draft transactions, validation workflow, and project-specific context.
* LlamaStudio is not expected to become the primary FlowCad UI.
* LlamaStudio may contain reusable infrastructure that reduces implementation effort.

Areas worth evaluating:

* Conversation/thread persistence
* Chat UI patterns
* Streaming response infrastructure
* Local model management
* Agent/tool execution loops
* Conversation history storage
* Multi-model support and model profiles
* Embedded chat-panel architecture

Questions to answer:

1. Should FlowCad build its own conversation system from scratch?
2. Should portions of LlamaStudio be extracted into a reusable library?
3. Should LlamaStudio support an embedded mode while continuing to operate as a standalone application?
4. What pieces are genuinely reusable versus FlowCad-specific?
5. What architecture would allow future FlowCad, Dojo, and other BLR applications to share a common local-agent runtime?

The goal is not to force LlamaStudio into FlowCad.

The goal is to determine whether a shared local-agent platform would accelerate development while avoiding duplicated infrastructure.

---

## Requested Output

Review the existing viewer architecture and propose:

1. A phased implementation plan.
2. Required backend changes.
3. Required frontend changes.
4. Thread persistence architecture.
5. Screenshot and annotation architecture.
6. How draft operations integrate into conversation history.
7. How this work relates to the existing Viewer Preview roadmap.
8. Whether this work should be split into multiple roadmap items.
9. Whether LlamaStudio provides reusable infrastructure that should be incorporated.

Focus on architecture and implementation breakdown rather than final UI polish.

