"""Lazy public access to generic validation contracts."""

from __future__ import annotations

import importlib
from typing import Any


_EXPORTS = {
    "GeometryAuthority": ("flow_cad.validation.contracts", "GeometryAuthority"),
    "Severity": ("flow_cad.validation.contracts", "Severity"),
    "ValidatorIssue": ("flow_cad.validation.contracts", "ValidatorIssue"),
    "ValidatorMetadata": ("flow_cad.validation.contracts", "ValidatorMetadata"),
    "ValidatorMode": ("flow_cad.validation.contracts", "ValidatorMode"),
    "ValidatorReport": ("flow_cad.validation.contracts", "ValidatorReport"),
    "coerce_validator_result": ("flow_cad.validation.contracts", "coerce_validator_result"),
    "error": ("flow_cad.validation.contracts", "error"),
    "info": ("flow_cad.validation.contracts", "info"),
    "report_with_issues": ("flow_cad.validation.contracts", "report_with_issues"),
    "success_report": ("flow_cad.validation.contracts", "success_report"),
    "warning": ("flow_cad.validation.contracts", "warning"),
    "FactResult": ("flow_cad.validation.facts", "FactResult"),
    "ValidationFactProvider": ("flow_cad.validation.facts", "ValidationFactProvider"),
    "PANEL_BASIC_METADATA": ("flow_cad.validation.panel", "PANEL_BASIC_METADATA"),
    "validate_panel_facts": ("flow_cad.validation.panel", "validate_panel_facts"),
    "placement_issues": ("flow_cad.validation.placement", "placement_issues"),
    "FocusedValidatorRunner": ("flow_cad.validation.runner", "FocusedValidatorRunner"),
    "ValidationContext": ("flow_cad.validation.runner", "ValidationContext"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(importlib.import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted({*globals(), *_EXPORTS})
