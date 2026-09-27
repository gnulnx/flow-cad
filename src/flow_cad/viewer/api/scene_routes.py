"""Lightweight queries and cancellable jobs for STEP color display scenes."""
from pathlib import Path
import threading
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from flow_cad.jobs import JobService
from flow_cad.viewer.services.scenes import DisplaySceneService, SCENE_VERSION
from .measurement_routes import _http_error


def create_scene_router(root: Path, job_service: JobService):
    service = DisplaySceneService(root)
    router = APIRouter(prefix="/api/parts", tags=["display scenes"])
    active = {}
    submission_lock = threading.Lock()

    def lookup(part_uuid, artifact_revision):
        try:
            return service.lookup(part_uuid, artifact_revision)
        except Exception as exc:
            raise _http_error(exc) from exc

    @router.get("/{part_uuid}/display-scene")
    def scene(part_uuid: str, artifact_revision: str):
        _, payload = lookup(part_uuid, artifact_revision)
        return payload or {"status": "job_required"}

    @router.get("/{part_uuid}/display-scene/model")
    def model(part_uuid: str, artifact_revision: str):
        _, payload = lookup(part_uuid, artifact_revision)
        if payload is None:
            raise HTTPException(404, "Display scene is not ready")
        return FileResponse(service.paths(artifact_revision)[0], media_type="model/gltf-binary",
                            headers={"Cache-Control": "no-cache", "ETag": f'"{payload["sha256"]}"'})

    @router.post("/{part_uuid}/display-scene/jobs")
    def queue(part_uuid: str, artifact_revision: str):
        binding, payload = lookup(part_uuid, artifact_revision)
        if payload:
            return payload
        with submission_lock:
            job_id = active.get(artifact_revision)
            job = job_service.get(job_id) if job_id else None
            if job is None or job.state.terminal:
                submission = job_service.submit(
                    request_id=f"display-scene:{artifact_revision}:{uuid4()}", kind="display-scene",
                    payload={"label": "Prepare component colors", "part_uuid": part_uuid,
                             "artifact_revision": artifact_revision, "version": SCENE_VERSION},
                    work=lambda context: service.build(binding, context),
                )
                job = submission.job
                active[artifact_revision] = job.job_id
        return {"status": job.state.value, "job_id": job.job_id,
                "job_url": f"/api/workbench/v1/jobs/{job.job_id}",
                "cancel_url": f"/api/workbench/v1/jobs/{job.job_id}/cancel"}

    return router
