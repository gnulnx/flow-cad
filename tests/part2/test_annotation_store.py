from __future__ import annotations

import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from flow_cad.annotations import (
    AnnotationContext,
    AnnotationMark,
    AnnotationStore,
    AnnotationValidationError,
    IdempotencyConflictError,
    NormalizedPoint,
)


def _context(revision: str = "step-sha-1") -> AnnotationContext:
    return AnnotationContext(
        camera={
            "position": [120.0, 80.0, 60.0],
            "target": [0.0, 0.0, 0.0],
            "up": [0.0, 0.0, 1.0],
        },
        viewport={"width": 1280, "height": 720, "render_context": "viewport-canvas"},
        artifact_revision=revision,
        visible_occurrence_ids=("guard-main", "motor-left"),
        viewer_revision="9",
    )


def _marks() -> tuple[AnnotationMark, ...]:
    return (
        AnnotationMark(
            mark_id="pen-1",
            kind="pen",
            points=(NormalizedPoint(0.1, 0.2), NormalizedPoint(0.3, 0.4)),
            color="#f0c983",
            stroke_width=2.0,
        ),
        AnnotationMark(
            mark_id="arrow-1",
            kind="arrow",
            points=(NormalizedPoint(0.5, 0.5), NormalizedPoint(0.75, 0.7)),
            color="#79cbd1",
            stroke_width=2.5,
        ),
        AnnotationMark(
            mark_id="text-1",
            kind="text",
            points=(NormalizedPoint(0.8, 0.2),),
            color="#ffffff",
            stroke_width=1.0,
            text="Review this clearance",
        ),
    )


def test_snapshot_is_fast_append_only_and_survives_restart(tmp_path: Path) -> None:
    store = AnnotationStore(tmp_path)
    started = time.perf_counter()
    first, created = store.save_snapshot(
        thread_id="default",
        marks=_marks(),
        context=_context(),
        request_id="annotation-save-1",
    )
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert created is True
    assert elapsed_ms < 250
    assert first.snapshot.intent == "review_intent"
    assert first.snapshot.context.artifact_revision == "step-sha-1"
    assert first.snapshot.context.visible_occurrence_ids == ("guard-main", "motor-left")
    assert first.snapshot.marks[0].points[0].as_list() == [0.1, 0.2]

    second, _ = store.save_snapshot(
        thread_id="default",
        marks=_marks()[:-1],
        context=_context("step-sha-2"),
        hidden=True,
        request_id="annotation-save-2",
    )
    reopened = AnnotationStore(tmp_path)
    assert [event.sequence for event in reopened.events("default")] == [
        first.sequence,
        second.sequence,
    ]
    latest = reopened.latest_snapshot("default")
    assert latest is not None
    assert latest.snapshot_id == second.snapshot.snapshot_id
    assert latest.hidden is True
    assert latest.context.artifact_revision == "step-sha-2"

    with sqlite3.connect(reopened.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE annotation_events SET event_type = 'changed' WHERE sequence = ?",
                (first.sequence,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM annotation_events WHERE sequence = ?", (first.sequence,)
            )


def test_request_id_is_idempotent_and_rejects_changed_contract(tmp_path: Path) -> None:
    store = AnnotationStore(tmp_path)
    first, first_created = store.save_snapshot(
        thread_id="thread-1",
        marks=_marks(),
        context=_context(),
        request_id="stable-request",
    )
    repeated, repeated_created = store.save_snapshot(
        thread_id="thread-1",
        marks=_marks(),
        context=_context(),
        request_id="stable-request",
    )
    assert first_created is True
    assert repeated_created is False
    assert repeated.event_id == first.event_id

    with pytest.raises(IdempotencyConflictError, match="different annotation snapshot"):
        store.save_snapshot(
            thread_id="thread-1",
            marks=(),
            context=_context(),
            request_id="stable-request",
        )


def test_normalized_review_marks_reject_topology_or_out_of_range_points() -> None:
    with pytest.raises(AnnotationValidationError, match="normalized"):
        NormalizedPoint(1.1, 0.5)
    with pytest.raises(AnnotationValidationError, match="review intent"):
        AnnotationMark(
            mark_id="bad",
            kind="circle",
            points=(NormalizedPoint(0.2, 0.2), NormalizedPoint(0.3, 0.3)),
            color="#fff",
            stroke_width=2,
            intent="cad_topology",
        )
    with pytest.raises(AnnotationValidationError, match="non-empty text"):
        AnnotationMark(
            mark_id="bad-text",
            kind="text",
            points=(NormalizedPoint(0.2, 0.2),),
            color="#fff",
            stroke_width=2,
            text=" ",
        )


def test_annotation_package_does_not_import_geometry_kernels(tmp_path: Path) -> None:
    script = """
import sys
from pathlib import Path
from flow_cad.annotations import AnnotationStore
AnnotationStore(Path(sys.argv[1]))
for name in sorted(sys.modules):
    if name == 'build123d' or name.startswith('build123d.') or name == 'OCP' or name.startswith('OCP.'):
        raise SystemExit(name)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout
