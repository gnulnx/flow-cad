from __future__ import annotations

import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from flow_cad.measurement import (
    MeasurementLabelState,
    MeasurementSnapshotIdempotencyConflictError,
    MeasurementSnapshotStore,
    MeasurementSnapshotValidationError,
)


PART_UUID = "2ff3ad34-7a6c-4d15-9743-e9790e4ae0cc"
OTHER_PART_UUID = "1c78e813-3a84-4e0c-a2ad-f6e420a11a01"


def _measurement(*, hidden: bool = False, pinned: bool = True) -> MeasurementLabelState:
    return MeasurementLabelState(
        measurement_id="mount-centers",
        kind="distance",
        title="Exact circle center to exact circle center",
        quality="exact",
        start_mm=(1.0, 2.0, 3.0),
        end_mm=(4.0, 6.0, 15.0),
        total_mm=13.0,
        delta_mm=(3.0, 4.0, 12.0),
        feature_ids=("circle_center:4", "circle_center:9"),
        hidden=hidden,
        pinned=pinned,
        label_offset_px=(18.0, -7.0),
    )


def test_snapshot_is_fast_append_only_and_survives_restart(tmp_path: Path) -> None:
    store = MeasurementSnapshotStore(tmp_path)
    started = time.perf_counter()
    first, created = store.save_snapshot(
        thread_id="default",
        part_uuid=PART_UUID,
        artifact_revision="a" * 64,
        measurements=(_measurement(),),
        request_id="measurement-save-1",
    )
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert created is True
    assert elapsed_ms < 250
    assert store.path == tmp_path / ".flow" / "measurements.sqlite3"
    assert first.snapshot.part_uuid == PART_UUID
    assert first.snapshot.artifact_revision == "a" * 64
    assert first.snapshot.measurements[0].pinned is True
    assert first.snapshot.measurements[0].label_offset_px == (18.0, -7.0)

    cleared, _ = store.save_snapshot(
        thread_id="default",
        part_uuid=PART_UUID,
        artifact_revision="b" * 64,
        measurements=(),
        request_id="measurement-save-2",
    )
    reopened = MeasurementSnapshotStore(tmp_path)
    assert [event.sequence for event in reopened.snapshots("default", PART_UUID)] == [
        first.sequence,
        cleared.sequence,
    ]
    latest = reopened.latest_snapshot("default", PART_UUID)
    assert latest is not None
    assert latest.snapshot_id == cleared.snapshot.snapshot_id
    assert latest.artifact_revision == "b" * 64
    assert latest.measurements == ()

    with sqlite3.connect(reopened.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE measurement_snapshot_events SET event_type = 'changed' "
                "WHERE sequence = ?",
                (first.sequence,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM measurement_snapshot_events WHERE sequence = ?",
                (first.sequence,),
            )


def test_request_id_is_idempotent_and_contract_conflicts_are_rejected(tmp_path: Path) -> None:
    store = MeasurementSnapshotStore(tmp_path)
    first, first_created = store.save_snapshot(
        thread_id="thread-1",
        part_uuid=PART_UUID,
        artifact_revision="a" * 64,
        measurements=(_measurement(),),
        request_id="stable-request",
    )
    repeated, repeated_created = store.save_snapshot(
        thread_id="thread-1",
        part_uuid=PART_UUID,
        artifact_revision="a" * 64,
        measurements=(_measurement(),),
        request_id="stable-request",
    )
    assert first_created is True
    assert repeated_created is False
    assert repeated.event_id == first.event_id

    with pytest.raises(
        MeasurementSnapshotIdempotencyConflictError,
        match="different measurement snapshot",
    ):
        store.save_snapshot(
            thread_id="thread-1",
            part_uuid=PART_UUID,
            artifact_revision="b" * 64,
            measurements=(_measurement(),),
            request_id="stable-request",
        )


def test_latest_and_list_are_thread_and_part_bound(tmp_path: Path) -> None:
    store = MeasurementSnapshotStore(tmp_path)
    primary, _ = store.save_snapshot(
        thread_id="thread-1",
        part_uuid=PART_UUID,
        artifact_revision="a" * 64,
        measurements=(_measurement(),),
        request_id="primary",
    )
    store.save_snapshot(
        thread_id="thread-2",
        part_uuid=PART_UUID,
        artifact_revision="b" * 64,
        measurements=(),
        request_id="other-thread",
    )
    store.save_snapshot(
        thread_id="thread-1",
        part_uuid=OTHER_PART_UUID,
        artifact_revision="c" * 64,
        measurements=(),
        request_id="other-part",
    )

    assert [event.event_id for event in store.snapshots("thread-1", PART_UUID)] == [
        primary.event_id
    ]
    latest = store.latest_snapshot("thread-1", PART_UUID)
    assert latest is not None
    assert latest.artifact_revision == "a" * 64


def test_measurement_contract_rejects_untrustworthy_facts() -> None:
    with pytest.raises(MeasurementSnapshotValidationError, match="delta_mm"):
        MeasurementLabelState(
            measurement_id="bad-delta",
            kind="distance",
            title="Bad",
            quality="exact",
            start_mm=(0.0, 0.0, 0.0),
            end_mm=(3.0, 4.0, 0.0),
            total_mm=5.0,
            delta_mm=(3.0, 3.0, 0.0),
            feature_ids=("vertex:1", "vertex:2"),
        )
    with pytest.raises(MeasurementSnapshotValidationError, match="feature ID"):
        MeasurementLabelState(
            measurement_id="missing-features",
            kind="edge_length",
            title="Exact edge length",
            quality="exact",
            start_mm=(0.0, 0.0, 0.0),
            end_mm=(5.0, 0.0, 0.0),
            total_mm=5.0,
            delta_mm=(5.0, 0.0, 0.0),
            feature_ids=(),
        )


def test_snapshot_store_does_not_import_geometry_kernels(tmp_path: Path) -> None:
    script = """
import sys
from pathlib import Path
from flow_cad.measurement import MeasurementSnapshotStore
MeasurementSnapshotStore(Path(sys.argv[1]))
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
