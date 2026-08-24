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
    ProjectBuildMode,
    ProjectBuildPlan,
    ProjectBuildService,
    ScopedPartBuildPlan,
    plan_scoped_part_build,
)
from .publication import BuildPublication, BuildPublicationError, publish_part_build

__all__ = [
    "BuildArtifactTarget",
    "BuildContractError",
    "BuildPublication",
    "BuildPublicationError",
    "PartBuildService",
    "PartNotBuildableError",
    "PartNotFoundError",
    "ProjectBuildMode",
    "ProjectBuildPlan",
    "ProjectBuildService",
    "ScopedPartBuildPlan",
    "plan_scoped_part_build",
    "publish_part_build",
]
