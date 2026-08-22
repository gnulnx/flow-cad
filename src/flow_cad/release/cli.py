"""Public CLI for durable production release gates."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import rich_click as click

from flow_cad.jobs import JobService, JobState
from flow_cad.registry import find_manifest

from .service import ReleaseGateService


@click.group("release")
def release() -> None:
    """Run strict-manifest production release checks."""


@release.command("gate")
@click.option("--request-id", default=None, help="Idempotency key for this release gate.")
@click.option(
    "--json-output",
    "as_json",
    is_flag=True,
    default=False,
    help="Emit only the terminal job record as JSON.",
)
def release_gate(request_id: str | None, as_json: bool) -> None:
    """Build and verify every production artifact as a cancellable job."""

    jobs: JobService | None = None
    submission = None
    try:
        project_root = find_manifest(Path.cwd()).parent
        resolved_request_id = request_id or f"cli-release-gate-{uuid.uuid4().hex}"
        jobs = JobService(
            project_root,
            max_concurrency=1,
            recover_interrupted=False,
        )
        submission = ReleaseGateService(project_root, jobs).submit(
            request_id=resolved_request_id
        )
        if not as_json:
            verb = "Submitted" if submission.created else "Reused"
            click.echo(
                f"{verb} release gate job {submission.job.job_id} "
                f"request_id={resolved_request_id}"
            )
        record = _follow_job(jobs, submission.job.job_id, as_json=as_json)
    except KeyboardInterrupt as error:
        if jobs is not None and submission is not None:
            jobs.cancel(submission.job.job_id)
        raise click.ClickException("release gate cancellation requested") from error
    except Exception as error:
        if isinstance(error, click.ClickException):
            raise
        raise click.ClickException(str(error)) from error
    finally:
        if jobs is not None:
            jobs.shutdown(wait=True, cancel_pending=False)

    if as_json:
        click.echo(json.dumps(record.as_dict(), sort_keys=True))
    if record.state is JobState.FAILED:
        raise click.ClickException(record.error or "release gate failed")
    if record.state is JobState.CANCELLED:
        raise click.ClickException("release gate was cancelled")
    if not as_json:
        result = record.result or {}
        click.echo(
            f"Release gate passed in {record.elapsed_seconds:.3f}s; "
            f"report={result.get('report_path')} "
            f"artifacts={result.get('artifact_manifest_path')}"
        )


def _follow_job(jobs: JobService, job_id: str, *, as_json: bool):
    sequence = 0
    while True:
        for event in jobs.events(job_id=job_id, after_sequence=sequence, limit=100):
            sequence = event.sequence
            if not as_json:
                click.echo(
                    f"[{event.phase}] {event.progress * 100:5.1f}% "
                    f"{event.message or event.state.value} "
                    f"({event.elapsed_seconds:.3f}s)"
                )
        record = jobs.get(job_id)
        if record.state.terminal:
            return record
        time.sleep(0.05)
