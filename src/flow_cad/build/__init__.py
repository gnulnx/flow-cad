"""Scoped replacement build services.

This package deliberately stays separate from the preserved legacy build
pipeline. Planning is metadata-only; CAD imports occur only in the submitted
job worker.
"""

from .service import (
    BuildArtifactTarget,
    BuildContractError,
    PartBuildService,
    PartNotBuildableError,
    PartNotFoundError,
    ScopedPartBuildPlan,
    plan_scoped_part_build,
)

__all__ = [
    "BuildArtifactTarget",
    "BuildContractError",
    "PartBuildService",
    "PartNotBuildableError",
    "PartNotFoundError",
    "ScopedPartBuildPlan",
    "plan_scoped_part_build",
]
