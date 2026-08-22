"""Exact, revision-bound measurement facts for STEP-backed parts.

Importing this package is metadata-only.  The CAD kernel is loaded lazily by
the extraction worker after a background job starts.
"""

from .service import (
    ArtifactBytesChangedError,
    ArtifactRevisionMismatchError,
    ExactFeatureBinding,
    ExactFeatureLookup,
    ExactFeatureService,
    ExactGeometryUnavailableError,
    InvalidArtifactRevisionError,
    PartNotFoundError,
)

__all__ = [
    "ArtifactBytesChangedError",
    "ArtifactRevisionMismatchError",
    "ExactFeatureBinding",
    "ExactFeatureLookup",
    "ExactFeatureService",
    "ExactGeometryUnavailableError",
    "InvalidArtifactRevisionError",
    "PartNotFoundError",
]
