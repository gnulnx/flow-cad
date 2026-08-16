from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from flow_cad.profiler import FlowCadProfiler, write_validator_profile
from flow_cad.project import FlowCadProject, _call_with_supported_kwargs
from flow_cad.validation.contracts import (
    GeometryAuthority,
    ValidatorMetadata,
    ValidatorReport,
    coerce_validator_result,
    error,
    report_with_issues,
)
from flow_cad.validation.facts import FactResult, ValidationFactProvider
from flow_cad.validation.panel import PANEL_BASIC_METADATA, validate_panel_facts


ValidatorCallable = Callable[["ValidationContext"], Any]


@dataclass(frozen=True)
class ValidationContext:
    project: FlowCadProject
    params: Any
    facts: ValidationFactProvider
    part_id: str | None = None
    family: str | None = None
    tag: str | None = None
    draft_token: str | None = None
    draft_transaction: str | None = None
    changed: bool = False


@dataclass(frozen=True)
class FocusedValidator:
    metadata: ValidatorMetadata
    callback: ValidatorCallable
    source: str = "builtin"


class ValidationRunnerError(RuntimeError):
    pass


class FocusedValidatorRunner:
    def __init__(self, project: FlowCadProject, *, params: Any | None = None):
        self.project = project
        self.params = params if params is not None else project.make_params()
        self.facts = ValidationFactProvider(project, params=self.params)

    def validators(self) -> list[FocusedValidator]:
        validators: dict[str, FocusedValidator] = {
            PANEL_BASIC_METADATA.id: FocusedValidator(
                PANEL_BASIC_METADATA,
                _run_panel_basic,
                source="builtin",
            )
        }
        for name, validator in self.project.iter_validators():
            metadata = _metadata_for_project_validator(name, validator)
            validators[metadata.id] = FocusedValidator(
                metadata,
                _project_validator_callback(validator, metadata),
                source="project",
            )
        return list(validators.values())

    def list_validators(
        self,
        *,
        family: str | None = None,
        tag: str | None = None,
    ) -> list[dict[str, Any]]:
        selected = self.select_validators(family=family, tag=tag)
        return [
            {
                **validator.metadata.to_dict(),
                "source": validator.source,
            }
            for validator in selected
        ]

    def select_validators(
        self,
        validator_id: str | None = None,
        *,
        family: str | None = None,
        tag: str | None = None,
    ) -> list[FocusedValidator]:
        validators = self.validators()
        if validator_id:
            validators = [validator for validator in validators if validator.metadata.id == validator_id]
            if not validators:
                raise ValidationRunnerError(f"Focused validator not found: {validator_id}")
        if family:
            validators = [validator for validator in validators if validator.metadata.family == family]
        if tag:
            validators = [validator for validator in validators if tag in validator.metadata.tags]
        if not validators:
            raise ValidationRunnerError("No focused validators matched the requested selection.")
        return validators

    def run(
        self,
        validator_id: str | None = None,
        *,
        part_id: str | None = None,
        family: str | None = None,
        tag: str | None = None,
        draft_token: str | None = None,
        draft_transaction: str | None = None,
        changed: bool = False,
        command: str = "flow validate run",
        profile: bool = True,
    ) -> tuple[list[ValidatorReport], dict[str, Any] | None]:
        validators = self.select_validators(validator_id, family=family, tag=tag)
        context = ValidationContext(
            project=self.project,
            params=self.params,
            facts=self.facts,
            part_id=part_id,
            family=family,
            tag=tag,
            draft_token=draft_token,
            draft_transaction=draft_transaction,
            changed=changed,
        )
        profiler = FlowCadProfiler(
            project_id=self.project.project_id,
            project_root=self.project.root,
            command=command,
            build_profile="validate",
        )
        reports: list[ValidatorReport] = []
        status = "ok"

        for validator in validators:
            event_metadata = {
                "validator_id": validator.metadata.id,
                "family": validator.metadata.family,
                "mode": validator.metadata.mode,
                "part_id": part_id or "",
                "draft_token": draft_token or "",
                "draft_transaction": draft_transaction or "",
                "budget_ms": validator.metadata.budget_ms,
            }
            started = time.perf_counter()
            with profiler.measure("validator", validator.metadata.id, part_id=part_id or validator.metadata.id, metadata=event_metadata):
                result = self._run_one(validator, context)
                elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
                report = coerce_validator_result(
                    result,
                    validator.metadata,
                    elapsed_ms=elapsed_ms,
                    input_summary={"part_id": part_id or "", "geometry_authority": GeometryAuthority.UNKNOWN},
                    default_part_id=part_id,
                    default_family=validator.metadata.family,
                )
                event_metadata.update(report.profile_metadata(part_id=part_id, draft_token=draft_token))
                event_metadata["draft_transaction"] = draft_transaction or ""
            reports.append(report)
            if not report.ok:
                status = "failed"

        profiler.finish(status)
        profile_payload: dict[str, Any] | None = None
        if profile:
            paths = write_validator_profile(profiler, self.project.paths.local_state)
            profile_payload = {
                "profile_path": str(paths.profile_path),
                "latest_path": str(paths.latest_path),
                "profile": profiler.to_dict(),
            }
        return reports, profile_payload

    def _run_one(self, validator: FocusedValidator, context: ValidationContext) -> Any:
        try:
            return validator.callback(context)
        except Exception as exc:
            return report_with_issues(
                validator.metadata,
                [
                    error(
                        "validator_exception",
                        f"Focused validator {validator.metadata.id!r} raised {type(exc).__name__}: {exc}",
                        part_id=context.part_id,
                        family=validator.metadata.family,
                        geometry_authority=GeometryAuthority.UNKNOWN,
                        remediation="Fix the validator implementation or run with --json for structured details.",
                    )
                ],
                input_summary={
                    "part_id": context.part_id or "",
                    "geometry_authority": GeometryAuthority.UNKNOWN,
                },
            )


def _metadata_for_project_validator(name: str, validator: Callable[..., Any]) -> ValidatorMetadata:
    metadata = getattr(validator, "validator_metadata", None)
    return ValidatorMetadata.from_any(metadata, default_id=name)


def _project_validator_callback(validator: Callable[..., Any], metadata: ValidatorMetadata) -> ValidatorCallable:
    def callback(context: ValidationContext) -> Any:
        definitions = list(context.project.iter_part_definitions())
        return _call_with_supported_kwargs(
            validator,
            context=context,
            _project=context.project,
            project=context.project,
            params=context.params,
            definitions=definitions,
            facts=context.facts,
            part_id=context.part_id,
            draft_token=context.draft_token,
            draft_transaction=context.draft_transaction,
        )

    return callback


def _run_panel_basic(context: ValidationContext) -> ValidatorReport:
    fact_result: FactResult
    if context.draft_transaction:
        fact_result = context.facts.draft_transaction_facts(context.draft_transaction)
        if fact_result.facts is not None and isinstance(fact_result.facts.get("draft"), dict):
            return validate_panel_facts(fact_result.facts["draft"], part_id=context.part_id)
        return report_with_issues(
            PANEL_BASIC_METADATA,
            fact_result.issues,
            input_summary={
                "draft_transaction": context.draft_transaction,
                "geometry_authority": GeometryAuthority.DRAFT,
            },
        )

    if context.draft_token:
        fact_result = context.facts.draft_facts(context.draft_token)
        if fact_result.facts is not None:
            return validate_panel_facts(fact_result.facts, part_id=context.part_id)
        return report_with_issues(
            PANEL_BASIC_METADATA,
            fact_result.issues,
            input_summary={
                "draft_token": context.draft_token,
                "geometry_authority": GeometryAuthority.DRAFT,
            },
        )

    if not context.part_id:
        return report_with_issues(
            PANEL_BASIC_METADATA,
            [
                error(
                    "panel_part_required",
                    "`panel-basic` requires --part, --draft-token, or --draft-transaction.",
                    family=PANEL_BASIC_METADATA.family,
                    geometry_authority=GeometryAuthority.UNKNOWN,
                    remediation="Pass a part id or draft token to validate panel facts.",
                )
            ],
            input_summary={"geometry_authority": GeometryAuthority.UNKNOWN},
        )

    cache_result = context.facts.active_cache_row(context.part_id, required=False, require_fresh=True)
    if cache_result.facts is not None and not cache_result.issues:
        return validate_panel_facts(cache_result.facts, part_id=context.part_id)

    step_result = context.facts.step_bounding_box(context.part_id)
    if step_result.facts is not None:
        report = validate_panel_facts(step_result.facts, part_id=context.part_id)
        stale_warnings = [issue.message for issue in cache_result.issues if issue.check_id.startswith("cache_")]
        if stale_warnings:
            return ValidatorReport(
                metadata=report.metadata,
                elapsed_ms=report.elapsed_ms,
                input_summary=report.input_summary,
                issues=report.issues,
                warnings=tuple([*report.warnings, *stale_warnings]),
            )
        return report

    issues = [*cache_result.issues, *step_result.issues]
    return report_with_issues(
        PANEL_BASIC_METADATA,
        issues,
        input_summary={
            "part_id": context.part_id,
            "geometry_authority": GeometryAuthority.UNKNOWN,
        },
    )


def concise_report_lines(reports: list[ValidatorReport]) -> list[str]:
    lines: list[str] = []
    for report in reports:
        status = "ok" if report.ok else "failed"
        counts = report.to_dict()["issue_counts"]
        lines.append(
            f"{report.metadata.id}: {status} "
            f"({counts['error']} error, {counts['warning']} warning, {counts['info']} info, "
            f"{report.elapsed_ms:.1f} ms)"
        )
        for issue in report.issues:
            if issue.severity == "info":
                continue
            location = f" part={issue.part_id}" if issue.part_id else ""
            lines.append(f"- {issue.severity} {issue.check_id}{location}: {issue.message}")
    return lines
