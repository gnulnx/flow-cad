"""Viewport review-annotation contracts and durable project-local storage."""

from .models import (
    AnnotationContext,
    AnnotationEvent,
    AnnotationMark,
    AnnotationSnapshot,
    AnnotationValidationError,
    NormalizedPoint,
)
from .store import (
    AnnotationStore,
    AnnotationStoreError,
    IdempotencyConflictError,
    UnsupportedAnnotationSchemaError,
)

__all__ = [
    "AnnotationContext",
    "AnnotationEvent",
    "AnnotationMark",
    "AnnotationSnapshot",
    "AnnotationStore",
    "AnnotationStoreError",
    "AnnotationValidationError",
    "IdempotencyConflictError",
    "NormalizedPoint",
    "UnsupportedAnnotationSchemaError",
]
