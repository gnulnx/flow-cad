"""Explicit disposable SQLite schema for the replacement registry."""

from __future__ import annotations


DATABASE_SCHEMA_VERSION = 2

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE projects (
    project_id TEXT PRIMARY KEY,
    python_package TEXT NOT NULL,
    manifest_schema_version INTEGER NOT NULL,
    manifest_path TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0)
);

CREATE TABLE parts (
    uuid TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    generator TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL,
    material TEXT,
    family TEXT,
    version TEXT,
    compatible_versions_json TEXT NOT NULL DEFAULT '[]',
    shell_count INTEGER CHECK (shell_count IS NULL OR shell_count > 0),
    infill_density REAL CHECK (
        infill_density IS NULL OR (infill_density >= 0.0 AND infill_density <= 1.0)
    ),
    mass_kg REAL CHECK (mass_kg IS NULL OR mass_kg >= 0.0),
    center_of_mass_mm_json TEXT,
    inertia_kg_m2_json TEXT,
    mass_source TEXT,
    metadata_status TEXT,
    metadata_notes TEXT,
    UNIQUE (project_id, key)
);

CREATE TABLE part_aliases (
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    part_uuid TEXT NOT NULL REFERENCES parts(uuid) ON DELETE CASCADE,
    PRIMARY KEY (project_id, alias)
);

CREATE TABLE source_definitions (
    part_uuid TEXT PRIMARY KEY REFERENCES parts(uuid) ON DELETE CASCADE,
    generator TEXT NOT NULL,
    module TEXT NOT NULL,
    symbol TEXT NOT NULL
);

CREATE TABLE assembly_occurrences (
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    assembly_key TEXT NOT NULL,
    occurrence_id TEXT NOT NULL,
    part_uuid TEXT NOT NULL REFERENCES parts(uuid) ON DELETE RESTRICT,
    translation_x_mm REAL NOT NULL,
    translation_y_mm REAL NOT NULL,
    translation_z_mm REAL NOT NULL,
    rotation_x_deg REAL NOT NULL,
    rotation_y_deg REAL NOT NULL,
    rotation_z_deg REAL NOT NULL,
    PRIMARY KEY (project_id, assembly_key, occurrence_id)
);

CREATE TABLE builds (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE build_jobs (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    part_uuid TEXT REFERENCES parts(uuid) ON DELETE SET NULL,
    request_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    phase TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE artifacts (
    part_uuid TEXT NOT NULL REFERENCES parts(uuid) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256 TEXT,
    byte_count INTEGER,
    state TEXT NOT NULL,
    PRIMARY KEY (part_uuid, kind)
);

CREATE TABLE artifact_dependencies (
    part_uuid TEXT NOT NULL REFERENCES parts(uuid) ON DELETE CASCADE,
    artifact_kind TEXT NOT NULL,
    dependency_path TEXT NOT NULL,
    dependency_sha256 TEXT,
    PRIMARY KEY (part_uuid, artifact_kind, dependency_path),
    FOREIGN KEY (part_uuid, artifact_kind)
        REFERENCES artifacts(part_uuid, kind) ON DELETE CASCADE
);

CREATE TABLE validation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    part_uuid TEXT REFERENCES parts(uuid) ON DELETE CASCADE,
    validator_key TEXT NOT NULL,
    status TEXT NOT NULL,
    artifact_revision TEXT,
    created_at TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE TABLE thread_summaries (
    thread_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_id INTEGER
);

CREATE INDEX idx_parts_project_status_key ON parts(project_id, status, key);
CREATE INDEX idx_aliases_part_uuid ON part_aliases(part_uuid);
CREATE INDEX idx_occurrences_part_uuid ON assembly_occurrences(part_uuid);
CREATE INDEX idx_artifacts_state ON artifacts(state);
"""
