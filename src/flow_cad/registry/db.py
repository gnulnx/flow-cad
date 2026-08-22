"""SQLite connection helpers that keep queries read-only."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .schema import DATABASE_SCHEMA_VERSION, SCHEMA_SQL


DATABASE_NAME = "flowcad.db"


class RegistryError(RuntimeError):
    """Base registry error."""


def database_path(project_root: Path) -> Path:
    return project_root.resolve() / ".flow" / DATABASE_NAME


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise RegistryError(f"registry index not found: {path}; run `flow sync`")
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def connect_writable(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    connection.execute(
        "INSERT INTO schema_meta(key, value) VALUES (?, ?)",
        ("database_schema_version", str(DATABASE_SCHEMA_VERSION)),
    )
    connection.execute(f"PRAGMA user_version = {DATABASE_SCHEMA_VERSION}")
