"""Command-line boundary enforcement for downstream projects."""

from __future__ import annotations

import json
from pathlib import Path

import rich_click as click

from .ownership import OwnershipScanConfig, scan_ownership


@click.group("ownership")
def ownership() -> None:
    """Enforce the Flow CAD/downstream project boundary."""


@ownership.command("check")
@click.option(
    "--project-root",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path.cwd,
    show_default="current directory",
)
@click.option("--allow-helper", multiple=True, help="Allow one additional Flow CAD import prefix.")
@click.option(
    "--exclude",
    multiple=True,
    type=click.Path(path_type=Path),
    help="Explicit project-relative path to omit from scanning.",
)
@click.option("--json-output", "as_json", is_flag=True, default=False)
def check_ownership(
    project_root: Path,
    allow_helper: tuple[str, ...],
    exclude: tuple[Path, ...],
    as_json: bool,
) -> None:
    """Fail when project Python copies or imports reusable runtime behavior."""

    runtime_root = Path(__file__).resolve().parents[1]
    runtime_files = tuple(sorted(runtime_root.rglob("*.py")))
    result = scan_ownership(
        OwnershipScanConfig(
            downstream_root=project_root,
            allowed_helper_imports=allow_helper,
            excluded_paths=exclude,
            runtime_python_files=runtime_files,
        )
    )
    if as_json:
        click.echo(json.dumps(result.to_dict(), sort_keys=True))
    else:
        click.echo(
            f"ownership files={result.file_count} issues={result.issue_count} "
            f"status={'ok' if result.ok else 'failed'}"
        )
        for issue in result.issues:
            location = f"{issue.path}:{issue.line}" if issue.line is not None else issue.path
            click.echo(f"{location}: {issue.code.value}: {issue.message}")
    if not result.ok:
        raise click.ClickException(f"ownership boundary failed with {result.issue_count} issue(s)")
