"""Fast, geometry-free bootstrap for replacement Flow CAD projects."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


PROJECT_MANIFEST = "flowcad.project.yaml"
_PACKAGE_CHARACTER = re.compile(r"[^a-z0-9_]+")


class BootstrapError(RuntimeError):
    """Raised when a project cannot be initialized safely."""


@dataclass(frozen=True, slots=True)
class InitResult:
    root: Path
    project_id: str
    python_package: str
    changed_paths: tuple[Path, ...]
    elapsed_ms: float


def normalize_python_package(value: str) -> str:
    """Return a deterministic importable package name for a repository name."""

    normalized = _PACKAGE_CHARACTER.sub("_", value.strip().lower()).strip("_")
    if not normalized:
        raise BootstrapError("project name must contain a letter or number")
    if normalized[0].isdigit():
        normalized = f"flow_{normalized}"
    return normalized


def init_project(
    project_root: Path,
    *,
    project_id: str | None = None,
    force: bool = False,
) -> InitResult:
    """Create only project-owned replacement files without importing CAD code."""

    started = time.perf_counter()
    root = project_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    resolved_project_id = (project_id or root.name).strip()
    if not resolved_project_id:
        raise BootstrapError("project id may not be empty")
    python_package = normalize_python_package(resolved_project_id)

    files = _project_files(resolved_project_id, python_package)
    changed: list[Path] = []
    for relative_path, content in files.items():
        destination = root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not force:
            continue
        _write_text_atomic(destination, content)
        changed.append(destination)

    for relative_directory in ("tests",):
        directory = root / relative_directory
        if not directory.exists():
            directory.mkdir(parents=True)
            changed.append(directory)

    return InitResult(
        root=root,
        project_id=resolved_project_id,
        python_package=python_package,
        changed_paths=tuple(changed),
        elapsed_ms=(time.perf_counter() - started) * 1000.0,
    )


def _write_text_atomic(path: Path, content: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _project_files(project_id: str, python_package: str) -> dict[Path, str]:
    return {
        Path("AGENTS.md"): _agents_template(project_id, python_package),
        Path(PROJECT_MANIFEST): _manifest_template(project_id, python_package),
        Path(python_package, "__init__.py"): _package_init_template(project_id),
        Path(python_package, "params.py"): _params_template(project_id),
        Path(python_package, "parts", "__init__.py"): '"""Project-owned CAD generators."""\n',
        Path(python_package, "validators", "__init__.py"): '"""Project-specific validators."""\n',
        Path("docs", "PART_INTERFACES.md"): "# Part Interfaces\n\nRecord fixed mating and hardware interfaces here.\n",
        Path("docs", "PRINT_MANIFEST.md"): "# Print Manifest\n\nRecord project-owned manufacturing intent here.\n",
        Path(".flow", ".gitignore"): "*\n!.gitignore\n",
    }


def _manifest_template(project_id: str, python_package: str) -> str:
    return (
        "schema_version: 1\n"
        f"project_id: {json.dumps(project_id)}\n"
        f"python_package: {json.dumps(python_package)}\n"
        f"parameter_provider: {python_package}.params:ProjectParams\n"
        "parts: []\n"
        "assemblies:\n"
        "  active:\n"
        "    occurrences: []\n"
    )


def _package_init_template(project_id: str) -> str:
    return f'"""Geometry source for {project_id}."""\n'


def _params_template(project_id: str) -> str:
    return (
        '"""Versioned project parameters; no Flow CAD runtime plumbing belongs here."""\n\n'
        "from dataclasses import dataclass\n\n\n"
        "@dataclass(frozen=True, slots=True)\n"
        "class ProjectParams:\n"
        f"    project_id: str = {project_id!r}\n"
    )


def _agents_template(project_id: str, python_package: str) -> str:
    return f"""# Agent Operating Guide

This repository owns the product-specific CAD project `{project_id}`. Flow CAD
owns the reusable runtime and public SDK.

## Ownership

- Geometry, dimensions, assembly occurrences, hardware interfaces, measured
  metadata, project validators, print intent, and generated exports belong here.
- Reusable CLI, manifest, registry, database, build, artifact, viewer, export,
  measurement, annotation, chat, job, and generic validation behavior belongs
  in Flow CAD.
- Project Python may import `flow_cad.sdk` and only explicitly approved stable
  geometry helpers. It may not import Flow CAD internals.
- Never define or copy `PartDefinition`, `PartRole`, registry/cache models,
  build orchestration, viewer APIs, export services, generic validators, or
  runtime CLI code in this repository.

## Source Of Truth

- Manifest: `flowcad.project.yaml`
- Parameters: `{python_package}/params.py`
- Parts: `{python_package}/parts/`
- Project validators: `{python_package}/validators/`
- Interface contracts: `docs/PART_INTERFACES.md`
- Print intent: `docs/PRINT_MANIFEST.md`
- Generated local state: `.flow/`

## Workflow

Run `flow sync` after changing manifest metadata. Use `flow part list` to inspect
the generated metadata index. Use focused part builds before the release gate.
Reusable behavior must be implemented and committed in Flow CAD, installed
editable here, and then verified in this project.

Original migration archives and checksum manifests are immutable. Every task
must report changed artifacts and hashes, commit all completed work, and end
with an empty `git status --short`.
"""
