from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from flow_cad.measurement import MeasurementSnapshotStore
from flow_cad.viewer.api.measurement_snapshot_routes import (
    create_measurement_snapshot_router,
)


PART_UUID = "2ff3ad34-7a6c-4d15-9743-e9790e4ae0cc"
BASE_URL = f"/api/measurements/threads/default/parts/{PART_UUID}"


def _client(project_root: Path) -> TestClient:
    app = FastAPI()
    app.include_router(create_measurement_snapshot_router(MeasurementSnapshotStore(project_root)))
    return TestClient(app)


def _request(*, request_id: str = "measurement-1") -> dict[str, object]:
    return {
        "request_id": request_id,
        "artifact_revision": "a" * 64,
        "measurements": [
            {
                "measurement_id": "mount-centers",
                "kind": "distance",
                "title": "Exact circle center to exact circle center",
                "quality": "exact",
                "start_mm": [1, 2, 3],
                "end_mm": [4, 6, 15],
                "total_mm": 13,
                "delta_mm": [3, 4, 12],
                "feature_ids": ["circle_center:4", "circle_center:9"],
                "hidden": False,
                "pinned": True,
                "label_offset_px": [18, -7],
            }
        ],
    }


def test_save_list_and_latest_preserve_current_label_state(tmp_path: Path) -> None:
    client = _client(tmp_path)
    empty = client.get(f"{BASE_URL}/latest")
    assert empty.status_code == 204

    saved = client.post(f"{BASE_URL}/snapshots", json=_request())
    assert saved.status_code == 201
    payload = saved.json()
    assert payload["created"] is True
    snapshot = payload["event"]["snapshot"]
    assert snapshot["thread_id"] == "default"
    assert snapshot["part_uuid"] == PART_UUID
    assert snapshot["artifact_revision"] == "a" * 64
    assert snapshot["measurements"][0]["feature_ids"] == [
        "circle_center:4",
        "circle_center:9",
    ]
    assert snapshot["measurements"][0]["pinned"] is True
    assert snapshot["measurements"][0]["label_offset_px"] == [18.0, -7.0]

    latest = client.get(f"{BASE_URL}/latest")
    assert latest.status_code == 200
    assert latest.json()["snapshot_id"] == snapshot["snapshot_id"]

    listed = client.get(f"{BASE_URL}/snapshots?after_sequence=0")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    sequence = listed.json()["events"][0]["sequence"]
    assert client.get(f"{BASE_URL}/snapshots?after_sequence={sequence}").json()["count"] == 0


def test_save_is_idempotent_and_changed_or_invalid_contract_is_rejected(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    first = client.post(f"{BASE_URL}/snapshots", json=_request())
    repeated = client.post(f"{BASE_URL}/snapshots", json=_request())
    assert first.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json()["created"] is False
    assert repeated.json()["event"]["event_id"] == first.json()["event"]["event_id"]

    changed = _request()
    changed["measurements"] = []
    conflict = client.post(f"{BASE_URL}/snapshots", json=changed)
    assert conflict.status_code == 409

    invalid_revision = _request(request_id="uppercase-revision")
    invalid_revision["artifact_revision"] = "A" * 64
    invalid = client.post(f"{BASE_URL}/snapshots", json=invalid_revision)
    assert invalid.status_code == 400
    assert "lowercase hexadecimal" in invalid.json()["detail"]

    invalid_facts = _request(request_id="bad-facts")
    measurements = invalid_facts["measurements"]
    assert isinstance(measurements, list)
    measurements[0]["total_mm"] = 12
    invalid = client.post(f"{BASE_URL}/snapshots", json=invalid_facts)
    assert invalid.status_code == 400
    assert "length of delta_mm" in invalid.json()["detail"]


def test_empty_snapshot_durably_represents_clear_all(tmp_path: Path) -> None:
    client = _client(tmp_path)
    request = _request(request_id="clear-all")
    request["measurements"] = []
    response = client.post(f"{BASE_URL}/snapshots", json=request)
    assert response.status_code == 201
    assert response.json()["event"]["snapshot"]["measurements"] == []
    assert client.get(f"{BASE_URL}/latest").json()["measurements"] == []
