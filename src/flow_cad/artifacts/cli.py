"""CLI for explicit, byte-exact preservation scopes."""

from __future__ import annotations

import csv
import json
import os
import subprocess
import tempfile
from pathlib import Path

import rich_click as click

from .preservation import (
    PreservationError,
    build_inventory,
    copy_archive,
    verify_archive,
    write_manifest_atomic,
)


def _scope_options(command):
    command = click.option(
        "--path",
        "explicit_paths",
        multiple=True,
        type=click.Path(path_type=Path),
        help="Include one project-relative file (repeatable).",
    )(command)
    command = click.option(
        "--tree",
        "trees",
        multiple=True,
        type=click.Path(path_type=Path),
        help="Include every regular file below a relative directory (repeatable).",
    )(command)
    return click.option(
        "--tracked",
        "tracked_scopes",
        multiple=True,
        type=click.Path(path_type=Path),
        help="Include Git-tracked files at or below a relative path (repeatable).",
    )(command)


@click.group("preserve")
def preserve() -> None:
    """Create and verify byte-identical migration archives."""


@preserve.command("manifest")
@click.option("--source", required=True, type=click.Path(path_type=Path, file_okay=False))
@click.option("--output", required=True, type=click.Path(path_type=Path, dir_okay=False))
@_scope_options
def manifest_command(
    source: Path,
    output: Path,
    explicit_paths: tuple[Path, ...],
    trees: tuple[Path, ...],
    tracked_scopes: tuple[Path, ...],
) -> None:
    """Write a sorted SHA-256 manifest for an explicit source scope."""

    try:
        paths = collect_scope(source, explicit_paths, trees, tracked_scopes)
        click.echo(f"phase=running operation=manifest files={len(paths)}")
        inventory = build_inventory(source, paths)
        write_manifest_atomic(output, inventory)
    except (OSError, PreservationError, subprocess.CalledProcessError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(_summary(inventory, output=str(output.resolve())), sort_keys=True))


@preserve.command("copy")
@click.option("--source", required=True, type=click.Path(path_type=Path, file_okay=False))
@click.option("--archive", required=True, type=click.Path(path_type=Path, file_okay=False))
@_scope_options
def copy_command(
    source: Path,
    archive: Path,
    explicit_paths: tuple[Path, ...],
    trees: tuple[Path, ...],
    tracked_scopes: tuple[Path, ...],
) -> None:
    """Copy an explicit source scope without overwriting archive files."""

    try:
        paths = collect_scope(source, explicit_paths, trees, tracked_scopes)
        click.echo(f"phase=running operation=copy files={len(paths)}")
        inventory = copy_archive(source, archive, paths)
    except (OSError, PreservationError, subprocess.CalledProcessError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(_summary(inventory, archive=str(archive.resolve())), sort_keys=True))


@preserve.command("verify")
@click.option("--source", required=True, type=click.Path(path_type=Path, file_okay=False))
@click.option("--archive", required=True, type=click.Path(path_type=Path, file_okay=False))
@_scope_options
def verify_command(
    source: Path,
    archive: Path,
    explicit_paths: tuple[Path, ...],
    trees: tuple[Path, ...],
    tracked_scopes: tuple[Path, ...],
) -> None:
    """Verify source/archive pairs using both SHA-256 and `cmp -s`."""

    try:
        paths = collect_scope(source, explicit_paths, trees, tracked_scopes)
        click.echo(f"phase=running operation=verify files={len(paths)}")
        inventory = verify_archive(source, archive, paths)
    except (OSError, PreservationError, subprocess.CalledProcessError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps(_summary(inventory, verified=True), sort_keys=True))


@preserve.command("migration-map")
@click.option("--source", required=True, type=click.Path(path_type=Path, file_okay=False))
@click.option("--output", required=True, type=click.Path(path_type=Path, dir_okay=False))
@click.option("--status", default="preserved-only", show_default=True)
@_scope_options
def migration_map_command(
    source: Path,
    output: Path,
    status: str,
    explicit_paths: tuple[Path, ...],
    trees: tuple[Path, ...],
    tracked_scopes: tuple[Path, ...],
) -> None:
    """Initialize a migration map from a verified source inventory."""

    try:
        paths = collect_scope(source, explicit_paths, trees, tracked_scopes)
        inventory = build_inventory(source, paths)
        _write_migration_map(output, inventory.entries, status=status)
    except (OSError, PreservationError, subprocess.CalledProcessError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(json.dumps({"file_count": inventory.file_count, "output": str(output.resolve())}, sort_keys=True))


def collect_scope(
    source: Path,
    explicit_paths: tuple[Path, ...] = (),
    trees: tuple[Path, ...] = (),
    tracked_scopes: tuple[Path, ...] = (),
) -> tuple[Path, ...]:
    root = source.resolve()
    collected = set(explicit_paths)
    for tree in trees:
        _require_relative_scope(tree)
        tree_root = root / tree
        if not tree_root.is_dir():
            raise PreservationError(f"preservation tree is not a directory: {tree}")
        for candidate in tree_root.rglob("*"):
            if candidate.is_symlink():
                raise PreservationError(f"preservation tree contains a symlink: {candidate}")
            if candidate.is_file():
                collected.add(candidate.relative_to(root))
    for tracked_scope in tracked_scopes:
        _require_relative_scope(tracked_scope)
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--", tracked_scope.as_posix()],
            check=True,
            capture_output=True,
        )
        for raw_path in result.stdout.split(b"\0"):
            if raw_path:
                collected.add(Path(os.fsdecode(raw_path)))
    if not collected:
        raise PreservationError("preservation scope is empty")
    return tuple(sorted(collected, key=lambda path: path.as_posix()))


def _require_relative_scope(scope: Path) -> None:
    if scope.is_absolute() or ".." in scope.parts or scope == Path("."):
        raise PreservationError(f"preservation scope must be a safe relative path: {scope}")


def _write_migration_map(output: Path, entries, *, status: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise PreservationError(f"migration map already exists: {output}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent, text=True
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(
                (
                    "original_path",
                    "original_sha256",
                    "active_destination_path",
                    "active_sha256",
                    "status",
                    "reason",
                    "validating_tests",
                )
            )
            for entry in entries:
                writer.writerow((entry.path, entry.sha256, "", "", status, "", ""))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, output)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _summary(inventory, **extra: object) -> dict[str, object]:
    return {
        "file_count": inventory.file_count,
        "byte_count": inventory.byte_count,
        **extra,
    }
