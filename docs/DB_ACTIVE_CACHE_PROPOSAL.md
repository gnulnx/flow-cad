B3 Architecture Proposal: The Database as an "Active Cache"

Executive Summary

This proposal resolves the architectural fork regarding the role of the SQLite database in Project B3.

The Conflict:

The original MCP Strategy (MCP.md) proposes using a SQLite database to manage components, mating interfaces, and clearances to prevent agent context window explosion.

Codex's Feedback rightly warns against using a database as the primary source of truth for design parameters, citing issues with Git branching, diff-ability, and the risk of silent design changes.

The Solution:

We propose the Database-as-an-Active-Cache pattern.

Geometry, parameters, and structural rules remain 100% code-first (params.py and src/flow_cad/registry.py).

The SQLite database (b3/registry.db) is treated strictly as a compiled metadata cache generated dynamically by the build pipeline.

The MCP server interacts only with the database cache, delivering lightweight JSON outputs to coding agents without forcing them to parse monolithic python source code or run heavy geometric calculations.

1. The Architectural Flow

   [ Developer or Agent ]
              │
              ▼
    Modifies Python Files ──► `flow cad build` ──► Generates STEP / Computes BBox & Vol
   (src/parts/, params.py)                              │
              ▲                                         ▼
              └────────────────────────────── Writes Snapshot to `b3/registry.db`
                                                        │
                                                        ▼
                                              Exposed via MCP Tools 
                                      (Ultra-lightweight JSON for Agents)


Why this Solves the "Context Ceiling"

An agent performing clearance checks or mounting hole alignments should not have to parse a 2,000-line CAD script or execute unstable localized geometry evaluations.

By having flow cad build populate an SQLite active cache, the MCP server can answer high-level spatial and organizational queries via simple JSON-RPC.

Example: When an agent asks get_component_dimensions("left_side_plate"), the MCP server queries b3/registry.db and returns standard, tiny JSON containing bounding boxes and volume figures, consuming less than 100 tokens instead of parsing hundreds of lines of CAD code.

2. Updated Phase 2 Implementation Tickets

We propose revising Phase 2 of REGISTRY.md to reflect this hybrid architecture.

REG-2.1: Python Source Registry (src/flow_cad/registry.py)

Goal: Establish the code-first, canonical mapping of part definitions.

Requirements:

Create a PartDefinition dataclass in python:

@dataclass
class PartDefinition:
    id: str
    module: str
    filename: str
    factory_func: Callable
    is_printable: bool = True
    material: str = "PETG"
    shell_count: int = 4
    infill_density: float = 0.4


Centralize all project parts in a REGISTRY dictionary inside this file.

Remove legacy manual lists in main.py and export scripts.

Verification:

Ensure python tests can import REGISTRY and verify all factory functions are runnable.

REG-2.2: SQLModel Cache Schema

Goal: Design the SQLite table structures to represent the compiled state of the CAD project.

Requirements:

Define ComponentCache table: id (PK), module, step_path, volume_mm3, bbox_x, bbox_y, bbox_z, compiled_at.

Define BuildMetadata table: build_id (PK), git_commit, parameters_json (a serialized freeze of params.py at compile time), is_clean_build.

Define PrintSpecificationCache table: component_id (FK), material, infill_density, shell_count, measured_mass_g (populated via physical telemetry CLI).

Verification:

Write database initialization logic running under b3/registry.db.

REG-2.3: Integrate Cache Writes into flow cad build

Goal: Make database updates a predictable, automatic post-process of the compilation step.

Requirements:

Modify flow cad build. On successful STEP compilation:

Calculate bounding box dimensions ($X, Y, Z$) and volume ($mm^3$) directly from the build123d shape objects in-memory.

Write these metrics, alongside the file paths and parameter snapshots, into b3/registry.db.

The database file is treated as a build artifact and can be ignored in .gitignore if desired (or committed to track releases).

Verification:

Verify that compiling a part immediately creates or updates its entry in b3/registry.db.

REG-2.4: Integrate CLI Tools with the Active Cache

Goal: Expose quick telemetry and querying to the developer and agent.

Requirements:

flow registry list: Queries the SQLite cache and prints a formatted terminal table showing part names, modules, volumes, and bounding boxes.

flow registry weight <component_id> <grams>: Allows direct telemetry logging of physical parts to compare physical vs. theoretical mass.

Verification:

Verify commands execute smoothly and fetch data directly from the SQLite cache.

3. Benefits of the Hybrid Approach

Evaluation Metric

Pure Code Registry (Codex)

Pure DB Registry (Original)

Active Cache Model (Proposed)

Git Diffs & Branching

Excellent (Plaintext)

Poor (SQLite Binary Conflict)

Excellent (Code is Truth, DB is derived artifact)

Agent Token Efficiency

Poor (Must parse code)

Excellent (Simple DB queries)

Excellent (Agent reads SQLite via MCP)

Sim2Real Traceability

Complex

Excellent

Excellent (Sim reads parameter snapshot from DB)

Execution Stability

Variable (Interpreter-heavy)

High

High (Data is pre-compiled)

Prepared for review by CODEX.
