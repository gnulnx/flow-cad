from __future__ import annotations

import json
from pathlib import Path

import rich_click as click

from flow_cad.project import ProjectError, load_project
from flow_cad.validation.runner import FocusedValidatorRunner, ValidationRunnerError, concise_report_lines


@click.group()
def validate() -> None:
    """Run focused Flow CAD validators."""


@validate.command("list")
@click.option("--family", default=None, help="Only show validators for this family.")
@click.option("--tag", default=None, help="Only show validators with this tag.")
@click.option("--json", "json_output", is_flag=True, default=False, help="Print validator metadata as JSON.")
def list_validators(family: str | None, tag: str | None, json_output: bool) -> None:
    """List focused validators for the active project."""
    project = _load_active_project()
    runner = FocusedValidatorRunner(project)
    try:
        validators = runner.list_validators(family=family, tag=tag)
    except ValidationRunnerError as exc:
        raise click.ClickException(str(exc)) from exc
    if json_output:
        click.echo(json.dumps({"validators": validators}, indent=2, sort_keys=True))
        return
    for validator in validators:
        tags = ",".join(validator["tags"]) if validator["tags"] else "-"
        click.echo(
            f"{validator['id']}  family={validator['family']}  mode={validator['mode']}  "
            f"budget={float(validator['budget_ms']):.0f}ms  source={validator['source']}  tags={tags}"
        )


@validate.command("run")
@click.argument("validator_id", required=False)
@click.option("--part", "part_id", default=None, help="Part id to validate.")
@click.option("--family", default=None, help="Filter selected validators by family.")
@click.option("--tag", default=None, help="Filter selected validators by tag.")
@click.option("--draft-token", default=None, help="Draft token to validate.")
@click.option("--draft-transaction", default=None, help="Draft transaction token to validate.")
@click.option("--changed", is_flag=True, default=False, help="Reserve selection for changed-part validators when available.")
@click.option("--json", "json_output", is_flag=True, default=False, help="Print full structured reports as JSON.")
@click.option("--profile/--no-profile", default=True, help="Write a standalone validator profile.")
@click.pass_context
def run_validator(
    ctx: click.Context,
    validator_id: str | None,
    part_id: str | None,
    family: str | None,
    tag: str | None,
    draft_token: str | None,
    draft_transaction: str | None,
    changed: bool,
    json_output: bool,
    profile: bool,
) -> None:
    """Run one or more focused validators outside the handoff gate."""
    if not validator_id and not family and not tag:
        raise click.ClickException("Pass a validator id, --family, or --tag.")
    project = _load_active_project()
    runner = FocusedValidatorRunner(project)
    command = _context_command(ctx)
    try:
        reports, profile_payload = runner.run(
            validator_id,
            part_id=part_id,
            family=family,
            tag=tag,
            draft_token=draft_token,
            draft_transaction=draft_transaction,
            changed=changed,
            command=command,
            profile=profile,
        )
    except ValidationRunnerError as exc:
        raise click.ClickException(str(exc)) from exc

    if json_output:
        click.echo(
            json.dumps(
                {
                    "ok": all(report.ok for report in reports),
                    "reports": [report.to_dict() for report in reports],
                    "profile": profile_payload,
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for line in concise_report_lines(reports):
            click.echo(line)
        if profile_payload is not None:
            click.echo(click.style(f"Wrote validator profile to {profile_payload['latest_path']}", fg="blue"))

    if any(not report.ok for report in reports):
        if json_output:
            ctx.exit(1)
        raise click.ClickException("Focused validation failed.")


def _load_active_project():
    try:
        return load_project(Path.cwd(), fallback_to_bundled=False)
    except ProjectError as exc:
        raise click.ClickException(f"{exc}. Run `flow init` in this project first.") from exc


def _context_command(ctx: click.Context) -> str:
    names: list[str] = []
    current: click.Context | None = ctx
    while current is not None:
        if current.info_name:
            names.append(current.info_name)
        current = current.parent
    return " ".join(reversed(names))
